"""
Live forecast orchestrator.

Usage: python3 scripts/run_live_forecast.py

Finds the most recent HRRR run, fetches live ASOS, runs inference for
fxx=1-12, uploads GeoTIFFs to R2, writes manifest.json to app/data/.
"""
import json
import os
import pickle
import sys
import numpy as np
import rasterio
import xgboost as xgb
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.fetch_live_asos import fetch_asos_latest
from scripts.fetch_live_hrrr import fetch_hrrr_forecast_hour, DC_STATION_COORDS
from scripts.run_inference_hour import infer_from_dataframes, CALIBRATOR_PATH, MODEL_PATH, STATION_COORDS
from scripts.spatial_pipeline import run_spatial_pipeline
from scripts.upload_to_r2 import upload_tif, upload_manifest, get_r2_client

import pandas as pd

OUTPUT_DIR     = "/tmp/fog_output"   # local staging only — not committed
MANIFEST_PATH  = "app/data/manifest.json"
FORECAST_FXX   = range(1, 13)       # fxx=1 through fxx=12 (skip fxx=0 analysis)
HRRR_RUN_HOURS = list(range(24))

# Fog Risk Score thresholds — must match fogScore() in app.js exactly
_SCORE_THRESHOLDS = [0.08, 0.13, 0.17, 0.22]
_BASELINE_FOG_RATE = 0.054  # eval set Oct–Dec 2024, vs DC metro raw ~0.54%


def latest_hrrr_run(now_utc: datetime) -> datetime:
    """Return the most recent HRRR run that should be available (90-min lag)."""
    # CRITICAL: handle day boundary correctly using timedelta, not hour arithmetic
    cutoff = now_utc - timedelta(minutes=90)
    if any(h <= cutoff.hour for h in HRRR_RUN_HOURS):
        run_hour = max(h for h in HRRR_RUN_HOURS if h <= cutoff.hour)
        return cutoff.replace(hour=run_hour, minute=0, second=0, microsecond=0)
    # All run hours are after cutoff.hour — go to previous day, use 18 UTC
    prev = cutoff - timedelta(days=1)
    return prev.replace(hour=18, minute=0, second=0, microsecond=0)


def read_geotiff_mean(tif_path: str) -> float:
    with rasterio.open(tif_path) as src:
        arr = src.read(1).astype(float)
        nodata = src.nodata or -9999.0
    valid = arr[(arr >= 0.0) & (arr <= 1.0)]
    return float(np.mean(valid)) if len(valid) > 0 else 0.0


def build_asos_for_hour(asos_df: pd.DataFrame, hrrr_df: pd.DataFrame,
                         valid_dt: datetime, fxx: int,
                         cal_dict: dict) -> pd.DataFrame:
    """
    Build the full ASOS feature DataFrame for one forecast hour.

    For fxx=1: use real ASOS observations as lag features.
    For fxx>=2: real ASOS observations are in the future — substitute
    HRRR-derived T-Td spread and wind. This is an approximation; documented in the app.

    True boundary is whether valid_time > most_recent_asos_observation + 90 minutes.
    Using fxx>=2 as the cutoff is an approximation of this.
    """
    merged = pd.merge(asos_df, hrrr_df, on="station", how="inner")
    fill = cal_dict["fill_medians"]

    # Cyclic time features depend only on valid_dt — compute once, not per station
    # CRITICAL: use month/12 (1-indexed), NOT (month-1)/12 — must match training formula
    hour_sin  = np.sin(2 * np.pi * valid_dt.hour / 24)
    hour_cos  = np.cos(2 * np.pi * valid_dt.hour / 24)
    month_sin = np.sin(2 * np.pi * valid_dt.month / 12)
    month_cos = np.cos(2 * np.pi * valid_dt.month / 12)

    result = []
    for _, row in merged.iterrows():
        r = {"station": row["station"]}
        if fxx <= 1:
            # Real ASOS lag available
            r["t_td_spread_lag"]    = row.get("t_td_spread_lag",    fill["t_td_spread_lag"])
            r["wind_speed_mph_lag"] = row.get("wind_speed_mph_lag", fill["wind_speed_mph_lag"])
            r["drct_sin_lag"]       = row.get("drct_sin_lag",       fill["drct_sin_lag"])
            r["drct_cos_lag"]       = row.get("drct_cos_lag",       fill["drct_cos_lag"])
            r["elevation"]          = row.get("elevation",          fill["elevation"])
        else:
            # Future hours: substitute HRRR-derived values for all ASOS lag features.
            # T-Td spread: difference in K == difference in °C; *9/5 converts to °F scale.
            # No 273.15 offset needed — this is a temperature *difference*, not absolute.
            tmp_k = row.get("tmp2m_k", np.nan)
            dpt_k = row.get("dpt2m_k", np.nan)
            if not (np.isnan(tmp_k) or np.isnan(dpt_k)):
                r["t_td_spread_lag"] = max(0.0, float((tmp_k - dpt_k) * 9 / 5))
            else:
                r["t_td_spread_lag"] = fill["t_td_spread_lag"]
            # Wind: derive from HRRR u10/v10 (meteorological convention: FROM direction)
            u = row.get("u10_ms", np.nan)
            v = row.get("v10_ms", np.nan)
            if not (np.isnan(u) or np.isnan(v)):
                speed = float(np.sqrt(u**2 + v**2))
                r["wind_speed_mph_lag"] = speed * 2.237
                if speed >= 0.1:
                    r["drct_sin_lag"] = float(-u / speed)
                    r["drct_cos_lag"] = float(-v / speed)
                else:
                    r["drct_sin_lag"] = 0.0  # calm: no preferred direction
                    r["drct_cos_lag"] = 0.0
            else:
                r["wind_speed_mph_lag"] = fill["wind_speed_mph_lag"]
                r["drct_sin_lag"]       = fill["drct_sin_lag"]
                r["drct_cos_lag"]       = fill["drct_cos_lag"]
            r["elevation"] = row.get("elevation", fill["elevation"])

        r["hour_sin"]  = hour_sin
        r["hour_cos"]  = hour_cos
        r["month_sin"] = month_sin
        r["month_cos"] = month_cos
        result.append(r)

    return pd.DataFrame(result)


def _fail_entry(fxx: int, valid_dt: datetime) -> dict:
    return {"fxx": fxx, "valid_utc": valid_dt.strftime("%Y-%m-%dT%H:00:00Z"),
            "url": None, "approx_asos": fxx >= 2}


def main(override_run_time=None):
    """override_run_time: pass a datetime to run hindcast against a past HRRR run (for testing)."""
    now_utc  = datetime.now(timezone.utc)
    run_time = override_run_time if override_run_time else latest_hrrr_run(now_utc)
    print(f"\n{'='*60}")
    print(f"Fogchaser live forecast — {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"HRRR run: {run_time.strftime('%Y-%m-%d %H UTC')}")
    print(f"{'='*60}\n")

    # Load model, calibrator, and R2 client ONCE — not inside the per-hour loop
    print("Loading model and calibrator...")
    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH)
    with open(CALIBRATOR_PATH, "rb") as f:
        cal_dict = pickle.load(f)
    print(f"  Model loaded. Features: {len(cal_dict['features'])}")
    r2_client = get_r2_client()

    # Fetch ASOS once for current observations
    print("\nFetching live ASOS observations...")
    asos_df = fetch_asos_latest(lookback_hours=2)
    if asos_df.empty:
        print("ERROR: No ASOS data — aborting forecast.")
        sys.exit(1)
    print(f"  {len(asos_df)} stations: {sorted(asos_df['station'].tolist())}")

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    manifest = {
        "run_utc":       run_time.strftime("%Y-%m-%dT%H:00:00Z"),
        "generated_utc": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "asos_note": "fxx>=2: ASOS lag substituted with HRRR-derived values (approximation)",
        "hours": [],
    }

    for fxx in FORECAST_FXX:
        valid_dt = run_time + timedelta(hours=fxx)
        print(f"\n[fxx={fxx:02d}] {valid_dt.strftime('%Y-%m-%d %H UTC')}", end="  ")

        hrrr_df = fetch_hrrr_forecast_hour(run_time, fxx)
        if hrrr_df.empty:
            print("SKIP — HRRR unavailable")
            manifest["hours"].append(_fail_entry(fxx, valid_dt))
            continue

        try:
            asos_hour = build_asos_for_hour(asos_df, hrrr_df, valid_dt, fxx, cal_dict)

            # Spatial pipeline requires >=6 stations
            if len(asos_hour) < 6:
                missing = set(DC_STATION_COORDS.keys()) - set(asos_hour["station"].tolist())
                print(f"SKIP — only {len(asos_hour)} stations (missing: {sorted(missing)})")
                manifest["hours"].append(_fail_entry(fxx, valid_dt))
                continue

            cal_probs, stations = infer_from_dataframes(
                asos_hour, hrrr_df, valid_dt, model, cal_dict)
            if len(cal_probs) == 0:
                print("SKIP — no stations merged")
                manifest["hours"].append(_fail_entry(fxx, valid_dt))
                continue

            lats  = [DC_STATION_COORDS[s][0] for s in stations if s in DC_STATION_COORDS]
            lons  = [DC_STATION_COORDS[s][1] for s in stations if s in DC_STATION_COORDS]
            probs = [p for s, p in zip(stations, cal_probs) if s in DC_STATION_COORDS]

            tif_local = run_spatial_pipeline(
                station_probs=probs, station_lats=lats, station_lons=lons,
                terrain_offset_path="data/processed/terrain_offset_grid.tif",
                output_dir=OUTPUT_DIR, valid_dt=valid_dt,
            )

            # Rename to plan naming convention: fog_YYYYMMDD_HHZ_fxxNN.tif
            tif_final = str(Path(OUTPUT_DIR) / f"fog_{valid_dt.strftime('%Y%m%d_%H')}Z_fxx{fxx:02d}.tif")
            os.rename(tif_local, tif_final)

            avg_prob = read_geotiff_mean(tif_final)
            tif_url  = upload_tif(tif_final, client=r2_client)

            t1, t2, t3, t4 = _SCORE_THRESHOLDS
            score = (1 if avg_prob < t1 else
                     2 if avg_prob < t2 else
                     3 if avg_prob < t3 else
                     4 if avg_prob < t4 else 5)
            label = {1: "Low", 2: "Moderate", 3: "High", 4: "Very High", 5: "Extreme"}[score]
            relative_risk = round(avg_prob / _BASELINE_FOG_RATE, 1)

            # Aggregate conditions for the "Why this score" explainer
            def _mean(df, col):
                return round(float(df[col].mean()), 1) if col in df.columns else None

            merged_for_cond = asos_hour.merge(hrrr_df[["station","hpbl_m","hgt_cldbase_m","rh2m_pct"]],
                                              on="station", how="inner")
            conditions = {
                "t_td_spread_f": _mean(merged_for_cond, "t_td_spread_lag"),
                "wind_speed_mph": _mean(merged_for_cond, "wind_speed_mph_lag"),
                "hpbl_m":        _mean(merged_for_cond, "hpbl_m"),
                "hgt_cldbase_m": _mean(merged_for_cond, "hgt_cldbase_m"),
                "rh_pct":        _mean(merged_for_cond, "rh2m_pct"),
            }

            manifest["hours"].append({
                "fxx":           fxx,
                "valid_utc":     valid_dt.strftime("%Y-%m-%dT%H:00:00Z"),
                "score":         score,
                "label":         label,
                "relative_risk": relative_risk,
                "avg_prob":      round(avg_prob, 3),
                "url":           tif_url,
                "approx_asos":   fxx >= 2,
                "conditions":    conditions,
            })
            print(f"avg={avg_prob:.3f}  score={score}/5 [{label}]  {relative_risk}× baseline  → {Path(tif_url).name}")

        except Exception as e:
            print(f"ERROR: fxx={fxx} failed: {e}")
            manifest["hours"].append(_fail_entry(fxx, valid_dt))

    successful = sum(1 for h in manifest["hours"] if h.get("url") is not None)
    print(f"\n{successful} of {len(manifest['hours'])} forecast hours succeeded.")
    if successful < 10:
        print(f"ERROR: Only {successful} hours succeeded — marking run as failed.")
        sys.exit(1)

    # Write manifest to a temp file, validate, then upload to R2
    manifest_tmp = "/tmp/manifest.json"
    with open(manifest_tmp, "w") as f:
        json.dump(manifest, f, indent=2)
    with open(manifest_tmp) as f:
        json.load(f)  # raises if malformed
    manifest_url = upload_manifest(manifest_tmp, client=r2_client)
    print(f"Manifest uploaded: {manifest_url}  ({len(manifest['hours'])} hours)")


if __name__ == "__main__":
    main()
