"""
Fetch HRRR forecast variables for DC metro stations for one forecast hour.

Uses Herbie only for downloading the GRIB2 subset file, then reads values
via wgrib2 subprocess calls — avoiding cfgrib / eccodeslib segfaults on Linux.
wgrib2 must be installed: apt-get install -y wgrib2
"""
import os
import re
import subprocess
import time as _time
import numpy as np
import pandas as pd
import xarray as xr
from datetime import datetime
from herbie import Herbie

DC_STATION_COORDS = {
    "KBWI": (39.1733, -76.6841),
    "KCGS": (38.9806, -76.9223),
    "KDCA": (38.8472, -77.0345),
    "KFDK": (39.4176, -77.3743),
    "KGAI": (39.1683, -77.1660),
    "KHEF": (38.7214, -77.5154),
    "KIAD": (38.9348, -77.4473),
    "KNYG": (38.5017, -77.3053),
}

REQUIRED_COLS = ["station", "hpbl_m", "tcdc_bl_pct", "dpt2m_k", "tmp2m_k",
                 "rh2m_pct", "hgt_cldbase_m", "u10_ms", "v10_ms"]

# ~38% of hours have no cloud — fill with 10km sentinel (not an error)
_NO_CLOUD_M = 10_000.0

HRRR_SEARCH = (
    ":(TMP|DPT|RH):2 m above ground|"
    ":UGRD:10 m above ground|"
    ":VGRD:10 m above ground|"
    ":HPBL:|"
    ":TCDC:boundary layer cloud layer|"
    ":HGT:cloud base"
)

# Real Herbie variable names confirmed via _herbie_var_check.py (MEMORY.md)
RENAME_MAP = {
    "t2m": "tmp2m_k",       # 2m temperature (K)
    "d2m": "dpt2m_k",       # 2m dewpoint (K)
    "r2":  "rh2m_pct",      # 2m relative humidity (%)
    "u10": "u10_ms",         # 10m U-wind (m/s)
    "v10": "v10_ms",         # 10m V-wind (m/s)
    "blh": "hpbl_m",         # planetary boundary layer height (m)
    "tcc": "tcdc_bl_pct",    # total cloud cover boundary layer (%)
    "gh":  "hgt_cldbase_m",  # cloud base height (m) — ~38% NaN = no cloud
}

# Maps wgrib2 match patterns → output column names
# Order matters for parsing: more specific patterns first to avoid ambiguity
_WGRIB2_VARS = [
    ("TMP:2 m above ground",           "tmp2m_k"),
    ("DPT:2 m above ground",           "dpt2m_k"),
    ("RH:2 m above ground",            "rh2m_pct"),
    ("UGRD:10 m above ground",         "u10_ms"),
    ("VGRD:10 m above ground",         "v10_ms"),
    ("HPBL:surface",                   "hpbl_m"),
    ("TCDC:boundary layer cloud layer","tcdc_bl_pct"),
    ("HGT:cloud base",                 "hgt_cldbase_m"),
]


def _wgrib2_extract_all(grib_path: str, station_coords: dict) -> pd.DataFrame:
    """
    Extract all 8 HRRR variables at each station lat/lon using wgrib2.

    For each variable, runs one wgrib2 call that queries all station points
    in a single pass using repeated -lon flags.  Falls back to one-station-
    at-a-time if the multi-lon form is not supported.

    wgrib2 -lon expects 0-360 longitude (HRRR native).
    Output line format: "N:OFFSET:lon=LON,lat=LAT,val=VALUE"
    """
    stations = list(station_coords.keys())
    lats = [station_coords[s][0] for s in stations]
    lons = [station_coords[s][1] for s in stations]
    lons360 = [lon + 360 if lon < 0 else lon for lon in lons]

    # Initialise result dict: station → {col: value}
    result = {s: {} for s in stations}

    for match_pattern, col_name in _WGRIB2_VARS:
        # Build a single wgrib2 call with one -lon per station
        cmd = ["wgrib2", grib_path, "-match", match_pattern]
        for lon360, lat in zip(lons360, lats):
            cmd += ["-lon", str(lon360), str(lat)]

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )
            output = proc.stdout
        except subprocess.TimeoutExpired:
            print(f"  WARNING: wgrib2 timed out for {col_name}")
            output = ""
        except FileNotFoundError:
            raise RuntimeError(
                "wgrib2 not found — install with: apt-get install -y wgrib2"
            )

        # Parse output lines that contain val=
        # Each -lon produces one output line per matching GRIB record.
        # When multiple records match (shouldn't happen here), we take the first.
        # Lines look like: "1:0:lon=283.316,lat=38.847,val=288.5"
        val_pattern = re.compile(
            r"lon=([0-9.]+),lat=([0-9.]+),val=([0-9eE+.\-]+)"
        )
        # Collect (lon360, lat, val) tuples from output
        parsed = []
        for line in output.splitlines():
            m = val_pattern.search(line)
            if m:
                parsed.append((float(m.group(1)), float(m.group(2)), float(m.group(3))))

        # Match parsed values back to stations by closest (lon360, lat) pair
        for s_idx, station in enumerate(stations):
            s_lon360 = lons360[s_idx]
            s_lat = lats[s_idx]
            best_val = np.nan
            best_dist = float("inf")
            for p_lon, p_lat, p_val in parsed:
                dist = (p_lon - s_lon360) ** 2 + (p_lat - s_lat) ** 2
                if dist < best_dist:
                    best_dist = dist
                    best_val = p_val
            result[station][col_name] = best_val

    # Build DataFrame
    rows = []
    for station in stations:
        row = {"station": station}
        for _, col_name in _WGRIB2_VARS:
            row[col_name] = result[station].get(col_name, np.nan)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["hgt_cldbase_m"] = df["hgt_cldbase_m"].fillna(_NO_CLOUD_M)

    # Ensure all required columns are present (fill missing with NaN)
    for col in REQUIRED_COLS:
        if col not in df.columns:
            df[col] = np.nan

    return df[REQUIRED_COLS].copy()


def extract_station_values(ds: xr.Dataset, station_coords: dict) -> pd.DataFrame:
    """
    Sample the xarray Dataset at each station's nearest HRRR grid point.

    Uses scaled Euclidean distance (accounts for lat/lon degree asymmetry at 39°N):
      1 degree lat ≈ 111 km, 1 degree lon ≈ 77 km at 39°N

    NOTE: This function is retained for tests and legacy use. The main
    fetch_hrrr_forecast_hour function now uses wgrib2 instead of cfgrib/xarray.
    """
    grid_lats = ds["latitude"].values.ravel()
    grid_lons = ds["longitude"].values.ravel()  # already 0-360 in HRRR

    rows = []
    for station, (lat, lon) in station_coords.items():
        lon360 = lon + 360 if lon < 0 else lon
        dist = np.sqrt(((grid_lats - lat) * 111) ** 2 +
                       ((grid_lons - lon360) * 77) ** 2)
        idx = int(np.argmin(dist))

        row = {"station": station}
        for short_name, col_name in RENAME_MAP.items():
            if short_name in ds.data_vars:
                row[col_name] = float(ds[short_name].values.ravel()[idx])
            else:
                row[col_name] = np.nan

        rows.append(row)

    df = pd.DataFrame(rows)
    df["hgt_cldbase_m"] = df["hgt_cldbase_m"].fillna(_NO_CLOUD_M)
    return df[REQUIRED_COLS].copy()


def fetch_hrrr_forecast_hour(run_time: datetime, fxx: int,
                              station_coords: dict = DC_STATION_COORDS,
                              save_dir: str = None) -> pd.DataFrame:
    """
    Download one HRRR forecast hour and extract station values.

    Uses Herbie to download the GRIB2 subset, then wgrib2 to read values —
    avoids cfgrib / eccodeslib segfaults on Linux.

    fxx=1 is the first true forecast hour (fxx=0 is the analysis field).
    Returns empty DataFrame on any failure — caller handles gracefully.

    save_dir defaults to HRRR_CACHE_DIR env var or /tmp/hrrr_cache.
    """
    if save_dir is None:
        save_dir = os.environ.get("HRRR_CACHE_DIR", "/tmp/hrrr_cache")

    # Herbie expects a tz-naive UTC datetime — strip tzinfo if present
    run_time_naive = run_time.replace(tzinfo=None) if run_time.tzinfo else run_time

    for attempt in range(3):
        try:
            H = Herbie(run_time_naive, model="hrrr", product="sfc", fxx=fxx,
                       save_dir=save_dir)

            # Download the GRIB2 subset — returns path to local file, no cfgrib
            grib_path = H.download(HRRR_SEARCH)

            if grib_path is None or not os.path.exists(str(grib_path)):
                raise FileNotFoundError(
                    f"Herbie download returned no file for fxx={fxx}"
                )

            return _wgrib2_extract_all(str(grib_path), station_coords)

        except (FileNotFoundError, ValueError) as e:
            print(f"  WARNING: HRRR fxx={fxx} not available yet (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                _time.sleep(30)
        except Exception as e:
            print(f"  WARNING: HRRR fetch failed (fxx={fxx}): {e}")
            return pd.DataFrame()

    print(f"  WARNING: HRRR fxx={fxx} unavailable after 3 attempts — skipping")
    return pd.DataFrame()
