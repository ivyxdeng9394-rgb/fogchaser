"""
Generate mock forecast data for local UI testing.
Creates 12 synthetic GeoTIFFs + manifest.json in app/data/.

Run: python3 scripts/generate_mock_forecast.py
"""
import json, os
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from datetime import datetime, timezone, timedelta

OUT_DIR = "app/data"
os.makedirs(OUT_DIR, exist_ok=True)

# DC metro bounding box (lat/lon, EPSG:4326)
WEST, EAST = -77.7, -76.8
SOUTH, NORTH = 38.5, 39.4
WIDTH, HEIGHT = 200, 180   # ~500m resolution equivalent

transform = from_bounds(WEST, SOUTH, EAST, NORTH, WIDTH, HEIGHT)

# --- Synthetic fog probability field ---
# Simulate realistic patterns: river valleys get higher fog,
# urban DC core gets lower, suburban Maryland/VA moderate.
rng = np.random.default_rng(42)
y_idx, x_idx = np.mgrid[0:HEIGHT, 0:WIDTH]
lats = NORTH - y_idx * (NORTH - SOUTH) / HEIGHT
lons = WEST  + x_idx * (EAST  - WEST)  / WIDTH

# Potomac river corridor: higher fog (around lat 38.85–39.05, lon -77.4 to -77.0)
river_fog = np.exp(-((lats - 38.9)**2 / 0.01 + (lons + 77.2)**2 / 0.05)) * 0.18

# Shenandoah/western valleys: high fog (west of DC)
valley_fog = np.exp(-((lats - 39.1)**2 / 0.02 + (lons + 77.55)**2 / 0.02)) * 0.22

# Urban DC core: lower fog (heat island, around 38.9 lat, -77.0 lon)
urban_suppress = np.exp(-((lats - 38.9)**2 / 0.004 + (lons + 77.0)**2 / 0.004)) * 0.12

# Northern Virginia rolling terrain: moderate
nova_fog = np.exp(-((lats - 38.75)**2 / 0.02 + (lons + 77.3)**2 / 0.04)) * 0.14

# Base field + noise — raise floor so mock data shows interesting fog across the grid
base = 0.06 + river_fog + valley_fog + nova_fog - urban_suppress
base = np.clip(base, 0.02, 0.252)
base += rng.normal(0, 0.01, base.shape)
base = np.clip(base, 0.02, 0.252).astype("float32")

profile = {
    "driver": "GTiff",
    "dtype": "float32",
    "width": WIDTH,
    "height": HEIGHT,
    "count": 1,
    "crs": "EPSG:4326",
    "transform": transform,
    "nodata": -9999.0,
}

# Start forecast from the next full hour so labels are always in the future
now = datetime.now(timezone.utc)
start = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

hours_meta = []
for fxx in range(0, 12):
    valid_dt = start + timedelta(hours=fxx)

    # For mock data: force interesting spread across the 12 hours regardless of time of day
    # fxx 1–4: building fog overnight (moderate→high)
    # fxx 5–8: peak fog (high→very high)
    # fxx 9–12: morning burn-off (high→low)
    intensities = [0.7, 0.85, 1.0, 1.15, 1.3, 1.4, 1.35, 1.2, 0.9, 0.6, 0.35, 0.2]
    intensity = intensities[fxx] + rng.uniform(-0.05, 0.05)

    arr = np.clip(base * intensity, 0.008, 0.252).astype("float32")

    fname = f"mock_fxx{fxx+1:02d}.tif"
    fpath = os.path.join(OUT_DIR, fname)
    with rasterio.open(fpath, "w", **profile) as dst:
        dst.write(arr, 1)

    avg_prob = float(arr.mean())
    score = (1 if avg_prob < 0.08 else
             2 if avg_prob < 0.13 else
             3 if avg_prob < 0.17 else
             4 if avg_prob < 0.22 else 5)
    label = {1:"Low",2:"Moderate",3:"High",4:"Very High",5:"Extreme"}[score]

    # Mock atmospheric conditions — higher fog hours get more saturated conditions
    foggy_intensity = min(1.0, (intensity - 0.2) / 1.2)  # normalize 0-1
    t_td = max(0.5, 12 - foggy_intensity * 11 + rng.uniform(-0.5, 0.5))
    wind = max(0.5, 18 - foggy_intensity * 16 + rng.uniform(-1, 1))
    hpbl = max(60, 900 - foggy_intensity * 820 + rng.uniform(-30, 30))
    cldbase = max(150, 2800 - foggy_intensity * 2600 + rng.uniform(-100, 100))
    rh = min(99, 55 + foggy_intensity * 42 + rng.uniform(-2, 2))

    hours_meta.append({
        "fxx":          fxx,
        "valid_utc":    valid_dt.strftime("%Y-%m-%dT%H:00:00Z"),
        "label":        label,
        "relative_risk": round(avg_prob / 0.054, 1),
        "avg_prob":     round(avg_prob, 3),
        "approx_asos":  fxx >= 1,
        "url":          f"data/{fname}",
        "conditions": {
            "t_td_spread_f":  round(float(t_td), 1),
            "wind_speed_mph": round(float(wind), 1),
            "hpbl_m":         round(float(hpbl)),
            "hgt_cldbase_m":  round(float(cldbase)),
            "rh_pct":         round(float(rh), 1),
        },
    })
    print(f"  fxx={fxx+1:02d}  {valid_dt.strftime('%H:00Z')}  avg={avg_prob:.3f}  {label}")

manifest = {
    "run_utc":       start.strftime("%Y-%m-%dT%H:00:00Z"),
    "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "hours":         hours_meta,
}
with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
    json.dump(manifest, f, indent=2)

print(f"\nWrote {len(hours_meta)} mock hours to {OUT_DIR}/manifest.json")
print("Now open http://localhost:8080 to preview the UI with mock data.")
