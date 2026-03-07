"""
End-to-end inference for one UTC hour.

Usage:
    python3 scripts/run_inference_hour.py 2024-01-15T06:00:00Z

Produces: outputs/spatial/fog_prob_{YYYYMMDD}_{HH}UTC.tif
"""

import sys
import json
import pickle
import numpy as np
import pandas as pd
import xgboost as xgb
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to path so we can import scripts/
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.spatial_pipeline import run_spatial_pipeline

# ── Paths ───────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
MODEL_PATH      = ROOT / "models/xgb_asos_hrrr_full_v1.json"
CALIBRATOR_PATH = ROOT / "models/calibrator_platt_v2.pkl"
STATION_LIST    = ROOT / "models/enhanced_asos_station_list.json"

# Cache station list at module level — loaded once, reused across all 12 forecast hours
with open(STATION_LIST) as _f:
    _STATION_LIST_CACHE = json.load(_f)
ASOS_TEST      = ROOT / "data/raw/asos/dc_metro_test_2024_2026.parquet"
HRRR_TEST      = ROOT / "data/raw/hrrr/hrrr_test_dc_2024.parquet"

# ── Station metadata (lat/lon from ASOS data, confirmed against spatial guide)
STATION_COORDS = {
    "KBWI": (39.1733, -76.6841),
    "KCGS": (38.9806, -76.9223),
    "KDCA": (38.8472, -77.0345),
    "KFDK": (39.4176, -77.3743),
    "KGAI": (39.1683, -77.1660),
    "KHEF": (38.7214, -77.5154),
    "KIAD": (38.9348, -77.4473),
    "KNYG": (38.5017, -77.3053),
}


def build_asos_features(valid_dt: datetime) -> pd.DataFrame:
    """
    Load ASOS features for the *previous* hour (lag=1) relative to valid_dt.

    The model was trained with lag features: the ASOS observation from the
    hour before the prediction time. We also compute hour/month cyclic features
    from valid_dt itself (the prediction hour).
    """
    lag_time = valid_dt - timedelta(hours=1)

    asos = pd.read_parquet(ASOS_TEST)
    asos["valid"] = pd.to_datetime(asos["valid"], utc=True)

    # Grab the row closest to lag_time for each station (within ±30 min)
    lag_utc = lag_time.replace(tzinfo=timezone.utc) if lag_time.tzinfo is None else lag_time
    window = asos[
        (asos["valid"] >= lag_utc - timedelta(minutes=30)) &
        (asos["valid"] <= lag_utc + timedelta(minutes=30))
    ].copy()

    if window.empty:
        raise ValueError(f"No ASOS data found near lag time {lag_utc}")

    # One row per station (nearest to lag_time)
    window["dt_diff"] = (window["valid"] - lag_utc).abs()
    asos_lag = window.sort_values("dt_diff").groupby("station").first().reset_index()

    # Compute lag features
    asos_lag["t_td_spread_lag"] = asos_lag["t_td_spread"] if "t_td_spread" in asos_lag.columns \
        else (asos_lag["tmpf"] - asos_lag["dwpf"])
    asos_lag["wind_speed_mph_lag"] = asos_lag["wind_speed_mph"] if "wind_speed_mph" in asos_lag.columns \
        else asos_lag["sknt"] * 1.15078

    drct_rad = np.radians(asos_lag["drct"].fillna(0))
    asos_lag["drct_sin_lag"] = np.sin(drct_rad)
    asos_lag["drct_cos_lag"] = np.cos(drct_rad)

    # Hour/month cyclic features from the *prediction* hour
    vdt = valid_dt.replace(tzinfo=timezone.utc) if valid_dt.tzinfo is None else valid_dt
    hour = vdt.hour
    month = vdt.month
    asos_lag["hour_sin"]   = np.sin(2 * np.pi * hour / 24)
    asos_lag["hour_cos"]   = np.cos(2 * np.pi * hour / 24)
    # CRITICAL: month is 1-indexed, no -1 offset — matches training formula
    asos_lag["month_sin"]  = np.sin(2 * np.pi * month / 12)
    asos_lag["month_cos"]  = np.cos(2 * np.pi * month / 12)

    return asos_lag[["station", "elevation", "t_td_spread_lag", "wind_speed_mph_lag",
                      "drct_sin_lag", "drct_cos_lag",
                      "hour_sin", "hour_cos", "month_sin", "month_cos"]]


def build_hrrr_features(valid_dt: datetime) -> pd.DataFrame:
    """Load HRRR features for the given valid_time across 8 DC stations."""
    hrrr = pd.read_parquet(HRRR_TEST)
    hrrr["valid_time"] = pd.to_datetime(hrrr["valid_time"], utc=True)

    vdt = valid_dt.replace(tzinfo=timezone.utc) if valid_dt.tzinfo is None else valid_dt
    window = hrrr[
        (hrrr["valid_time"] >= vdt - timedelta(minutes=30)) &
        (hrrr["valid_time"] <= vdt + timedelta(minutes=30))
    ].copy()

    if window.empty:
        raise ValueError(f"No HRRR data found for valid_time {vdt}")

    window["dt_diff"] = (window["valid_time"] - vdt).abs()
    hrrr_hour = window.sort_values("dt_diff").groupby("station").first().reset_index()

    # Fill cloud base NaN with 10,000m sentinel (no cloud = very high ceiling)
    hrrr_hour["hgt_cldbase_m"] = hrrr_hour["hgt_cldbase_m"].fillna(10000.0)

    return hrrr_hour[["station", "hpbl_m", "tcdc_bl_pct", "dpt2m_k", "tmp2m_k",
                       "rh2m_pct", "hgt_cldbase_m", "u10_ms", "v10_ms"]]


def encode_station(df: pd.DataFrame, station_list: list) -> pd.DataFrame:
    """Encode station_code as pd.Categorical — required for enable_categorical=True model."""
    cat_dtype = pd.CategoricalDtype(categories=station_list, ordered=False)
    codes = df["station"].astype(cat_dtype).cat.codes.astype("Int64")
    codes = codes.where(codes >= 0, other=pd.NA)
    df["station_code"] = pd.Categorical.from_codes(
        codes.fillna(-1).astype(int),
        categories=range(len(station_list)),
    )
    df.loc[codes.isna(), "station_code"] = np.nan
    return df


def infer_from_dataframes(asos_feat: pd.DataFrame, hrrr_feat: pd.DataFrame,
                           valid_dt: datetime,
                           model=None, cal_dict: dict = None):
    """
    Core inference: merge ASOS + HRRR, run XGBoost + Platt calibration.

    model    : pre-loaded XGBClassifier (pass None to load from disk)
    cal_dict : pre-loaded calibrator dict (pass None to load from disk)

    Returns (cal_probs: np.ndarray, stations: list)
    """
    import pickle as _pickle
    import xgboost as _xgb

    if model is None:
        model = _xgb.XGBClassifier()
        model.load_model(MODEL_PATH)
    if cal_dict is None:
        with open(CALIBRATOR_PATH, "rb") as f:
            cal_dict = _pickle.load(f)

    # Add hour/month cyclic features from valid_dt
    vdt = valid_dt.replace(tzinfo=timezone.utc) if valid_dt.tzinfo is None else valid_dt
    hour = vdt.hour
    month = vdt.month
    asos_feat = asos_feat.copy()
    asos_feat["hour_sin"]  = np.sin(2 * np.pi * hour / 24)
    asos_feat["hour_cos"]  = np.cos(2 * np.pi * hour / 24)
    asos_feat["month_sin"] = np.sin(2 * np.pi * month / 12)
    asos_feat["month_cos"] = np.cos(2 * np.pi * month / 12)

    merged = pd.merge(asos_feat, hrrr_feat, on="station", how="inner")
    if merged.empty:
        return np.array([]), []

    merged = encode_station(merged, _STATION_LIST_CACHE)

    feature_cols = cal_dict["features"]
    fill_medians = cal_dict["fill_medians"]

    for col in feature_cols:
        if col not in merged.columns:
            merged[col] = fill_medians[col]

    X = merged[feature_cols].fillna(fill_medians)
    assert len(X.columns) == 18, f"Expected 18 features, got {len(X.columns)}: {list(X.columns)}"

    raw_scores = model.predict_proba(X)[:, 1]
    cal_probs  = cal_dict["calibrator"].predict_proba(
                     raw_scores.reshape(-1, 1))[:, 1]

    if np.any(cal_probs <= 0.0) or np.any(cal_probs >= 1.0):
        raise ValueError(f"Calibrated probs out of range [0,1]: "
                         f"min={cal_probs.min():.3f}, max={cal_probs.max():.3f}")
    # 0.40 = well above the expected [0.008, 0.252] range; flags model input anomalies
    if np.any(cal_probs > 0.40):
        print(f"  WARNING: Some calibrated probs outside expected [0.008, 0.252] range. "
              f"min={cal_probs.min():.3f}, max={cal_probs.max():.3f} — check model inputs.")

    return cal_probs, merged["station"].tolist()


def run_hour(valid_dt: datetime) -> str:
    """
    Full inference pipeline for one UTC hour.

    Returns the path to the output GeoTIFF.
    """
    print(f"\n=== Fogchaser inference: {valid_dt.strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    # 1. Load features
    print("Loading ASOS lag features...")
    asos_feat = build_asos_features(valid_dt)
    print(f"  {len(asos_feat)} stations with ASOS data")

    print("Loading HRRR features...")
    hrrr_feat = build_hrrr_features(valid_dt)
    print(f"  {len(hrrr_feat)} stations with HRRR data")

    # 2. Merge on station
    merged = pd.merge(asos_feat, hrrr_feat, on="station", how="inner")
    print(f"  {len(merged)} stations after merge: {sorted(merged['station'].tolist())}")

    # 3. Station encoding
    merged = encode_station(merged, _STATION_LIST_CACHE)

    # 4. Build feature matrix in model order
    with open(CALIBRATOR_PATH, "rb") as f:
        cal_dict = pickle.load(f)

    feature_cols = cal_dict["features"]
    fill_medians = cal_dict["fill_medians"]

    # Fill any missing features with training medians
    for col in feature_cols:
        if col not in merged.columns:
            merged[col] = fill_medians[col]
            print(f"  WARNING: {col} missing — filled with median {fill_medians[col]:.4f}")

    X = merged[feature_cols].copy()
    X = X.fillna(fill_medians)
    assert len(X.columns) == 18, f"Expected 18 features, got {len(X.columns)}: {list(X.columns)}"

    # 5. XGBoost inference
    print("\nRunning XGBoost model...")
    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH)
    raw_scores = model.predict_proba(X)[:, 1]
    print(f"  Raw scores: {np.round(raw_scores, 4)}")

    # 6. Platt calibration
    print("Applying Platt calibration...")
    calibrator = cal_dict["calibrator"]  # fitted LogisticRegression
    cal_probs = calibrator.predict_proba(raw_scores.reshape(-1, 1))[:, 1]
    threshold = cal_dict["best_threshold"]
    print(f"  Calibrated probs: {np.round(cal_probs, 4)}")
    print(f"  F2 threshold: {threshold}")
    alerts = cal_probs >= threshold
    print(f"  Stations above threshold: {merged['station'].values[alerts].tolist()}")

    # 7. Print per-station summary
    print("\n--- Per-station probabilities ---")
    for idx, (sta, raw, cal) in enumerate(zip(merged["station"], raw_scores, cal_probs)):
        alert = "FOG ALERT" if cal >= threshold else ""
        print(f"  {sta}: raw={raw:.3f} -> calibrated={cal:.3f}  {alert}")

    # 8. Spatial pipeline
    lats = [STATION_COORDS[s][0] for s in merged["station"]]
    lons = [STATION_COORDS[s][1] for s in merged["station"]]

    print("\nRunning spatial pipeline...")
    out_path = run_spatial_pipeline(
        station_probs=cal_probs,
        station_lats=lats,
        station_lons=lons,
        valid_dt=valid_dt,
    )

    print(f"\nDone. Fog map: {out_path}")
    return out_path


def main():
    if len(sys.argv) < 2:
        # Default: 2024-01-15 06:00 UTC (winter morning fog candidate)
        valid_dt = datetime(2024, 1, 15, 6, 0, tzinfo=timezone.utc)
    else:
        ts = sys.argv[1].rstrip("Z")
        valid_dt = datetime.fromisoformat(ts).replace(tzinfo=timezone.utc)

    run_hour(valid_dt)


if __name__ == "__main__":
    main()
