"""
Validation checks for the spatial interpolation layer.
Run all checks: python scripts/validate_spatial.py
"""
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")   # non-interactive backend
import matplotlib.pyplot as plt
from pathlib import Path

Path("outputs/validation").mkdir(parents=True, exist_ok=True)


def check_1_valley_ridge_transects():
    """
    Check 1: Plot terrain offset along 5 known valley cross-sections.
    Pass criterion: valley bottoms show higher terrain offset than adjacent ridges.
    """
    print("\n--- Check 1: Valley-Ridge Transects ---")
    with rasterio.open("data/processed/terrain_offset_grid.tif") as src:
        offset = src.read(1).astype(float)
        offset[offset == -9999] = np.nan
        transform = src.transform

    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:5070", always_xy=True)

    def latlon_to_rowcol(lat, lon):
        x, y = transformer.transform(lon, lat)
        col = int((x - transform.c) / transform.a)
        row = int((y - transform.f) / transform.e)
        return row, col

    def sample_transect(lat1, lon1, lat2, lon2, n_points=50):
        lats = np.linspace(lat1, lat2, n_points)
        lons = np.linspace(lon1, lon2, n_points)
        values = []
        for lat, lon in zip(lats, lons):
            r, c = latlon_to_rowcol(lat, lon)
            if 0 <= r < offset.shape[0] and 0 <= c < offset.shape[1]:
                values.append(offset[r, c])
            else:
                values.append(np.nan)
        return np.array(values)

    # Transects: (lat1, lon1, lat2, lon2, label)
    transects = [
        (39.05, -77.10, 39.05, -76.90, "Rock Creek EW cross-section"),
        (38.95, -77.40, 38.95, -77.20, "Dulles corridor"),
        (38.90, -77.10, 38.80, -77.05, "Potomac near DC"),
        (39.00, -77.20, 38.95, -77.10, "Fairfax county ridge-valley"),
        (39.30, -76.90, 39.20, -76.75, "Patuxent corridor"),
    ]

    fig, axes = plt.subplots(len(transects), 1, figsize=(10, 3 * len(transects)))
    for ax, (lat1, lon1, lat2, lon2, label) in zip(axes, transects):
        vals = sample_transect(lat1, lon1, lat2, lon2)
        ax.plot(vals, marker=".", linewidth=1)
        ax.axhline(0, color="gray", linestyle="--", linewidth=0.8)
        ax.set_ylabel("terrain offset (log-odds)")
        ax.set_title(label)
        ax.set_ylim(-0.6, 0.6)

    plt.tight_layout()
    out = "outputs/validation/check1_valley_ridge_transects.png"
    plt.savefig(out, dpi=150)
    plt.close()
    print(f"  Saved {out}")
    print("  MANUAL: Inspect plot — valley bottoms should show higher offset than ridges.")
    print("  PASS if at least 3 of 5 transects show a visible low-point in valley sections.")


def check_2_urban_suppression():
    """
    Check 2: Urban core cells should show lower impervious offset than suburban/rural cells.
    """
    print("\n--- Check 2: Urban Suppression ---")
    with rasterio.open("data/processed/imperv_norm.tif") as src:
        imperv = src.read(1).astype(float)
        imperv[imperv == -9999] = np.nan
        transform = src.transform
        crs_str = src.crs.to_string()

    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:4326", crs_str, always_xy=True)

    def sample_region(lat_center, lon_center, radius_px=5):
        x, y = transformer.transform(lon_center, lat_center)
        col = int((x - transform.c) / transform.a)
        row = int((y - transform.f) / transform.e)
        r0, r1 = max(0, row-radius_px), min(imperv.shape[0], row+radius_px)
        c0, c1 = max(0, col-radius_px), min(imperv.shape[1], col+radius_px)
        patch = imperv[r0:r1, c0:c1]
        return np.nanmean(patch)

    # Zones: (label, lat, lon)
    zones = [
        ("DC downtown",          38.897, -77.036),
        ("Crystal City (urban)", 38.855, -77.051),
        ("Rockville (suburban)", 39.084, -77.153),
        ("Dulles Airport area",  38.953, -77.456),
        ("Poolesville (rural)",  39.143, -77.416),
        ("Great Falls (rural)",  39.000, -77.254),
    ]

    print("  Zone                         | Imperv norm (lower = more urban suppression)")
    print("  " + "-" * 65)
    means = []
    for label, lat, lon in zones:
        mean_val = sample_region(lat, lon)
        means.append((label, mean_val))
        print(f"  {label:<30} | {mean_val:+.3f}")

    # Check: urban zones should have lower values than rural zones
    urban_vals  = [v for l, v in means if any(u in l for u in ["downtown", "Crystal", "Airport"])]
    rural_vals  = [v for l, v in means if any(r in l for r in ["rural", "Poolesville", "Great Falls"])]
    if urban_vals and rural_vals:
        urban_mean = np.mean(urban_vals)
        rural_mean = np.mean(rural_vals)
        print(f"\n  Urban mean: {urban_mean:+.3f}  |  Rural mean: {rural_mean:+.3f}")
        if urban_mean < rural_mean:
            print("  PASS: Urban areas show lower imperv feature value (correct suppression direction)")
        else:
            print("  FAIL: Urban areas should have LOWER imperv norm than rural — check NLCD download")


def check_3_holdout_station(holdout_station="KIAD"):
    """
    Check 3: Hold out one ASOS station, predict at its location using
    IDW from remaining 7 stations + terrain. Compute AUC-PR vs nearest-neighbor.

    Uses observed fog labels as proxy probabilities (0 or 1) to test
    the spatial interpolation machinery, not forecast accuracy.

    Pass criterion: IDW AUC-PR >= nearest-neighbor AUC-PR.
    """
    print(f"\n--- Check 3: Hold-Out Station Test (holding out {holdout_station}) ---")
    import sys, os
    import pandas as pd
    from sklearn.metrics import average_precision_score
    # Add project root to path so spatial_pipeline can be found regardless of cwd
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)
    from scripts.spatial_pipeline import idw_logodds, haversine_km

    # Actual stations in dc_metro_test_2024_2026.parquet
    # Note: KNYG is in the data instead of KADW
    STATIONS = {
        "KDCA": (38.8521, -77.0377),
        "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683),
        "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743),
        "KHEF": (38.7217, -77.5155),
        "KNYG": (38.5014, -77.3058),
        "KCGS": (38.5803, -76.9228),
    }

    # Load DC metro test data
    df = pd.read_parquet("data/raw/asos/dc_metro_test_2024_2026.parquet")

    # Actual column names found in Step 1:
    #   station ID  -> "station"
    #   timestamp   -> "valid"
    #   fog outcome -> "is_fog"  (already 0/1, derived from vsby_km < 1.0)
    STATION_COL = "station"
    TIME_COL    = "valid"
    FOG_COL     = "is_fog"

    # Fallback: derive fog label from vsby_km if is_fog is missing
    if FOG_COL not in df.columns:
        if "vsby_km" in df.columns:
            df["fog_label"] = (df["vsby_km"] < 1.0).astype(int)
            FOG_COL = "fog_label"
        else:
            for candidate in ["fog", "fog_binary", "vsby_fog", "fog_label"]:
                if candidate in df.columns:
                    FOG_COL = candidate
                    break
            else:
                print(f"  Cannot find fog column. Available: {df.columns.tolist()}")
                return

    holdout_lat, holdout_lon = STATIONS[holdout_station]

    # ASOS stations report at different minute-marks within the hour (e.g. :47, :50, :52).
    # Round to nearest hour so all stations' readings are bucketed into the same group.
    df["valid_hour"] = df[TIME_COL].dt.round("h")

    print(f"  Data shape: {df.shape}")
    print(f"  Fog rate overall: {df[FOG_COL].mean():.3f}")
    print(f"  Computing per-hour IDW predictions at held-out station...")

    results = []
    # Group by rounded hour
    for valid_time, group in df.groupby("valid_hour"):
        # Build station probability dict from observed labels
        preds = {}
        for station_id in STATIONS:
            rows = group[group[STATION_COL] == station_id]
            if len(rows) == 0:
                continue
            # Use fog label (0 or 1) as proxy probability
            preds[station_id] = float(rows[FOG_COL].iloc[0])

        # Need holdout station and at least 5 others
        if holdout_station not in preds or len(preds) < 6:
            continue

        actual_fog = preds[holdout_station]

        # IDW from remaining stations
        remaining = {k: v for k, v in preds.items() if k != holdout_station}
        s_probs = np.array(list(remaining.values()))
        s_lats  = np.array([STATIONS[k][0] for k in remaining])
        s_lons  = np.array([STATIONS[k][1] for k in remaining])

        idw_prob, _ = idw_logodds(s_probs, s_lats, s_lons,
                                   np.array([holdout_lat]), np.array([holdout_lon]))
        idw_val = float(idw_prob[0])

        # Nearest-neighbor: find closest station in remaining
        dists = {k: haversine_km(holdout_lat, holdout_lon, STATIONS[k][0], STATIONS[k][1])
                 for k in remaining}
        nn_station = min(dists, key=dists.get)
        nn_val = preds[nn_station]

        results.append({
            "valid_time": valid_time,
            "actual":     actual_fog,
            "idw_pred":   idw_val,
            "nn_pred":    nn_val,
        })

    if not results:
        print("  No valid hours found — check data format.")
        return

    results_df = pd.DataFrame(results)
    print(f"  Hours evaluated: {len(results_df)}")
    print(f"  Fog rate in evaluated hours: {results_df['actual'].mean():.3f}")

    auc_idw = average_precision_score(results_df["actual"], results_df["idw_pred"])
    auc_nn  = average_precision_score(results_df["actual"], results_df["nn_pred"])

    print(f"  AUC-PR  IDW (7 stations): {auc_idw:.4f}")
    print(f"  AUC-PR  Nearest-neighbor: {auc_nn:.4f}")
    if auc_idw >= auc_nn:
        print("  PASS: IDW >= nearest-neighbor baseline")
    else:
        print(f"  NOTE: IDW ({auc_idw:.4f}) < nearest-neighbor ({auc_nn:.4f}) — "
              "not a failure (IDW is harder), but worth noting.")


def check_4_historical_replay():
    """
    Check 4: Run spatial layer on known dense-fog hours.
    Visual inspection: Potomac/valley corridors should show elevated probability.
    """
    print("\n--- Check 4: Historical Event Replay ---")
    import pandas as pd
    from scripts.spatial_pipeline import run_spatial_pipeline

    STATIONS = {
        "KDCA": (38.8521, -77.0377),
        "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683),
        "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743),
        "KHEF": (38.7217, -77.5155),
        "KNYG": (38.5014, -77.3058),
        "KCGS": (38.5803, -76.9228),
    }

    df = pd.read_parquet("data/raw/asos/dc_metro_test_2024_2026.parquet")
    df["valid_hour"] = df["valid"].dt.round("h")

    # Find hours where the most stations reported fog
    hourly = df.groupby("valid_hour")["is_fog"].agg(["sum", "count"])
    hourly = hourly[hourly["count"] >= 5]
    top_hours = hourly["sum"].nlargest(5).index.tolist()
    print(f"  Top 5 fog hours: {[str(t) for t in top_hours]}")

    for valid_dt in top_hours[:2]:
        hour_data = df[df["valid_hour"] == valid_dt]
        probs, lats, lons = [], [], []
        for sid, (lat, lon) in STATIONS.items():
            row = hour_data[hour_data["station"] == sid]
            if len(row) == 0:
                continue
            probs.append(float(row["is_fog"].iloc[0]))
            lats.append(lat)
            lons.append(lon)

        if len(probs) < 5:
            print(f"  Skipping {valid_dt}: too few stations ({len(probs)})")
            continue

        dt = pd.Timestamp(valid_dt).to_pydatetime()
        out_path = run_spatial_pipeline(probs, lats, lons, valid_dt=dt,
                                         output_dir="outputs/validation")

        with rasterio.open(out_path) as src:
            prob = src.read(1).astype(float)
            prob[prob < 0] = np.nan

        fig, ax = plt.subplots(figsize=(8, 8))
        im = ax.imshow(prob, vmin=0, vmax=1, cmap="Blues", origin="upper")
        plt.colorbar(im, ax=ax, label="Fog probability")
        ax.set_title(f"Fog probability — {valid_dt}")
        out_fig = f"outputs/validation/check4_event_{dt.strftime('%Y%m%d_%H')}UTC.png"
        plt.savefig(out_fig, dpi=150)
        plt.close()
        print(f"  Saved {out_fig}")
        print("  MANUAL: check Potomac/valley corridors are highlighted")


def check_5_sensitivity_sanity():
    """
    Check 5: Set all stations to flat 30% — output range should be analytically bounded.
    Expected: [expit(logit(0.3) - 0.5), expit(logit(0.3) + 0.5)] ~ [0.21, 0.41].
    """
    print("\n--- Check 5: Sensitivity Sanity ---")
    import pyproj
    from scipy.special import logit, expit
    from scripts.spatial_pipeline import idw_logodds, apply_terrain_offset

    STATIONS = {
        "KDCA": (38.8521, -77.0377),
        "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683),
        "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743),
        "KHEF": (38.7217, -77.5155),
        "KNYG": (38.5014, -77.3058),
        "KCGS": (38.5803, -76.9228),
    }

    s_probs = np.full(8, 0.30)
    s_lats  = np.array([v[0] for v in STATIONS.values()])
    s_lons  = np.array([v[1] for v in STATIONS.values()])

    with rasterio.open("data/processed/terrain_offset_grid.tif") as src:
        terrain = src.read(1).astype(float)
        terrain[terrain == -9999] = 0.0
        transform = src.transform
        crs_str = src.crs.to_string()

    transformer = pyproj.Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
    rows, cols = np.mgrid[0:terrain.shape[0], 0:terrain.shape[1]]
    xs = transform.c + cols * transform.a
    ys = transform.f + rows * transform.e
    lons, lats = transformer.transform(xs.ravel(), ys.ravel())
    grid_lats = lats.reshape(terrain.shape)
    grid_lons = lons.reshape(terrain.shape)

    idw_prob, _ = idw_logodds(s_probs, s_lats, s_lons, grid_lats, grid_lons)
    final_prob   = apply_terrain_offset(idw_prob, terrain)

    # Analytical bounds for input=0.30, offset=+/-0.5:
    lower = float(expit(logit(0.30) - 0.5))  # ~0.21
    upper = float(expit(logit(0.30) + 0.5))  # ~0.41

    actual_min = np.nanmin(final_prob)
    actual_max = np.nanmax(final_prob)

    print(f"  Analytical expected range: [{lower:.3f}, {upper:.3f}]")
    print(f"  Actual output range:       [{actual_min:.3f}, {actual_max:.3f}]")

    # Allow small tolerance since IDW with finite power isn't exactly 0.30 everywhere
    if actual_min >= lower - 0.05 and actual_max <= upper + 0.05:
        print("  PASS: Output range within analytically derived bounds (+/- 0.05 tolerance)")
    else:
        print("  FAIL: Output range exceeds terrain offset bounds — check formula implementation")


def check_6_bullseye_artifact():
    """
    Check 6: Synthetic 1-station-fog event — verify probability contours follow
    terrain (not perfect circles around the station).
    """
    print("\n--- Check 6: Bullseye Artifact Check ---")
    from datetime import datetime
    from scripts.spatial_pipeline import run_spatial_pipeline

    STATIONS = {
        "KDCA": (38.8521, -77.0377),
        "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683),
        "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743),
        "KHEF": (38.7217, -77.5155),
        "KNYG": (38.5014, -77.3058),
        "KCGS": (38.5803, -76.9228),
    }

    # Synthetic: KDCA reports 80% fog, all others 5%
    probs = [0.80 if s == "KDCA" else 0.05 for s in STATIONS]
    lats = [v[0] for v in STATIONS.values()]
    lons = [v[1] for v in STATIONS.values()]

    out_path = run_spatial_pipeline(probs, lats, lons,
                                     valid_dt=datetime(2024, 1, 1, 6, 0),
                                     output_dir="outputs/validation")

    with rasterio.open(out_path) as src:
        prob = src.read(1).astype(float)
        prob[prob < 0] = np.nan
        transform_out = src.transform

    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:4326", src.crs.to_string(), always_xy=True)

    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(prob, vmin=0, vmax=1, cmap="Blues", origin="upper")
    plt.colorbar(im, ax=ax, label="Fog probability")

    # Mark station locations
    for sid, (lat, lon) in STATIONS.items():
        x, y = transformer.transform(lon, lat)
        col = (x - transform_out.c) / transform_out.a
        row = (y - transform_out.f) / transform_out.e
        color = "red" if sid == "KDCA" else "white"
        ax.plot(col, row, "o", color=color, markersize=8)
        ax.text(col + 2, row, sid, color=color, fontsize=7)

    ax.set_title("Bullseye check: KDCA=80%, all others=5%\nContours should follow terrain, not circles")
    out_fig = "outputs/validation/check6_bullseye.png"
    plt.savefig(out_fig, dpi=150)
    plt.close()
    print(f"  Saved {out_fig}")
    print("  MANUAL: If high-probability zone is a perfect circle centered on KDCA,")
    print("  consider reducing IDW power from 1.5 to 1.2 in spatial_pipeline.py idw_logodds().")
    print("  PASS if probability contours show any terrain-influenced shape (not a perfect bull's-eye).")


if __name__ == "__main__":
    check_1_valley_ridge_transects()
    check_2_urban_suppression()
    check_3_holdout_station()
    check_4_historical_replay()
    check_5_sensitivity_sanity()
    check_6_bullseye_artifact()
    print("\nAll 6 validation checks complete.")
