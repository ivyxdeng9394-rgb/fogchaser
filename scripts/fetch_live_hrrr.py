"""
Fetch HRRR forecast variables for DC metro stations for one forecast hour.
"""
import os
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


def extract_station_values(ds: xr.Dataset, station_coords: dict) -> pd.DataFrame:
    """
    Sample the xarray Dataset at each station's nearest HRRR grid point.

    Uses scaled Euclidean distance (accounts for lat/lon degree asymmetry at 39°N):
      1 degree lat ≈ 111 km, 1 degree lon ≈ 77 km at 39°N
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

    fxx=1 is the first true forecast hour (fxx=0 is the analysis field).
    Returns empty DataFrame on any failure — caller handles gracefully.

    save_dir defaults to HRRR_CACHE_DIR env var or /tmp/hrrr_cache.
    """
    if save_dir is None:
        save_dir = os.environ.get("HRRR_CACHE_DIR", "/tmp/hrrr_cache")

    for attempt in range(3):
        try:
            H = Herbie(run_time, model="hrrr", product="sfc", fxx=fxx,
                       save_dir=save_dir)
            result = H.xarray(HRRR_SEARCH)

            if isinstance(result, list):
                ds = xr.merge(result, compat="override", join="override")
            else:
                ds = result

            # Ensure valid_time is timezone-aware (MEMORY.md gotcha)
            if "valid_time" in ds and hasattr(ds["valid_time"], "dt"):
                if ds["valid_time"].dt.tz is None:
                    ds["valid_time"] = ds["valid_time"].dt.tz_localize("UTC")

            return extract_station_values(ds, station_coords)

        except (FileNotFoundError, ValueError) as e:
            print(f"  WARNING: HRRR fxx={fxx} not available yet (attempt {attempt+1}/3): {e}")
            if attempt < 2:
                _time.sleep(30)
        except Exception as e:
            print(f"  WARNING: HRRR fetch failed (fxx={fxx}): {e}")
            return pd.DataFrame()

    print(f"  WARNING: HRRR fxx={fxx} unavailable after 3 attempts — skipping")
    return pd.DataFrame()
