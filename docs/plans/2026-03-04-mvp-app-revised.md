# Fogchaser MVP App — Revised Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **After writing each file:** Run the `simplify` skill on the newly written code before moving to the next step. This catches over-engineering, redundancy, and clarity issues while the code is fresh.
>
> **After every batch of tasks (3 tasks per batch):** Run a parallel review cycle before continuing:
> 1. **Verifier agent** — checks implementation matches this plan spec exactly; runs all tests; reports pass/fail per item
> 2. **Hole-poker agent** — looks for bugs, production failure modes, and gaps the tests won't catch; classifies findings as BLOCKER / BUG / WARN / NITPICK
> 3. **Accept/decline** — the main agent decides what to fix now vs. defer vs. decline, with reasoning; flags Ivy for anything that requires a decision
> 4. Fix accepted issues, re-run full test suite, confirm green before proceeding to the next batch

**Goal:** Build a live fog prediction web app — every 6 hours, fetch real HRRR + ASOS data, run the XGBoost model, generate fog probability maps for the next 12 hours, and serve them on an interactive Leaflet map so a photographer can decide whether to get up tomorrow morning.

**Architecture:** A Python pipeline fetches live HRRR (via Herbie) and ASOS (via IEM API), runs inference for forecast hours fxx=1–12, and uploads GeoTIFF fog maps to Cloudflare R2 (free). A manifest.json pointing to R2 URLs is committed to the repo. GitHub Actions runs this every 6 hours. Vercel auto-deploys, serving the static frontend. The frontend loads GeoTIFFs from R2 and renders them on a Leaflet map.

**Tech Stack:** Python (Herbie, xgboost, rasterio, requests, boto3), Leaflet.js + georaster-layer-for-leaflet + geoblaze (CDN, no build step), GitHub Actions (free), Cloudflare R2 (free tier, GeoTIFF storage), Vercel (free static hosting)

**Why R2 instead of committing TIFFs to git:** Each run generates 12 GeoTIFFs (~720KB each = ~8.6MB/run). At 4 runs/day, git objects grow ~34MB/day — the repo hits GitHub's limit within weeks. R2 stores files outside git history. Only manifest.json (tiny JSON) gets committed.

---

## Revision notes (vs 2026-03-03-mvp-app.md)

Changes made based on technical + PM review:
- **Cut:** Weather JSON + fog bullets system (Task 5 in old plan) — show label + percentage only on click
- **Cut:** TDD "run to verify it fails" ceremony — tests still exist, just write + run without the ritual
- **Fixed:** ASOS lag features for forecast hours fxx≥1 use HRRR-derived T-Td as substitute
- **Fixed:** `latest_hrrr_run()` day-boundary bug; fxx loop starts at 1 (not 0)
- **Fixed:** IEM multi-station parameter encoding (list of tuples, not dict)
- **Fixed:** Model/calibrator loaded once per run, not inside the per-hour loop
- **Fixed:** GitHub Actions concurrency guard + pull-before-push
- **Fixed:** GeoTIFFs go to Cloudflare R2, not git
- **Added:** Herbie variable verification step before Task 4
- **Added:** "Last updated" timestamp in app header
- **Added:** Winter limitation disclaimer visible in UI
- **Fixed:** Summary badge averages overnight hours (23–07 UTC) only
- **Fixed:** Color ramp validated against actual model output range (0.008–0.252)
- **Fixed:** requirements.txt uses pip freeze, not guessed versions

---

## Context — What Already Exists

Read before touching anything:
- `CLAUDE.md` — spatial layer gotchas (TPI sign, IDW power 1.2, calibrated probs only)
- `MEMORY.md` — HRRR technical notes (0-360 longitude, Herbie merge, NaN fills)
- `scripts/run_inference_hour.py` — end-to-end inference for one hour (reads from parquet)
- `scripts/spatial_pipeline.py` — IDW + terrain offset → GeoTIFF
- `models/calibrator_platt_v2.pkl` — dict: calibrator, best_threshold (0.17), features (18 cols), fill_medians
- `models/xgb_asos_hrrr_full_v1.json` — trained XGBoost model (6yr full, 2018–2023; AUC-PR 0.357)
- `models/enhanced_asos_station_list.json` — station CategoricalDtype list
- `data/raw/hrrr/hrrr_test_dc_2024.parquet` — 8 DC stations, columns: station, hpbl_m, tcdc_bl_pct, dpt2m_k, tmp2m_k, rh2m_pct, hgt_cldbase_m, u10_ms, v10_ms
- `data/raw/asos/dc_metro_test_2024_2026.parquet` — columns: station, valid, elevation, t_td_spread, wind_speed_mph, drct, etc.

**8 DC stations:** KBWI, KCGS, KDCA, KFDK, KGAI, KHEF, KIAD, KNYG

---

## Phase 1 — Data Pipeline

### Task 1: Create requirements.txt and app/ skeleton

**Files:**
- Create: `requirements.txt`
- Create: `app/index.html` (placeholder)
- Create: `app/data/.gitkeep`
- Create/update: `.gitignore`

**Step 1: Create requirements.txt with minimum version pins**

List direct dependencies manually — **do not use `pip freeze`** (it captures your entire local environment and will fail on the GitHub Actions runner):

```
xgboost>=1.7
herbie-data>=2024.8
boto3>=1.28
pandas>=2.0
numpy>=1.24
rasterio>=1.3
pyproj>=3.5
scipy>=1.11
requests>=2.31
scikit-learn>=1.3
pytest>=7.4
```

**Important: `eccodes` cannot be installed via pip.** It is required by Herbie but must be installed as a system package. Add this step to the GitHub Actions workflow (Task 8):

```yaml
- name: Install eccodes
  run: sudo apt-get install -y libeccodes-dev
```

**Step 2: Create app/ structure**

```bash
mkdir -p app/data
touch app/data/.gitkeep
echo '<!DOCTYPE html><html><body><p>Loading...</p></body></html>' > app/index.html
```

**Step 3: Update .gitignore — prevent TIFFs and HRRR cache from entering git**

Add these lines (create .gitignore if it doesn't exist):

```
# HRRR downloaded files (not for git)
*.grib2
/tmp/hrrr_live/
/tmp/hrrr_cache/
~/data/hrrr/

# All GeoTIFFs — never commit binary rasters
*.tif
*.tiff

# Large training/test parquet files
data/raw/hrrr/*.parquet

# Python
__pycache__/
*.pyc
.DS_Store
```

**Warning:** Without `*.tif` in `.gitignore`, your first pipeline test run will stage GeoTIFF files and you may accidentally commit ~8MB of binary data to git. Verify with `git status` after a local test run that no `.tif` files appear as untracked.

**Step 4: Verify**

```bash
python3 -m pytest tests/spatial/ -v
# Expected: all 16 existing spatial tests PASS — nothing broken
```

---

### Task 2: Verify Herbie variable names against real HRRR data

**Do this before writing any HRRR fetching code.** The plan cannot assume Herbie's xarray variable names — they depend on GRIB2 eccodes mappings that vary by HRRR version.

**Files:**
- No files written — this is a discovery step
- Create: `scripts/_herbie_var_check.py` (throwaway script)

**Step 1: Write the verification script**

```python
# scripts/_herbie_var_check.py
"""
Run this once to discover real Herbie variable names for HRRR.
Print results and record them before writing fetch_live_hrrr.py.
"""
from herbie import Herbie
import xarray as xr
from datetime import datetime, timezone

# Use a recent date where HRRR is known to be available
# (adjust if this specific run isn't on AWS anymore)
run_time = datetime(2024, 12, 10, 6, tzinfo=timezone.utc)

SEARCH = (
    ":(TMP|DPT|RH):2 m above ground|"
    ":UGRD:10 m above ground|"
    ":VGRD:10 m above ground|"
    ":HPBL:|"
    ":TCDC:boundary layer cloud layer|"
    ":HGT:cloud base"
)

print(f"Downloading HRRR {run_time} fxx=1...")
H = Herbie(run_time, model="hrrr", product="sfc", fxx=1,
           save_dir="/tmp/hrrr_live")

result = H.xarray(SEARCH)

if isinstance(result, list):
    print(f"  Herbie returned list of {len(result)} datasets — merging")
    ds = xr.merge(result, compat="override", join="override")
else:
    ds = result

print("\nVariables in merged dataset:")
for var in sorted(ds.data_vars):
    shape = ds[var].shape
    sample = float(ds[var].values.ravel()[0])
    print(f"  {var:30s}  shape={shape}  sample={sample:.3f}")

print("\nDimensions:", dict(ds.dims))
print("\nCoordinates:", list(ds.coords))
```

**Step 2: Run it and record the output**

```bash
python3 scripts/_herbie_var_check.py
```

**Step 3: Record the actual variable names**

After merging the Herbie result with `xr.merge()`, print `list(ds.data_vars)` — these are the exact names to use as keys in `RENAME_MAP`. Use these xarray variable names, **not** the GRIB `shortName` (they are often different). The output tells you exactly what names to use in `RENAME_MAP` in Task 4. Common patterns:
- TMP 2m might be `t2m` or `TMP_2maboveground` depending on HRRR version
- Record whatever appears and use those exact strings

**Step 4: Verify the HRRR search string matches**

If `:TCDC:boundary layer cloud layer` returns no results, try `:TCDC:` alone and inspect what layers are available.

---

### Task 3: Write live ASOS fetcher

**Files:**
- Create: `scripts/fetch_live_asos.py`
- Create: `tests/pipeline/__init__.py`
- Create: `tests/pipeline/test_asos_fetcher.py`

**Step 1: Write tests**

```python
# tests/pipeline/test_asos_fetcher.py
import pandas as pd
import pytest
from unittest.mock import patch, Mock
from scripts.fetch_live_asos import fetch_asos_latest

# IEM returns CSV with a comment header line starting with #
MOCK_CSV = """# Iowa Environmental Mesonet
station,valid,tmpf,dwpf,sknt,drct,vsby,lon,lat,elev
KBWI,2024-12-10 08:54,34.0,32.0,4,220,0.25,-76.6841,39.1733,42.0
KDCA,2024-12-10 08:52,36.0,35.0,3,200,0.12,-77.0345,38.8472,20.0
KIAD,2024-12-10 08:52,33.0,32.5,2,180,0.12,-77.4473,38.9348,98.0
"""


def test_returns_required_columns():
    """fetch_asos_latest should return a DataFrame with required lag feature columns."""
    with patch("scripts.fetch_live_asos.requests.get") as mock_get:
        mock_get.return_value = Mock(status_code=200, text=MOCK_CSV)
        df = fetch_asos_latest(lookback_hours=2)
    required = {"station", "elevation", "t_td_spread_lag",
                "wind_speed_mph_lag", "drct_sin_lag", "drct_cos_lag"}
    assert required.issubset(set(df.columns))


def test_one_row_per_station():
    """Should return at most one row per station."""
    with patch("scripts.fetch_live_asos.requests.get") as mock_get:
        mock_get.return_value = Mock(status_code=200, text=MOCK_CSV)
        df = fetch_asos_latest(lookback_hours=2)
    assert df["station"].nunique() == len(df)


def test_t_td_spread_non_negative():
    """T-Td spread must be >= 0 (temp is always >= dewpoint)."""
    with patch("scripts.fetch_live_asos.requests.get") as mock_get:
        mock_get.return_value = Mock(status_code=200, text=MOCK_CSV)
        df = fetch_asos_latest(lookback_hours=2)
    assert (df["t_td_spread_lag"] >= 0).all()


def test_returns_empty_on_api_failure():
    """Should return empty DataFrame (not raise) when API fails."""
    with patch("scripts.fetch_live_asos.requests.get") as mock_get:
        mock_get.side_effect = Exception("connection refused")
        df = fetch_asos_latest(lookback_hours=2)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_returns_empty_on_iem_200_with_no_data():
    """IEM returns HTTP 200 with empty body when stations have no recent obs.
    This is the most common real-world failure mode — must not be treated as success."""
    empty_csv = "# Iowa Environmental Mesonet\nstation,valid,tmpf,dwpf,sknt,drct,vsby,lon,lat,elev\n"
    with patch("scripts.fetch_live_asos.requests.get") as mock_get:
        mock_get.return_value = Mock(status_code=200, text=empty_csv)
        df = fetch_asos_latest(lookback_hours=2)
    assert isinstance(df, pd.DataFrame)
    assert df.empty
```

**Step 2: Write scripts/fetch_live_asos.py**

**Lag feature definition:** The model was trained on `*_lag` features representing the observation *one hour prior* to fog onset. In live inference, treat the current ASOS observation (most recent report within the last 90 minutes) as the lag input. If no report exists within 90 minutes for a station, mark that station as unavailable for this run. Do not impute; do not use stale data older than 90 minutes.

Note the IEM multi-station fix: use a list of tuples for params, not a dict.

```python
"""
Fetch the most recent ASOS observations for DC metro stations from IEM.
"""
import numpy as np
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta
from io import StringIO

DC_STATIONS = ["KBWI", "KCGS", "KDCA", "KFDK", "KGAI", "KHEF", "KIAD", "KNYG"]
IEM_URL = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"


def fetch_asos_latest(lookback_hours: int = 2,
                      stations: list = DC_STATIONS) -> pd.DataFrame:
    """
    Fetch recent ASOS observations and return lag feature DataFrame.

    Returns empty DataFrame if request fails — caller handles gracefully.
    """
    now_utc = datetime.now(timezone.utc)
    start = now_utc - timedelta(hours=lookback_hours)

    # CRITICAL: IEM requires repeated station= params. requests handles a list
    # of tuples correctly: [("station","KBWI"), ("station","KDCA"), ...]
    params = [
        ("data",        "tmpf,dwpf,sknt,drct,vsby"),
        ("tz",          "UTC"),
        ("format",      "comma"),
        ("latlon",      "yes"),
        ("elev",        "yes"),
        ("report_type", "3"),
        ("year1",  start.year),   ("month1", start.month),
        ("day1",   start.day),    ("hour1",  start.hour),   ("minute1", 0),
        ("year2",  now_utc.year), ("month2", now_utc.month),
        ("day2",   now_utc.day),  ("hour2",  now_utc.hour), ("minute2", 59),
    ]
    for s in stations:
        params.append(("station", s))

    try:
        resp = requests.get(IEM_URL, params=params, timeout=30,
                            headers={"User-Agent": "fogchaser-forecast-bot/1.0 (personal project)"})
        resp.raise_for_status()
    except Exception as e:
        print(f"  WARNING: ASOS fetch failed: {e}")
        return pd.DataFrame()

    lines = [l for l in resp.text.splitlines() if not l.startswith("#")]
    if len(lines) < 2:
        print("  WARNING: ASOS response empty or header-only")
        return pd.DataFrame()

    # IEM returns HTTP 200 with empty data when stations have no recent obs.
    # Check for missing stations after parsing — do not treat a 0-station 200 as success.

    df = pd.read_csv(StringIO("\n".join(lines)))
    df.columns = df.columns.str.strip()
    df["valid"] = pd.to_datetime(df["valid"], utc=True, errors="coerce")
    df = df.dropna(subset=["valid"])

    # One row per station — most recent observation
    df = df.sort_values("valid").groupby("station").last().reset_index()

    # Check for missing stations — IEM may return partial results with HTTP 200
    returned = set(df["station"].tolist())
    missing = set(stations) - returned
    if missing:
        print(f"  WARNING: Missing stations from IEM: {sorted(missing)}")
    if df.empty:
        print("  WARNING: IEM returned 200 but no station data. Treating as failure.")
        return pd.DataFrame()

    # Compute lag features
    df["t_td_spread_lag"]   = (df["tmpf"] - df["dwpf"]).clip(lower=0)
    df["wind_speed_mph_lag"] = pd.to_numeric(df["sknt"], errors="coerce") * 1.15078
    drct_rad = np.radians(pd.to_numeric(df["drct"], errors="coerce").fillna(0))
    df["drct_sin_lag"] = np.sin(drct_rad)
    df["drct_cos_lag"] = np.cos(drct_rad)
    df["elevation"]    = pd.to_numeric(df["elev"], errors="coerce")

    return df[["station", "elevation", "t_td_spread_lag",
               "wind_speed_mph_lag", "drct_sin_lag", "drct_cos_lag"]].copy()
```

**Step 3: Run tests**

```bash
python3 -m pytest tests/pipeline/test_asos_fetcher.py -v
# Expected: PASS (4 tests)
```

---

### Task 4: Write live HRRR fetcher

**Use the actual variable names discovered in Task 2.** The `RENAME_MAP` below uses placeholder names — replace them with the real names from the Task 2 output before running.

**Files:**
- Create: `scripts/fetch_live_hrrr.py`
- Create: `tests/pipeline/test_hrrr_fetcher.py`

**Step 1: Write tests**

```python
# tests/pipeline/test_hrrr_fetcher.py
import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scripts.fetch_live_hrrr import extract_station_values, REQUIRED_COLS, DC_STATION_COORDS


def make_mock_ds():
    """Build a minimal mock xarray Dataset.
    IMPORTANT: keys here must match RENAME_MAP in fetch_live_hrrr.py — update both together.
    """
    coords = list(DC_STATION_COORDS.values())
    n = len(coords)
    lats = np.array([c[0] for c in coords])
    # Convert lons to 0-360 as HRRR does
    lons = np.array([c[1] + 360 if c[1] < 0 else c[1] for c in coords])

    return xr.Dataset({
        # Replace these keys with real Herbie variable names from Task 2
        "t2m":  xr.DataArray(np.full(n, 275.0), dims=["points"]),
        "d2m":  xr.DataArray(np.full(n, 274.0), dims=["points"]),
        "r2":   xr.DataArray(np.full(n, 95.0),  dims=["points"]),
        "u10":  xr.DataArray(np.full(n, 1.0),   dims=["points"]),
        "v10":  xr.DataArray(np.full(n, -0.5),  dims=["points"]),
        "blh":  xr.DataArray(np.full(n, 50.0),  dims=["points"]),
        "tcc":  xr.DataArray(np.full(n, 80.0),  dims=["points"]),
        "gh":   xr.DataArray(np.full(n, np.nan), dims=["points"]),
        "latitude":  xr.DataArray(lats, dims=["points"]),
        "longitude": xr.DataArray(lons, dims=["points"]),
    })


def test_required_columns_present():
    df = extract_station_values(make_mock_ds(), DC_STATION_COORDS)
    for col in REQUIRED_COLS:
        assert col in df.columns, f"Missing: {col}"


def test_cloud_base_nan_filled():
    """hgt_cldbase_m NaN (no cloud) must become 10000.0."""
    df = extract_station_values(make_mock_ds(), DC_STATION_COORDS)
    assert (df["hgt_cldbase_m"] == 10000.0).all()


def test_one_row_per_station():
    df = extract_station_values(make_mock_ds(), DC_STATION_COORDS)
    assert len(df) == len(DC_STATION_COORDS)
    assert df["station"].nunique() == len(DC_STATION_COORDS)


def test_returns_empty_on_exception():
    from scripts.fetch_live_hrrr import fetch_hrrr_forecast_hour
    from unittest.mock import patch
    from datetime import datetime, timezone
    with patch("scripts.fetch_live_hrrr.Herbie", side_effect=Exception("network")):
        df = fetch_hrrr_forecast_hour(datetime(2024, 12, 10, 6, tzinfo=timezone.utc), fxx=1)
    assert isinstance(df, pd.DataFrame)
    assert df.empty


def test_longitude_360_conversion():
    """CRITICAL: HRRR uses 0-360 longitude. Negative station lons must be converted.
    DCA is at -77.03 lon — must become 282.97, not -77.03, for nearest-grid-point search."""
    ds = make_mock_ds()
    # extract_station_values should internally convert -77.03 → 282.97
    # Verify by checking that a station with known negative lon returns a result (not NaN)
    df = extract_station_values(ds, {"KDCA": (38.8472, -77.0345)})
    assert len(df) == 1
    assert not df["tmp2m_k"].isna().any(), \
        "NaN result suggests longitude conversion failed — HRRR uses 0-360"
```

**Step 2: Write scripts/fetch_live_hrrr.py**

**IMPORTANT:** Update `RENAME_MAP` keys with real Herbie variable names from Task 2 before shipping.

```python
"""
Fetch HRRR forecast variables for DC metro stations for one forecast hour.
"""
import numpy as np
import pandas as pd
import xarray as xr
from datetime import datetime, timezone
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

HRRR_SEARCH = (
    ":(TMP|DPT|RH):2 m above ground|"
    ":UGRD:10 m above ground|"
    ":VGRD:10 m above ground|"
    ":HPBL:|"
    ":TCDC:boundary layer cloud layer|"
    ":HGT:cloud base"
)

# UPDATE THESE KEYS with real names from Task 2 _herbie_var_check.py output
RENAME_MAP = {
    "t2m": "tmp2m_k",        # 2m temperature (K)
    "d2m": "dpt2m_k",        # 2m dewpoint (K)
    "r2":  "rh2m_pct",       # 2m relative humidity (%)
    "u10": "u10_ms",          # 10m U-wind (m/s)
    "v10": "v10_ms",          # 10m V-wind (m/s)
    "blh": "hpbl_m",          # planetary boundary layer height (m)
    "tcc": "tcdc_bl_pct",     # total cloud cover boundary layer (%)
    "gh":  "hgt_cldbase_m",   # cloud base height (m) — ~38% NaN = no cloud
}


def extract_station_values(ds: xr.Dataset, station_coords: dict) -> pd.DataFrame:
    """
    Sample the xarray Dataset at each station's nearest HRRR grid point.

    Uses scaled Euclidean distance (accounts for lat/lon degree asymmetry at 39°N):
      1 degree lat ≈ 111 km, 1 degree lon ≈ 77 km at 39°N
    """
    grid_lats = ds["latitude"].values.ravel()
    grid_lons = ds["longitude"].values.ravel()   # already 0-360 in HRRR

    rows = []
    for station, (lat, lon) in station_coords.items():
        lon360 = lon + 360 if lon < 0 else lon
        # Scaled distance to avoid east-west bias at 39°N
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
    df["hgt_cldbase_m"] = df["hgt_cldbase_m"].fillna(10000.0)
    return df[REQUIRED_COLS].copy()


def fetch_hrrr_forecast_hour(run_time: datetime, fxx: int,
                              station_coords: dict = DC_STATION_COORDS,
                              save_dir: str = None) -> pd.DataFrame:
    """
    Download one HRRR forecast hour and extract station values.

    fxx=1 is the first true forecast hour (fxx=0 is the analysis field).
    Returns empty DataFrame on any failure — caller handles gracefully.

    save_dir defaults to HRRR_CACHE_DIR env var or /tmp/hrrr_cache.
    Do NOT hardcode a local absolute path — this must work on GitHub Actions.

    Herbie raises FileNotFoundError or ValueError for unavailable/malformed
    HRRR files (not HTTPError) — these are caught in the except block.
    """
    if save_dir is None:
        import os
        save_dir = os.environ.get("HRRR_CACHE_DIR", "/tmp/hrrr_cache")

    # Retry up to 3 times with 30-second waits.
    # Herbie raises FileNotFoundError or ValueError for unavailable/malformed HRRR
    # files — NOT HTTPError. Catch these specifically.
    import time as _time
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
```

**Step 3: Run tests**

```bash
python3 -m pytest tests/pipeline/test_hrrr_fetcher.py -v
# Expected: PASS (4 tests)
# Note: test_returns_empty_on_exception mocks Herbie — does not hit network
```

---

### Task 5: Refactor run_inference_hour.py and add infer_from_dataframes

Add a `infer_from_dataframes` function that accepts pre-loaded DataFrames and accepts pre-loaded model/calibrator objects — so the orchestrator loads them once, not 12 times per run.

**Files:**
- Modify: `scripts/run_inference_hour.py`
- Create: `tests/pipeline/test_inference.py`

**Step 1: Write tests**

```python
# tests/pipeline/test_inference.py
import numpy as np
import pandas as pd
import pickle
import xgboost as xgb
from datetime import datetime, timezone
from scripts.run_inference_hour import infer_from_dataframes

STATIONS = ["KBWI", "KCGS", "KDCA", "KFDK", "KGAI", "KHEF", "KIAD", "KNYG"]


def make_asos_row(station):
    return {
        "station": station, "elevation": 42.0,
        "t_td_spread_lag": 1.0, "wind_speed_mph_lag": 3.0,
        "drct_sin_lag": 0.0, "drct_cos_lag": 1.0,
        "hour_sin": 0.0, "hour_cos": -1.0,
        "month_sin": 0.866, "month_cos": 0.5,
    }


def make_hrrr_fog():
    return {"hpbl_m": 50.0, "tcdc_bl_pct": 80.0, "dpt2m_k": 275.0,
            "tmp2m_k": 276.0, "rh2m_pct": 96.0, "hgt_cldbase_m": 100.0,
            "u10_ms": 1.0, "v10_ms": -0.5}


def make_hrrr_clear():
    return {"hpbl_m": 2000.0, "tcdc_bl_pct": 0.0, "dpt2m_k": 260.0,
            "tmp2m_k": 275.0, "rh2m_pct": 30.0, "hgt_cldbase_m": 10000.0,
            "u10_ms": 8.0, "v10_ms": 3.0}


def load_model_and_cal():
    """Load model and calibrator once (matches how orchestrator uses them)."""
    model = xgb.XGBClassifier()
    model.load_model("models/xgb_asos_hrrr_full_v1.json")
    with open("models/calibrator_platt_v2.pkl", "rb") as f:
        cal_dict = pickle.load(f)
    return model, cal_dict


def test_returns_probabilities_in_range():
    model, cal_dict = load_model_and_cal()
    asos_df = pd.DataFrame([make_asos_row(s) for s in STATIONS])
    hrrr_df = pd.DataFrame([{"station": s, **make_hrrr_fog()} for s in STATIONS])
    valid_dt = datetime(2024, 12, 10, 9, tzinfo=timezone.utc)

    probs, stations = infer_from_dataframes(asos_df, hrrr_df, valid_dt, model, cal_dict)

    assert len(probs) == len(stations)
    assert all(0.0 <= p <= 1.0 for p in probs), f"Out of range: {probs}"


def test_fog_inputs_score_higher_than_clear():
    model, cal_dict = load_model_and_cal()
    asos_df = pd.DataFrame([make_asos_row(s) for s in STATIONS])
    valid_dt = datetime(2024, 12, 10, 9, tzinfo=timezone.utc)

    hrrr_fog   = pd.DataFrame([{"station": s, **make_hrrr_fog()}   for s in STATIONS])
    hrrr_clear = pd.DataFrame([{"station": s, **make_hrrr_clear()} for s in STATIONS])

    probs_fog,   _ = infer_from_dataframes(asos_df, hrrr_fog,   valid_dt, model, cal_dict)
    probs_clear, _ = infer_from_dataframes(asos_df, hrrr_clear, valid_dt, model, cal_dict)

    assert np.mean(probs_fog) > np.mean(probs_clear), \
        f"Fog {np.mean(probs_fog):.3f} not > clear {np.mean(probs_clear):.3f}"
```

**Step 2: Update path constants and encode_station in run_inference_hour.py**

First, update the path constants at the top of the file:

```python
MODEL_PATH      = ROOT / "models/xgb_asos_hrrr_full_v1.json"
CALIBRATOR_PATH = ROOT / "models/calibrator_platt_v2.pkl"
```

Also update `encode_station` — the full 6yr model uses `enable_categorical=True`, which requires
`station_code` to be a `pd.Categorical` (not integer codes). The old `.cat.codes` approach returns
int64, which XGBoost won't recognise as categorical:

```python
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
```

Also fix the month formula in `build_asos_features` (the existing file-based function used in `run_hour`):
```python
# CORRECT — matches training formula (month is 1-indexed, no -1 offset)
asos_lag["month_sin"] = np.sin(2 * np.pi * month / 12)
asos_lag["month_cos"] = np.cos(2 * np.pi * month / 12)
```

**Step 3: Add `infer_from_dataframes` to run_inference_hour.py**

Add this function. It accepts `model` and `cal_dict` as parameters so the caller loads them once.

```python
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

    merged = pd.merge(asos_feat, hrrr_feat, on="station", how="inner")
    if merged.empty:
        return np.array([]), []

    # CRITICAL: must reuse the same CategoricalDtype from training (MEMORY.md)
    with open(STATION_LIST) as f:
        station_list = json.load(f)
    merged = encode_station(merged, station_list)

    feature_cols = cal_dict["features"]
    fill_medians = cal_dict["fill_medians"]

    for col in feature_cols:
        if col not in merged.columns:
            merged[col] = fill_medians[col]

    # Explicitly reorder columns to match training order — XGBoost is sensitive to this
    X = merged[feature_cols].fillna(fill_medians)
    assert len(X.columns) == 18, f"Expected 18 features, got {len(X.columns)}: {list(X.columns)}"

    raw_scores = model.predict_proba(X)[:, 1]
    cal_probs  = cal_dict["calibrator"].predict_proba(
                     raw_scores.reshape(-1, 1))[:, 1]

    # Sanity check: calibrated probs should be in [0.008, 0.252] range (6yr full model)
    if np.any(cal_probs <= 0.0) or np.any(cal_probs >= 1.0):
        raise ValueError(f"Calibrated probs out of range [0,1]: min={cal_probs.min():.3f}, max={cal_probs.max():.3f}")
    if np.any(cal_probs > 0.40):
        print(f"  WARNING: Some calibrated probs outside expected [0.008, 0.252] range. "
              f"min={cal_probs.min():.3f}, max={cal_probs.max():.3f} — check model inputs.")

    return cal_probs, merged["station"].tolist()
```

**Step 4: Run tests**

```bash
python3 -m pytest tests/pipeline/test_inference.py -v
# Expected: PASS (2 tests)
```

**Step 5: Verify existing run_hour still works with updated model**

```bash
python3 scripts/run_inference_hour.py 2024-12-10T09:00:00Z
# Expected: fog alerts at some stations, GeoTIFF written to outputs/spatial/
# Note: alert rate will differ from pilot model (threshold is now 0.17, not 0.09)
```

---

### Task 6: Set up Cloudflare R2 bucket

GeoTIFFs are stored in R2, not committed to git. This task sets up the bucket and verifies uploads work.

**Files:**
- Create: `scripts/upload_to_r2.py`

**Step 1: Create Cloudflare R2 bucket**

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → R2 → Create bucket → name: `fogchaser-maps`
2. On the bucket page → Settings → Enable "Public Access" → note the public URL: `https://pub-XXXXXXXX.r2.dev`
3. Go to R2 → Manage R2 API Tokens → Create API Token:
   - **Scope it to "Object Read & Write" on the `fogchaser-maps` bucket only.** Do not use an account-level token — it's overpermissioned.
4. Note: Account ID, Access Key ID, Secret Access Key
5. **Configure CORS** on the bucket: allowed origin = your Vercel domain (e.g., `https://fogchaser.vercel.app`), allowed methods = `GET`. Without this, browsers will silently block GeoTIFF loads (no JS error — just an empty map). Test by opening a GeoTIFF URL in the browser from the deployed Vercel domain and checking the Network tab for CORS errors.

Keep these — you'll need them as GitHub Actions secrets in Task 8.

**Step 2: Install boto3**

```bash
pip3 install boto3
pip3 freeze | grep boto3 >> requirements.txt
```

**Step 3: Write scripts/upload_to_r2.py**

```python
"""
Upload a file to Cloudflare R2 (S3-compatible).
"""
import os
import boto3
from pathlib import Path


def get_r2_client():
    from botocore.config import Config
    account_id = os.environ["R2_ACCOUNT_ID"]
    return boto3.client(
        "s3",
        endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(retries={"max_attempts": 3, "mode": "standard"}),
    )


def upload_tif(local_path: str, bucket: str = None) -> str:
    """
    Upload a GeoTIFF to R2. Returns the public URL.

    Requires env vars: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID,
                       R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, R2_PUBLIC_URL
    """
    if bucket is None:
        bucket = os.environ["R2_BUCKET_NAME"]
    public_url_base = os.environ["R2_PUBLIC_URL"].rstrip("/")

    fname = Path(local_path).name
    client = get_r2_client()
    client.upload_file(
        local_path, bucket, fname,
        ExtraArgs={"ContentType": "image/tiff"}
    )
    return f"{public_url_base}/{fname}"
```

**Step 4: Smoke test upload (replace with your real credentials)**

```bash
export R2_ACCOUNT_ID=your_account_id
export R2_ACCESS_KEY_ID=your_key_id
export R2_SECRET_ACCESS_KEY=your_secret
export R2_BUCKET_NAME=fogchaser-maps
export R2_PUBLIC_URL=https://pub-XXXXXXXX.r2.dev

python3 -c "
from scripts.upload_to_r2 import upload_tif
url = upload_tif('outputs/spatial/fog_prob_20241210_09UTC.tif')
print('Uploaded:', url)
"
# Expected: prints the public URL

# Verify public access is working — this must return HTTP 200
# If it returns 403 or CORS error, fix the bucket public access settings before proceeding
curl -I "<the public URL printed above>"
# Expected: HTTP/2 200
```

**Important:** Upload all GeoTIFFs before writing `manifest.json`. If any upload fails, do not write the manifest — log the error and exit with a non-zero code. A partial manifest pointing to missing files will break the frontend.

---

### Task 7: Write the live forecast orchestrator

Ties everything together. Loads model/calibrator once. Handles ASOS lag for future hours. Uploads to R2.

**Files:**
- Create: `scripts/run_live_forecast.py` (includes `build_asos_for_hour` — defined here, not in fetch_live_asos.py)

**GeoTIFF naming convention:** `fog_{YYYYMMDD}_{HH}Z_fxx{FXX:02d}.tif` (e.g., `fog_20240115_00Z_fxx06.tif`)

**Manifest structure (frontend contract — do not change without updating app.js):**
```json
{
  "run_utc":       "2024-01-15T00:00:00Z",
  "generated_utc": "2024-01-15T01:23:45Z",
  "asos_note": "fxx>=2: ASOS lag substituted with HRRR-derived values (approximation)",
  "hours": [
    { "fxx": 1, "valid_utc": "2024-01-15T01:00:00Z", "url": "https://pub-xxx.r2.dev/fog_20240115_00Z_fxx01.tif", "approx_asos": false },
    { "fxx": 2, "valid_utc": "2024-01-15T02:00:00Z", "url": null }
  ]
}
```
`url` is `null` for hours that failed — the frontend must grey out null entries.

**Key design decision — ASOS lag for future forecast hours:**
The model was trained with ASOS observations from the hour *before* the fog event. For fxx=1 (1 hour out), we have the current ASOS as the lag. For fxx>=2, we don't have future observations, so we substitute HRRR-derived values for all four ASOS lag features:

- `t_td_spread_lag = (tmp2m_k - dpt2m_k) * 9/5`
  **Unit math note:** This is a *temperature difference*, not an absolute temperature, so no 273.15 offset is needed. Kelvin and Celsius share the same degree size; `* 9/5` converts the difference to °F scale. Do not subtract 273.15.
- `wind_speed_mph_lag = sqrt(u10_ms² + v10_ms²) * 2.237`
- `drct_sin_lag = -u10_ms / wind_speed` (meteorological convention: wind FROM direction)
- `drct_cos_lag = -v10_ms / wind_speed`
- For calm winds (speed < 0.1 m/s), set sin/cos to 0.

**Important caveat on the fxx>=2 boundary:** This cutoff is an approximation. The true boundary is whether `valid_time > most_recent_asos_observation + 90 minutes`. If a fresh ASOS observation exists within 90 min of valid time, use it regardless of fxx value. Document this assumption in a code comment.

Document this clearly in the app — it's an approximation for forecast hours beyond the current observation window.

```python
"""
Live forecast orchestrator.

Usage: python3 scripts/run_live_forecast.py

Finds the most recent HRRR run, fetches live ASOS, runs inference for
fxx=1–12, uploads GeoTIFFs to R2, commits manifest.json to app/data/.
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
from scripts.run_inference_hour import (infer_from_dataframes, CALIBRATOR_PATH,
                                         MODEL_PATH, STATION_COORDS)
from scripts.spatial_pipeline import run_spatial_pipeline
from scripts.upload_to_r2 import upload_tif

import pandas as pd

OUTPUT_DIR      = "/tmp/fog_output"   # local staging only — not committed
MANIFEST_PATH   = "app/data/manifest.json"
FORECAST_FXX    = range(1, 13)        # fxx=1 through fxx=12 (skip fxx=0 analysis)
HRRR_RUN_HOURS  = [0, 6, 12, 18]


def latest_hrrr_run(now_utc: datetime) -> datetime:
    """Return the most recent HRRR run that should be available (90-min lag)."""
    # CRITICAL: handle day boundary correctly using timedelta, not hour arithmetic
    cutoff = now_utc - timedelta(minutes=90)
    # Find the latest run hour <= cutoff hour on the SAME date as cutoff
    run_hour = max((h for h in HRRR_RUN_HOURS if h <= cutoff.hour), default=18)
    if not any(h <= cutoff.hour for h in HRRR_RUN_HOURS):
        # All run hours are after cutoff.hour — go to previous day, use 18 UTC
        cutoff = cutoff - timedelta(days=1)
        run_hour = 18
    return cutoff.replace(hour=run_hour, minute=0, second=0, microsecond=0)


def read_geotiff_mean(tif_path: str) -> float:
    with rasterio.open(tif_path) as src:
        arr = src.read(1).astype(float)
        nodata = src.nodata or -9999.0
    valid = arr[(arr != nodata) & (arr > -9990)]
    return float(np.mean(valid)) if len(valid) > 0 else 0.0


def build_asos_for_hour(asos_df: pd.DataFrame, hrrr_df: pd.DataFrame,
                         valid_dt: datetime, fxx: int,
                         cal_dict: dict) -> pd.DataFrame:
    """
    Build the full ASOS feature DataFrame for one forecast hour.

    For fxx=1: use real ASOS observations as lag features.
    For fxx>=2: real ASOS observations are in the future — substitute
    HRRR-derived T-Td spread and fill other ASOS features with training medians.
    This is an approximation; documented in the app.
    """
    merged = pd.merge(asos_df, hrrr_df, on="station", how="inner")
    fill = cal_dict["fill_medians"]

    result = []
    for _, row in merged.iterrows():
        r = {"station": row["station"]}
        if fxx <= 1:
            # Real ASOS lag available
            r["t_td_spread_lag"]    = row.get("t_td_spread_lag", fill["t_td_spread_lag"])
            r["wind_speed_mph_lag"] = row.get("wind_speed_mph_lag", fill["wind_speed_mph_lag"])
            r["drct_sin_lag"]       = row.get("drct_sin_lag", fill["drct_sin_lag"])
            r["drct_cos_lag"]       = row.get("drct_cos_lag", fill["drct_cos_lag"])
            r["elevation"]          = row.get("elevation", fill["elevation"])
        else:
            # Future hours: substitute HRRR-derived values for all ASOS lag features.
            # T-Td spread: difference in K ≈ difference in °C; multiply by 9/5 for °F scale.
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
                    r["drct_sin_lag"] = 0.0   # calm: no preferred direction
                    r["drct_cos_lag"] = 0.0
            else:
                r["wind_speed_mph_lag"] = fill["wind_speed_mph_lag"]
                r["drct_sin_lag"]       = fill["drct_sin_lag"]
                r["drct_cos_lag"]       = fill["drct_cos_lag"]
            r["elevation"] = row.get("elevation", fill["elevation"])

        # Cyclic time features always come from the forecast valid_dt
        # CRITICAL: use month/12 (1-indexed), NOT (month-1)/12 — must match training formula
        r["hour_sin"]   = np.sin(2 * np.pi * valid_dt.hour / 24)
        r["hour_cos"]   = np.cos(2 * np.pi * valid_dt.hour / 24)
        r["month_sin"]  = np.sin(2 * np.pi * valid_dt.month / 12)
        r["month_cos"]  = np.cos(2 * np.pi * valid_dt.month / 12)
        result.append(r)

    return pd.DataFrame(result)


def main(override_run_time=None):
    """override_run_time: pass a datetime to run hindcast against a past HRRR run (for testing)."""
    now_utc  = datetime.now(timezone.utc)
    run_time = override_run_time if override_run_time else latest_hrrr_run(now_utc)
    print(f"\n{'='*60}")
    print(f"Fogchaser live forecast — {now_utc.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"HRRR run: {run_time.strftime('%Y-%m-%d %H UTC')}")
    print(f"{'='*60}\n")

    # Load model and calibrator ONCE — not inside the per-hour loop
    print("Loading model and calibrator...")
    model = xgb.XGBClassifier()
    model.load_model(MODEL_PATH)
    with open(CALIBRATOR_PATH, "rb") as f:
        cal_dict = pickle.load(f)
    print(f"  Model loaded. Features: {len(cal_dict['features'])}")

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
            manifest["hours"].append({"fxx": fxx, "valid_utc": valid_dt.strftime("%Y-%m-%dT%H:00:00Z"), "url": None, "approx_asos": fxx >= 2})
            continue

        # Wrap each fxx in try/except — don't abort the whole batch for one failure
        try:
            asos_hour = build_asos_for_hour(asos_df, hrrr_df, valid_dt, fxx, cal_dict)

            # Check station count — spatial pipeline requires >=6 stations
            if len(asos_hour) < 6:
                missing = set(DC_STATION_COORDS.keys()) - set(asos_hour["station"].tolist())
                print(f"SKIP — only {len(asos_hour)} stations (missing: {sorted(missing)})")
                manifest["hours"].append({"fxx": fxx, "valid_utc": valid_dt.strftime("%Y-%m-%dT%H:00:00Z"), "url": None, "approx_asos": fxx >= 2})
                continue

            cal_probs, stations = infer_from_dataframes(
                asos_hour, hrrr_df, valid_dt, model, cal_dict)
            if len(cal_probs) == 0:
                print("SKIP — no stations merged")
                manifest["hours"].append({"fxx": fxx, "valid_utc": valid_dt.strftime("%Y-%m-%dT%H:00:00Z"), "url": None, "approx_asos": fxx >= 2})
                continue

            lats  = [DC_STATION_COORDS[s][0] for s in stations if s in DC_STATION_COORDS]
            lons  = [DC_STATION_COORDS[s][1] for s in stations if s in DC_STATION_COORDS]
            probs = [p for s, p in zip(stations, cal_probs) if s in DC_STATION_COORDS]

            # IMPORTANT: capture the return value — do not construct tif_local manually.
            # run_spatial_pipeline determines the output filename internally.
            # If it does not return a path, update spatial_pipeline.py to do so.
            tif_local = run_spatial_pipeline(
                station_probs=probs, station_lats=lats, station_lons=lons,
                terrain_offset_path="data/processed/terrain_offset_grid.tif",
                output_dir=OUTPUT_DIR, valid_dt=valid_dt,
            )
            # Expected: tif_local = "/tmp/fog_output/fog_prob_YYYYMMDD_HHUTC.tif" (or similar)
            # If spatial_pipeline.py does not return the path, add `return output_path`
            # to its final line before integrating here.

            avg_prob = read_geotiff_mean(tif_local)

            # Upload to R2
            tif_url = upload_tif(tif_local)

            # Fog Risk Score — thresholds must match fogScore() in app.js exactly
            score = (1 if avg_prob < 0.08 else
                     2 if avg_prob < 0.13 else
                     3 if avg_prob < 0.17 else
                     4 if avg_prob < 0.22 else 5)
            label = {1: "Low", 2: "Moderate", 3: "High", 4: "Very High", 5: "Extreme"}[score]
            relative_risk = round(avg_prob / 0.054, 1)  # vs ~5.4% baseline

            manifest["hours"].append({
                "fxx":           fxx,
                "valid_utc":     valid_dt.strftime("%Y-%m-%dT%H:00:00Z"),
                "score":         score,
                "label":         label,
                "relative_risk": relative_risk,
                "avg_prob":      round(avg_prob, 3),
                "url":           tif_url,
                "approx_asos":   fxx >= 2,
            })
            print(f"avg={avg_prob:.3f}  score={score}/5 [{label}]  {relative_risk}× baseline  → {tif_url.split('/')[-1]}")

        except Exception as e:
            print(f"ERROR: fxx={fxx} failed: {e}")
            manifest["hours"].append({"fxx": fxx, "valid_utc": valid_dt.strftime("%Y-%m-%dT%H:00:00Z"), "url": None, "approx_asos": fxx >= 2})

    # Count successful hours
    successful = sum(1 for h in manifest["hours"] if h.get("url") is not None)
    print(f"\n{successful} of {len(manifest['hours'])} forecast hours succeeded.")
    if successful < 10:
        print(f"ERROR: Only {successful} hours succeeded — marking run as failed.")
        sys.exit(1)

    # Write manifest atomically — write to temp file, validate JSON, then rename
    Path("app/data").mkdir(parents=True, exist_ok=True)
    manifest_tmp = MANIFEST_PATH + ".tmp"
    with open(manifest_tmp, "w") as f:
        json.dump(manifest, f, indent=2)
    # Validate it's valid JSON before overwriting the live manifest
    with open(manifest_tmp) as f:
        json.load(f)  # will raise if malformed
    import os as _os
    _os.rename(manifest_tmp, MANIFEST_PATH)
    print(f"Manifest: {MANIFEST_PATH}  ({len(manifest['hours'])} hours)")


if __name__ == "__main__":
    main()
```

**Step 2: Manual test (requires R2 credentials set as env vars)**

```bash
export R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
export R2_BUCKET_NAME=fogchaser-maps R2_PUBLIC_URL=https://pub-XXXX.r2.dev

python3 scripts/run_live_forecast.py

# Expected:
# - 8-12 hours generated
# - GeoTIFFs uploaded to R2
# - app/data/manifest.json written with tif_url fields pointing to R2

python3 -c "
import json
with open('app/data/manifest.json') as f: m = json.load(f)
print('Hours:', len(m['hours']))
for h in m['hours']:
    url = h.get('url') or 'FAILED'
    print(f\"  {h['valid_utc']}  {h.get('label','—')}  {url[:60]}\")
"
```

**Step 3: Add manifest structure test**

```python
# tests/pipeline/test_manifest.py
import json
import os

def test_manifest_structure():
    """The manifest is the contract between pipeline and frontend.
    If keys change, the frontend breaks silently."""
    manifest_path = "app/data/manifest.json"
    if not os.path.exists(manifest_path):
        import pytest
        pytest.skip("No manifest.json yet — run the pipeline first")

    with open(manifest_path) as f:
        m = json.load(f)

    assert "run_utc" in m, "manifest missing 'run_utc'"
    assert "generated_utc" in m, "manifest missing 'generated_utc'"
    assert "hours" in m, "manifest missing 'hours'"
    assert len(m["hours"]) > 0, "manifest has empty 'hours'"
    for h in m["hours"]:
        assert "fxx" in h and isinstance(h["fxx"], int)
        assert "valid_utc" in h and isinstance(h["valid_utc"], str)
        assert "url" in h  # url may be None for failed hours — that's OK
        assert "approx_asos" in h
```

**Step 4: Run all pipeline tests**

```bash
python3 -m pytest tests/ -v
# Expected: all tests pass
```

---

## Phase 2 — GitHub Actions

### Task 8: Set up GitHub repository and Actions workflow

**Prerequisites:**

```bash
cd "/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/work/vibe coding/fogchaser"
git init
git add .
git commit -m "feat: initial fogchaser commit"
# Create repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/fogchaser.git
git branch -M main
git push -u origin main
```

**Add GitHub Secrets** (repo → Settings → Secrets → Actions):
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `R2_PUBLIC_URL`

**Files:**
- Create: `.github/workflows/forecast.yml`

```yaml
name: Fog Forecast

on:
  schedule:
    # 30min after each HRRR run: :30 at 00, 06, 12, 18 UTC
    # Running at :30 (not :01) gives HRRR files time to be fully published,
    # especially fxx=10-12 which are published last.
    - cron: "30 0,6,12,18 * * *"
  workflow_dispatch:   # manual trigger from GitHub UI for testing

# Cancel any in-progress run when a new one starts — prevents job queue buildup
# if a run takes longer than expected (e.g., HRRR data delayed).
concurrency:
  group: forecast
  cancel-in-progress: true

jobs:
  forecast:
    runs-on: ubuntu-latest
    timeout-minutes: 45   # hard cap — prevents hung jobs from blocking future runs
    permissions:
      contents: write

    steps:
      - uses: actions/checkout@v4

      - name: Install eccodes (required by Herbie, cannot install via pip)
        run: sudo apt-get install -y libeccodes-dev

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run forecast pipeline
        env:
          R2_ACCOUNT_ID:         ${{ secrets.R2_ACCOUNT_ID }}
          R2_ACCESS_KEY_ID:      ${{ secrets.R2_ACCESS_KEY_ID }}
          R2_SECRET_ACCESS_KEY:  ${{ secrets.R2_SECRET_ACCESS_KEY }}
          R2_BUCKET_NAME:        ${{ secrets.R2_BUCKET_NAME }}
          R2_PUBLIC_URL:         ${{ secrets.R2_PUBLIC_URL }}
          HRRR_CACHE_DIR:        /tmp/hrrr_cache
        run: python3 scripts/run_live_forecast.py

      - name: Commit updated manifest
        run: |
          git config user.email "actions@github.com"
          git config user.name  "GitHub Actions"
          git pull --rebase origin main   # prevent non-fast-forward on retry
          git add app/data/manifest.json
          git diff --cached --quiet || \
            git commit -m "forecast: $(date -u '+%Y-%m-%d %H:%M UTC')"
          git push
```

**Validate the YAML:**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/forecast.yml')); print('valid')"
```

**Test by triggering manually** after pushing:
- GitHub → Actions → Fog Forecast → Run workflow
- Watch the logs — confirm it completes and manifest.json is updated

---

## Phase 3 — Web Frontend

### Task 9: Build the Leaflet map with fog overlay

Single `index.html` file. No build step. All libraries from CDN.

**Files:**
- Create: `app/style.css`
- Overwrite: `app/index.html`
- Create: `app/app.js`

**Step 1: Write app/style.css**

```css
* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #0f1117;
  color: #e8eaf0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

#header {
  padding: 10px 16px;
  background: #1a1d27;
  border-bottom: 1px solid #2a2d3a;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
  z-index: 1000;
}

#header h1 { font-size: 17px; font-weight: 700; color: #7eb8e8; letter-spacing: 0.08em; }

#summary-badge {
  padding: 3px 10px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  background: #1e3a52;
  color: #7eb8e8;
}

#updated-label {
  margin-left: auto;
  font-size: 11px;
  color: #555;
}

#season-notice {
  background: #2a2510;
  border-bottom: 1px solid #3a3215;
  padding: 5px 16px;
  font-size: 12px;
  color: #b8a060;
  text-align: center;
  flex-shrink: 0;
}

#map { flex: 1; min-height: 0; }

#time-bar {
  padding: 8px 16px 10px;
  background: #1a1d27;
  border-top: 1px solid #2a2d3a;
  flex-shrink: 0;
}

#time-bar label { font-size: 12px; color: #888; display: block; margin-bottom: 5px; }
#hour-slider { width: 100%; accent-color: #7eb8e8; cursor: pointer; height: 20px; }
#hour-labels { display: flex; justify-content: space-between; font-size: 10px; color: #555; margin-top: 3px; }

/* Click panel */
#click-panel {
  display: none;
  position: absolute;
  bottom: 80px; left: 12px; right: 12px;
  z-index: 1000;
  background: #1a1d27;
  border: 1px solid #2a2d3a;
  border-radius: 10px;
  padding: 14px 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.6);
}
@media (min-width: 600px) {
  #click-panel { left: 16px; width: 280px; right: auto; }
}
#click-panel.visible { display: block; }
.close-btn { float: right; background: none; border: none; color: #666; font-size: 16px; cursor: pointer; }
#prob-value { font-size: 32px; font-weight: 700; color: #7eb8e8; }
#prob-label { font-size: 13px; color: #888; margin-top: 2px; }
#approx-note { font-size: 11px; color: #555; margin-top: 6px; font-style: italic; }

#loading {
  position: absolute; top: 50%; left: 50%;
  transform: translate(-50%, -50%);
  z-index: 2000;
  background: rgba(15,17,23,0.92);
  padding: 18px 28px;
  border-radius: 8px;
  font-size: 13px;
  color: #7eb8e8;
}
```

**Step 2: Write app/index.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Fogchaser — DC Metro</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <link rel="stylesheet" href="style.css" />
</head>
<body>

<div id="header">
  <h1>fogchaser</h1>
  <span id="summary-badge">Loading...</span>
  <span id="updated-label">—</span>
</div>

<div id="season-notice">
  Best accuracy Oct–Mar · Model trained on winter data only · Not for safety decisions
</div>

<div id="station-notice">
  Forecast interpolated from 8 weather stations · Accuracy decreases away from station locations
</div>

<div id="map"></div>

<div id="time-bar">
  <label id="hour-label">—</label>
  <input type="range" id="hour-slider" min="0" max="0" value="0" />
  <div id="hour-labels"></div>
</div>

<div id="click-panel">
  <button class="close-btn" id="close-btn">✕</button>
  <div id="prob-value">—</div>
  <div id="prob-label">—</div>
  <div id="approx-note"></div>
</div>

<div id="loading">Loading forecast...</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/georaster@1.5.6/dist/georaster.bundle.min.js"></script>
<script src="https://unpkg.com/georaster-layer-for-leaflet@3.10.0/dist/georaster-layer-for-leaflet.min.js"></script>
<script src="https://unpkg.com/geoblaze@2.4.1/dist/geoblaze.browser.js"></script>
<script src="app.js"></script>
</body>
</html>
```

**Step 3: Write app/app.js**

Color ramp: minimum threshold at **0.03** (below this, render transparent — practical noise floor; model calibrated range is 0.008–0.252). Add a visual break at **0.17** (the F2-optimized alert threshold) — use a more distinct color step or legend marker here so users can see the "actionable" threshold.

**Important UI requirements (non-negotiable for an honest product):**
1. **Error fallback:** Wrap the manifest fetch in a try/catch. On failure, display: "Forecast data unavailable — try again later." Do not leave the map in a broken/blank state.
2. **Cache-busting:** Fetch manifest with `fetch('/data/manifest.json?t=' + Date.now())` — Vercel will otherwise cache the file and users will see stale forecasts for hours.
3. **Station disclaimer:** Add visible text on the map: "Forecast interpolated from 8 weather stations. Accuracy decreases away from station locations."
4. **Seasonal disclaimer:** Add: "Model trained on winter data (Nov–Feb). Predictions outside fog season (Oct–Mar) are less reliable." Consider a prominent warning banner in summer months (May–Sep).

```javascript
const DATA_DIR  = "data";
const DC_CENTER = [38.95, -77.05];
const DC_ZOOM   = 10;

// Color ramp calibrated for model output range 0.008–0.252
// Threshold: below 0.03, render transparent (practical noise floor)
// Visual break at 0.17 = F2-optimized alert threshold (actionable for photographer)
function fogColor(prob) {
  if (prob == null || prob < 0) return null;
  if (prob < 0.03)  return null;                        // below practical signal — no color
  if (prob < 0.08)  return "rgba(173,216,230,0.25)";    // very light blue — low background
  if (prob < 0.12)  return "rgba(120,180,220,0.40)";
  if (prob < 0.17)  return "rgba(80,150,210,0.55)";     // approaching alert threshold
  if (prob < 0.21)  return "rgba(50,120,195,0.65)";     // at/above 0.17 threshold
  if (prob < 0.24)  return "rgba(25,90,180,0.75)";
  return                    "rgba(0, 40,145,0.88)";     // deep blue — near model max (0.252)
}

const BASELINE = 0.054; // ~5.4% base fog rate in DC metro training data

function fogScore(prob) {
  if (!prob || prob < 0.08) return 1;   // Low — below meaningful signal
  if (prob < 0.13) return 2;             // Moderate
  if (prob < 0.17) return 3;             // High — approaching alert threshold
  if (prob < 0.22) return 4;             // Very High — at/above alert threshold
  return 5;                              // Extreme — near model max (~0.252)
}

function fogLabel(prob) {
  return ["", "Low", "Moderate", "High", "Very High", "Extreme"][fogScore(prob)];
}

function relativeRisk(prob) {
  if (!prob) return "1.0";
  return (prob / BASELINE).toFixed(1);
}

// Legacy helper used in summary badge — returns "Score/5 — Label"
function probLabel(prob) {
  if (!prob || prob < 0.03) return "1/5 — Low";
  return `${fogScore(prob)}/5 — ${fogLabel(prob)}`;
}

function timeAgo(isoStr) {
  const diff = (Date.now() - new Date(isoStr).getTime()) / 60000; // minutes
  if (diff < 60)  return `${Math.round(diff)}m ago`;
  return `${Math.round(diff / 60)}h ago`;
}

// ── State ────────────────────────────────────────────────────────────────────
let map, currentLayer, manifest;
const georasterCache = {};

// ── Init map ─────────────────────────────────────────────────────────────────
map = L.map("map", { center: DC_CENTER, zoom: DC_ZOOM });
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "© OpenStreetMap contributors", maxZoom: 18,
}).addTo(map);

document.getElementById("close-btn").addEventListener("click", () => {
  document.getElementById("click-panel").classList.remove("visible");
});

// ── Load manifest and start ───────────────────────────────────────────────────
async function init() {
  try {
    // Cache-busting required — Vercel CDN caches manifest.json aggressively.
    // Without ?t=..., users will see stale forecast data for hours after a new run.
    const r = await fetch(`${DATA_DIR}/manifest.json?t=` + Date.now());
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    manifest = await r.json();
  } catch (e) {
    document.getElementById("loading").textContent =
      "Forecast data unavailable — try again later.";
    document.getElementById("loading").style.color = "#e88";
    return;
  }

  if (!manifest.hours?.length) {
    document.getElementById("loading").textContent = "Forecast data empty.";
    return;
  }

  // Updated timestamp
  document.getElementById("updated-label").textContent =
    "Updated " + timeAgo(manifest.generated_utc);

  // Summary badge — average only overnight hours (23:00–07:00 UTC)
  // These are the hours relevant to a photographer's morning decision
  const overnightHours = manifest.hours.filter(h => {
    const hr = parseInt(h.valid_utc.slice(11, 13));
    return hr >= 23 || hr <= 7;
  });
  const hoursForBadge = overnightHours.length > 0 ? overnightHours : manifest.hours;
  const avgOvernight = hoursForBadge.reduce((s, h) => s + h.avg_prob, 0) / hoursForBadge.length;
  document.getElementById("summary-badge").textContent =
    `Fog tonight: ${probLabel(avgOvernight)}  ·  ${relativeRisk(avgOvernight)}× above normal`;

  // Build slider
  const slider = document.getElementById("hour-slider");
  slider.max   = manifest.hours.length - 1;
  slider.value = 0;
  buildHourLabels();

  await showHour(0);
  document.getElementById("loading").style.display = "none";

  slider.addEventListener("input", () => showHour(parseInt(slider.value)));
  map.on("click", onMapClick);
}

function buildHourLabels() {
  const el = document.getElementById("hour-labels");
  el.innerHTML = "";
  // Show every other hour label to avoid crowding on mobile
  manifest.hours.forEach((h, i) => {
    const span = document.createElement("span");
    span.textContent = i % 2 === 0 ? h.valid_utc.slice(11, 13) + "Z" : "";
    el.appendChild(span);
  });
}

async function showHour(idx) {
  const h = manifest.hours[idx];
  document.getElementById("hour-label").textContent =
    `${h.valid_utc.slice(0, 10)}  ${h.valid_utc.slice(11, 13)}:00 UTC  —  ${h.label || "—"}`;

  if (!h.url) {
    // This hour failed — remove any existing layer and show nothing
    if (currentLayer) { map.removeLayer(currentLayer); currentLayer = null; }
    return;
  }
  const gr = await loadGeoRaster(h.url);
  if (currentLayer) map.removeLayer(currentLayer);

  currentLayer = new GeoRasterLayer({
    georaster: gr,
    opacity:   0.85,
    pixelValuesToColorFn: (values) => {
      const v = values[0];
      if (v == null || v < -9990) return null;
      return fogColor(v);
    },
    resolution: 256,
  });
  currentLayer.addTo(map);
}

async function loadGeoRaster(url) {
  if (georasterCache[url]) return georasterCache[url];
  const resp   = await fetch(url);
  const buffer = await resp.arrayBuffer();
  const gr     = await parseGeoraster(buffer);
  georasterCache[url] = gr;
  return gr;
}

async function onMapClick(e) {
  const h  = manifest.hours[parseInt(document.getElementById("hour-slider").value)];
  if (!h.url) return;
  const gr = await loadGeoRaster(h.url);

  let prob = null;
  try {
    const results = await geoblaze.identify(gr, [e.latlng.lng, e.latlng.lat]);
    if (results?.[0] != null && results[0] > -9990) prob = results[0];
  } catch (_) {}
  if (prob == null) return;

  document.getElementById("prob-value").textContent =
    `${fogScore(prob)}/5 — ${fogLabel(prob)}`;
  document.getElementById("prob-label").textContent =
    `${Math.round(prob * 100)}%  ·  ${relativeRisk(prob)}× more likely than a typical morning`;
  document.getElementById("approx-note").textContent =
    h.approx_asos ? "Note: ASOS data approximated for this forecast hour" : "";
  document.getElementById("click-panel").classList.add("visible");
}

init();
```

**Step 4: Test locally**

```bash
cd "/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/work/vibe coding/fogchaser/app"
python3 -m http.server 8080
# Open http://localhost:8080
```

Note: the app needs a real `app/data/manifest.json` with `url` fields pointing to R2.
If testing before R2 is set up, temporarily point `tif_url` to a local path and test with `python3 -m http.server`.

Verify:
- Map loads on desktop and mobile
- Fog overlay appears (blue over valley corridors, lighter over urban DC)
- Time slider switches hours
- Tapping/clicking map shows probability panel
- Season notice is visible at all times
- "Last updated X hours ago" shows in header

---

## Phase 4 — Deploy

### Task 10: Deploy to Vercel

**Files:**
- Create: `vercel.json`

```json
{
  "outputDirectory": "app",
  "buildCommand": "",
  "installCommand": "",
  "headers": [
    {
      "source": "/data/manifest.json",
      "headers": [
        { "key": "Cache-Control", "value": "no-cache, no-store, must-revalidate" }
      ]
    }
  ]
}
```

**Why `no-cache` on manifest.json:** Vercel's CDN aggressively caches static files. Without this header, users will see stale forecast data for hours after a new pipeline run. The frontend also adds `?t=<timestamp>` as a second layer of cache-busting.

```bash
npm install -g vercel
cd "/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/work/vibe coding/fogchaser"
vercel
# Follow prompts — set output directory to app/
# After deploy, go to Vercel dashboard → Settings → Git → connect GitHub repo → branch: main
```

Expected: live URL like `https://fogchaser.vercel.app`

**Pre-deploy integration test (do this before enabling the schedule):**

Before enabling the scheduled Actions workflow, run the full orchestrator once locally in hindcast mode against a known past HRRR date:

```bash
export R2_ACCOUNT_ID=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=...
export R2_BUCKET_NAME=fogchaser-maps R2_PUBLIC_URL=https://pub-XXXX.r2.dev
export HRRR_CACHE_DIR=/tmp/hrrr_cache

# Run against a past date to verify end-to-end wiring
python3 -c "
import scripts.run_live_forecast as f
from datetime import datetime, timezone
f.main(override_run_time=datetime(2024, 1, 15, 0, tzinfo=timezone.utc))
"

# Verify:
# - 8 station rows produced per hour (check logs)
# - 10+ of 12 hours succeed
# - app/data/manifest.json written and valid JSON
# - GeoTIFFs visible at their R2 URLs
# - Load app/index.html locally and verify the map renders
```

If this passes, the pipeline is wired correctly. Then enable the schedule.

**Final check — trigger first live cycle:**

GitHub → Actions → Fog Forecast → Run workflow

Confirm: pipeline completes, manifest.json updated in repo, Vercel redeploys, app shows tonight's forecast.

---

## Current Model (6yr full — already in place)

The pipeline uses the retrained 6yr model. No model swap needed.

- `models/xgb_asos_hrrr_full_v1.json` — trained on 2018–2023 national ASOS+HRRR data
- `models/calibrator_platt_v2.pkl` — Platt-calibrated, threshold=0.17, recall=72%, precision=36%

If a future retrain produces a better model, the swap is:
```bash
cp /path/to/new_model.json models/xgb_asos_hrrr_full_v1.json
cp /path/to/new_calibrator.pkl models/calibrator_platt_v2.pkl
python3 scripts/run_live_forecast.py  # verify pipeline still runs
git add models/ && git commit -m "model: update to vN" && git push
```
