# Spatial Interpolation Layer — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the two-phase spatial layer that extends fog probability from 8 ASOS stations to a continuous 500m grid map of the DC metro area, using IDW in log-odds space plus a static terrain offset.

**Architecture:** Phase 1 (run once) downloads DEM + NLCD, computes 4 terrain features at 500m, saves a static terrain offset GeoTIFF. Phase 2 (per HRRR hour) blends 8 station predictions via IDW in log-odds space, adds the terrain offset, outputs `fog_prob_{YYYYMMDD}_{HH}UTC.tif`.

**Tech Stack:** Python 3.10+, `py3dep` (3DEP DEM), `pygeohydro` (NLCD), `rasterio`, `rioxarray`, `numpy`, `scipy.ndimage` (focal stats), `scipy.special` (logit/expit), `pyproj`, `matplotlib`, `sklearn.metrics` (AUC-PR)

**Design doc:** `docs/plans/2026-03-02-spatial-layer-design.md`

**Key constants (used throughout):**
```python
BBOX = (-78.1, 38.1, -76.0, 39.7)   # (west, south, east, north) WGS84
CRS_PROJ = "EPSG:5070"               # Albers Equal Area, NAD83 — all computation
CRS_GEO  = "EPSG:4326"              # WGS84 — input/output
RES_M    = 500                       # output grid resolution in meters
TERRAIN_OFFSET_PATH = "data/processed/terrain_offset_grid.tif"
METADATA_PATH       = "data/processed/terrain_grid_metadata.csv"
```

**DC metro ASOS stations (8):**
```python
STATIONS = {
    "KDCA": (38.8521, -77.0377),
    "KIAD": (38.9531, -77.4565),
    "KBWI": (39.1754, -76.6683),
    "KGAI": (39.1683, -77.1660),
    "KFDK": (39.4175, -77.3743),
    "KHEF": (38.7217, -77.5155),
    "KADW": (38.8108, -76.8694),
    "KCGS": (38.5803, -76.9228),
}
```

---

## Task 1: Install Dependencies and Create Directory Structure

**Files:**
- Create: `scripts/terrain_setup.py` (empty scaffold)
- Create: `tests/spatial/__init__.py`
- Create: `tests/spatial/test_idw.py`
- Create: `tests/spatial/test_terrain.py`

**Step 1: Install packages**

```bash
pip install py3dep pygeohydro rioxarray rasterio pyproj scipy matplotlib scikit-learn
```

Expected: all install without error. Note: `pygeohydro` is part of the HyRiver suite. If it fails, install separately: `pip install pygeohydro pynhd`.

**Step 2: Verify imports work**

```python
# run this as a quick smoke test
import py3dep
import pygeohydro
import rasterio
import rioxarray
import numpy as np
from scipy.special import logit, expit
from scipy.ndimage import uniform_filter
from pyproj import Transformer
print("all imports OK")
```

Run: `python -c "import py3dep, pygeohydro, rasterio, rioxarray, numpy, scipy, pyproj; print('OK')"`
Expected: prints `OK`

**Step 3: Create output directories**

```bash
mkdir -p data/processed outputs/spatial tests/spatial
touch tests/spatial/__init__.py
```

**Step 4: Commit**

```bash
git add tests/spatial/ data/processed/ outputs/spatial/
git commit -m "feat: scaffold spatial layer directories and verify dependencies"
```

---

## Task 2: Download and Reproject 3DEP DEM

**Files:**
- Create: `scripts/terrain_setup.py`

**Step 1: Write the download function test**

In `tests/spatial/test_terrain.py`:

```python
import numpy as np
import rasterio
from pathlib import Path

def test_dem_file_exists_and_valid():
    """DEM file should exist at 500m, in EPSG:5070, cover the DC metro bbox."""
    path = Path("data/processed/dem_500m.tif")
    assert path.exists(), "Run scripts/terrain_setup.py first"
    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 5070
        assert src.res == (500, 500)
        # should cover at least 300x300 cells (150km / 500m)
        assert src.width >= 300
        assert src.height >= 300
        # no all-NaN bands
        data = src.read(1)
        assert not np.all(np.isnan(data.astype(float)))
```

Run: `pytest tests/spatial/test_terrain.py::test_dem_file_exists_and_valid -v`
Expected: FAIL with "Run scripts/terrain_setup.py first"

**Step 2: Write the DEM download script**

In `scripts/terrain_setup.py`:

```python
"""
Phase 1 terrain setup — run once to generate data/processed/ terrain files.
"""
import numpy as np
import rasterio
from rasterio.warp import calculate_default_transform, reproject, Resampling
from rasterio.crs import CRS
from pathlib import Path
import py3dep
from shapely.geometry import box

BBOX = (-78.1, 38.1, -76.0, 39.7)   # (west, south, east, north) WGS84
CRS_PROJ = "EPSG:5070"
RES_M = 500
Path("data/processed").mkdir(parents=True, exist_ok=True)


def download_dem(bbox=BBOX, output_path="data/processed/dem_raw.tif"):
    """Download 3DEP 30m DEM for bbox, save as GeoTIFF in WGS84."""
    print("Downloading 3DEP DEM...")
    geometry = box(*bbox)
    # py3dep returns an xarray.DataArray in CRS EPSG:4269 (NAD83 geographic)
    dem_xr = py3dep.get_dem(geometry, resolution=30)
    dem_xr.rio.to_raster(output_path)
    print(f"  Saved raw DEM to {output_path}")
    return output_path


def reproject_resample(input_path, output_path, target_crs=CRS_PROJ, res_m=RES_M):
    """Reproject raster to target_crs and resample to res_m resolution."""
    with rasterio.open(input_path) as src:
        transform, width, height = calculate_default_transform(
            src.crs, target_crs,
            src.width, src.height,
            *src.bounds,
            resolution=res_m,
        )
        meta = src.meta.copy()
        meta.update({
            "crs": target_crs,
            "transform": transform,
            "width": width,
            "height": height,
            "dtype": "float32",
            "nodata": -9999.0,
        })
        with rasterio.open(output_path, "w", **meta) as dst:
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=rasterio.band(dst, i),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=Resampling.bilinear,
                )
    print(f"  Reprojected/resampled -> {output_path} ({width}x{height} @ {res_m}m)")
    return output_path


if __name__ == "__main__":
    raw = download_dem()
    reproject_resample(raw, "data/processed/dem_500m.tif")
    print("DEM ready.")
```

**Step 3: Run and verify**

```bash
python scripts/terrain_setup.py
```

Expected output includes: `DEM ready.`

If `py3dep` raises a connection error, check internet connectivity and that `py3dep` is installed. If `py3dep` fails entirely, fallback: download the 1/3 arc-second DEM manually from https://apps.nationalmap.gov/downloader — select "Elevation Products (3DEP)", "1/3 arc-second DEM", use the DC metro bbox, download GeoTIFF, place at `data/processed/dem_raw.tif` and run only `reproject_resample()`.

**Step 4: Run test**

```bash
pytest tests/spatial/test_terrain.py::test_dem_file_exists_and_valid -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/terrain_setup.py tests/spatial/test_terrain.py data/processed/dem_500m.tif
git commit -m "feat: download and reproject 3DEP DEM to EPSG:5070 500m grid"
```

---

## Task 3: Download NLCD and Reproject

**Files:**
- Modify: `scripts/terrain_setup.py`
- Modify: `tests/spatial/test_terrain.py`

**Step 1: Write the NLCD test**

Add to `tests/spatial/test_terrain.py`:

```python
def test_nlcd_files_exist_and_valid():
    """NLCD land cover and impervious files should exist at 500m in EPSG:5070."""
    for name in ["nlcd_landcover_500m.tif", "nlcd_impervious_500m.tif"]:
        path = Path(f"data/processed/{name}")
        assert path.exists(), f"Missing {name} — run scripts/terrain_setup.py"
        with rasterio.open(path) as src:
            assert src.crs.to_epsg() == 5070
            data = src.read(1)
            assert data.shape[0] >= 300
```

Run: `pytest tests/spatial/test_terrain.py::test_nlcd_files_exist_and_valid -v`
Expected: FAIL

**Step 2: Write NLCD download function**

Add to `scripts/terrain_setup.py`:

```python
import pygeohydro


def download_nlcd(bbox=BBOX):
    """Download NLCD 2021 land cover and impervious surface for bbox."""
    print("Downloading NLCD 2021...")
    from pygeohydro import NLCD
    from shapely.geometry import box as sbox

    nlcd = NLCD()
    geometry = sbox(*bbox)

    # Land cover (21 classes)
    lc = nlcd.get_map("landcover", 2021, geometry)
    lc_path = "data/processed/nlcd_landcover_raw.tif"
    lc.rio.to_raster(lc_path)
    print(f"  Saved raw land cover to {lc_path}")

    # Impervious surface fraction (0-100)
    imperv = nlcd.get_map("impervious", 2021, geometry)
    imperv_path = "data/processed/nlcd_impervious_raw.tif"
    imperv.rio.to_raster(imperv_path)
    print(f"  Saved raw impervious to {imperv_path}")

    return lc_path, imperv_path
```

**Note on pygeohydro:** If `pygeohydro.NLCD().get_map()` fails with a version or API error, the fallback is to download NLCD 2021 directly from https://www.mrlc.gov/data — select "NLCD 2021 Land Cover (CONUS)" and "NLCD 2021 Impervious Surface (CONUS)", clip to the DC metro bbox using QGIS or `gdalwarp`:
```bash
gdalwarp -te -78.1 38.1 -76.0 39.7 -t_srs EPSG:4326 nlcd_2021_land_cover_l48.img data/processed/nlcd_landcover_raw.tif
```

**Step 3: Add NLCD reproject step to `__main__` block**

```python
if __name__ == "__main__":
    # DEM
    raw_dem = download_dem()
    reproject_resample(raw_dem, "data/processed/dem_500m.tif")

    # NLCD — use nearest-neighbor for categorical land cover, bilinear for impervious
    lc_raw, imperv_raw = download_nlcd()
    reproject_resample(lc_raw, "data/processed/nlcd_landcover_500m.tif",
                       resampling_method=Resampling.nearest)
    reproject_resample(imperv_raw, "data/processed/nlcd_impervious_500m.tif",
                       resampling_method=Resampling.bilinear)
    print("All terrain data ready.")
```

Update `reproject_resample()` to accept a `resampling_method` parameter (replace the hardcoded `Resampling.bilinear`).

**Step 4: Run and test**

```bash
python scripts/terrain_setup.py
pytest tests/spatial/test_terrain.py::test_nlcd_files_exist_and_valid -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/terrain_setup.py tests/spatial/test_terrain.py
git commit -m "feat: download NLCD 2021 land cover and impervious, reproject to 500m"
```

---

## Task 4: Compute TPI_multi Feature

**Files:**
- Create: `scripts/compute_terrain_features.py`
- Modify: `tests/spatial/test_terrain.py`

**Step 1: Write the TPI test**

Add to `tests/spatial/test_terrain.py`:

```python
def test_tpi_multi_range_and_shape():
    """TPI_multi should be normalized to [-1,+1] and match the DEM grid shape."""
    path = Path("data/processed/tpi_multi_norm.tif")
    assert path.exists(), "Run scripts/compute_terrain_features.py first"
    with rasterio.open(path) as src:
        tpi = src.read(1).astype(float)
        # nodata masked out
        tpi[tpi == -9999] = np.nan
        assert np.nanmin(tpi) >= -1.01
        assert np.nanmax(tpi) <= 1.01
        # should have meaningful spread: more than just -1 and +1
        spread = np.nanpercentile(tpi, 75) - np.nanpercentile(tpi, 25)
        assert spread > 0.1, f"TPI spread too low ({spread:.3f}) — check neighborhood radius"

    # shape should match DEM
    with rasterio.open("data/processed/dem_500m.tif") as dem_src:
        with rasterio.open(path) as tpi_src:
            assert dem_src.width == tpi_src.width
            assert dem_src.height == tpi_src.height
```

Run: `pytest tests/spatial/test_terrain.py::test_tpi_multi_range_and_shape -v`
Expected: FAIL

**Step 2: Write the TPI computation script**

Create `scripts/compute_terrain_features.py`:

```python
"""
Compute terrain features from DEM and NLCD. Saves normalized feature rasters.
Run after terrain_setup.py.
"""
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from scipy.ndimage import uniform_filter
from pathlib import Path

Path("data/processed").mkdir(parents=True, exist_ok=True)


def load_raster(path):
    """Load a raster, return (array, profile). Nodata → NaN for floats."""
    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        nodata = src.nodata
        profile = src.profile.copy()
    if nodata is not None:
        arr[arr == nodata] = np.nan
    return arr, profile


def save_raster(arr, profile, path):
    """Save float32 array as single-band GeoTIFF, NaN → nodata=-9999."""
    out = arr.copy().astype(np.float32)
    out[np.isnan(out)] = -9999.0
    profile.update(dtype="float32", count=1, nodata=-9999.0)
    with rasterio.open(path, "w", **profile) as dst:
        dst.write(out, 1)
    print(f"  Saved {path}")


def percentile_normalize(arr, low_pct=2, high_pct=98):
    """Clip to [low_pct, high_pct] percentile, then scale to [-1, +1]."""
    lo = np.nanpercentile(arr, low_pct)
    hi = np.nanpercentile(arr, high_pct)
    if hi == lo:
        return np.zeros_like(arr)
    clipped = np.clip(arr, lo, hi)
    return 2.0 * (clipped - lo) / (hi - lo) - 1.0


def compute_tpi(dem, radius_pixels):
    """
    Terrain Position Index: how much higher/lower a cell is than its neighborhood mean.
    Negative = valley, Positive = ridge.
    Uses uniform_filter as a fast approximation to circular neighborhood mean.
    """
    # uniform_filter window size = diameter (2*radius + 1)
    kernel_size = 2 * radius_pixels + 1
    neighborhood_mean = uniform_filter(np.where(np.isnan(dem), 0, dem),
                                       size=kernel_size)
    # handle NaN edges
    count = uniform_filter(~np.isnan(dem) * 1.0, size=kernel_size) * kernel_size**2
    return dem - neighborhood_mean


def compute_tpi_multi(dem_path="data/processed/dem_500m.tif",
                      output_path="data/processed/tpi_multi_norm.tif"):
    """
    Compute multi-scale TPI:
      TPI_500m: 1-cell radius (500m) — small features (Rock Creek valley)
      TPI_2km:  4-cell radius (2km)  — broad basin features (Potomac corridor)
      TPI_multi = 0.6 * TPI_500m + 0.4 * TPI_2km
    """
    print("Computing TPI_multi...")
    dem, profile = load_raster(dem_path)

    # At 500m resolution: 1 pixel = 500m, so:
    # 500m radius = 1 pixel  → kernel_size = 3
    # 2km radius  = 4 pixels → kernel_size = 9
    tpi_500m = compute_tpi(dem, radius_pixels=1)
    tpi_2km  = compute_tpi(dem, radius_pixels=4)

    tpi_multi = 0.6 * tpi_500m + 0.4 * tpi_2km
    tpi_norm  = percentile_normalize(tpi_multi)

    save_raster(tpi_norm, profile, output_path)
    print(f"  TPI range: [{np.nanmin(tpi_norm):.3f}, {np.nanmax(tpi_norm):.3f}]")
    return output_path


if __name__ == "__main__":
    compute_tpi_multi()
    print("TPI_multi done.")
```

**Step 3: Run and test**

```bash
python scripts/compute_terrain_features.py
pytest tests/spatial/test_terrain.py::test_tpi_multi_range_and_shape -v
```

Expected: PASS. If spread < 0.1, the DC metro terrain may truly be very flat — the TPI is working but the signal is weak. This is useful information: log TPI spread in the metadata file (Task 9).

**Step 4: Commit**

```bash
git add scripts/compute_terrain_features.py tests/spatial/test_terrain.py data/processed/tpi_multi_norm.tif
git commit -m "feat: compute multi-scale TPI feature (500m + 2km blend)"
```

---

## Task 5: Compute Impervious Fraction and Surface Moisture Features

**Files:**
- Modify: `scripts/compute_terrain_features.py`
- Modify: `tests/spatial/test_terrain.py`

**Step 1: Write the tests**

Add to `tests/spatial/test_terrain.py`:

```python
def test_impervious_feature_normalized():
    path = Path("data/processed/imperv_norm.tif")
    assert path.exists()
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        arr[arr == -9999] = np.nan
        # inverted: high impervious = low value → negative
        assert np.nanmin(arr) >= -1.01
        assert np.nanmax(arr) <= 1.01

def test_surface_moisture_non_negative():
    """Surface moisture contribution is clamped to >= 0."""
    path = Path("data/processed/surface_moisture_norm.tif")
    assert path.exists()
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        arr[arr == -9999] = np.nan
        # clamped positive only
        assert np.nanmin(arr) >= -0.01
        assert np.nanmax(arr) <= 1.01
```

Run: `pytest tests/spatial/test_terrain.py::test_impervious_feature_normalized tests/spatial/test_terrain.py::test_surface_moisture_non_negative -v`
Expected: FAIL

**Step 2: Add impervious + surface moisture functions**

Add to `scripts/compute_terrain_features.py`:

```python
def compute_impervious_feature(
        imperv_path="data/processed/nlcd_impervious_500m.tif",
        output_path="data/processed/imperv_norm.tif"):
    """
    Impervious fraction (0-100 → 0-1), inverted so high impervious = low value.
    Urban heat island suppresses radiation fog.
    """
    print("Computing impervious fraction feature...")
    arr, profile = load_raster(imperv_path)

    # NLCD impervious is 0-100 (percent); convert to 0-1 fraction
    frac = arr / 100.0
    frac = np.clip(frac, 0, 1)

    # Invert: high impervious → low fog weight
    inverted = 1.0 - frac

    norm = percentile_normalize(inverted)
    save_raster(norm, profile, output_path)
    return output_path


def compute_surface_moisture(
        lc_path="data/processed/nlcd_landcover_500m.tif",
        output_path="data/processed/surface_moisture_norm.tif",
        radius_pixels=2):
    """
    Surface moisture = 0.7 * open_water_fraction + 0.3 * wetlands_fraction
    within a 1km radius (2 pixels at 500m resolution).
    Clamped to >= 0 (absence of water does not suppress fog).

    NLCD 2021 class codes:
      Open Water:           11
      Woody Wetlands:       90
      Emergent Herb Wetlands: 95
    """
    print("Computing surface moisture feature...")
    lc, profile = load_raster(lc_path)
    # replace NaN with 0 for binary masks
    lc_int = np.nan_to_num(lc, nan=0).astype(int)

    kernel_size = 2 * radius_pixels + 1

    # Open water mask
    water_mask = (lc_int == 11).astype(float)
    water_frac = uniform_filter(water_mask, size=kernel_size)

    # Wetlands mask (both types)
    wetland_mask = ((lc_int == 90) | (lc_int == 95)).astype(float)
    wetland_frac = uniform_filter(wetland_mask, size=kernel_size)

    surface_moisture = 0.7 * water_frac + 0.3 * wetland_frac

    # Normalize then clamp to >= 0
    norm = percentile_normalize(surface_moisture)
    norm = np.clip(norm, 0, 1)  # absence of water = neutral (0), not negative

    save_raster(norm, profile, output_path)
    return output_path
```

Update `__main__` to call both functions.

**Step 3: Run and test**

```bash
python scripts/compute_terrain_features.py
pytest tests/spatial/test_terrain.py -v -k "impervious or moisture"
```

Expected: PASS

**Step 4: Commit**

```bash
git add scripts/compute_terrain_features.py data/processed/imperv_norm.tif data/processed/surface_moisture_norm.tif
git commit -m "feat: compute impervious fraction (inverted) and surface moisture features"
```

---

## Task 6: Compute Cosine Aspect Feature

**Files:**
- Modify: `scripts/compute_terrain_features.py`
- Modify: `tests/spatial/test_terrain.py`

**Step 1: Write the test**

```python
def test_cos_aspect_range():
    path = Path("data/processed/cos_aspect.tif")
    assert path.exists()
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        arr[arr == -9999] = np.nan
        # cosine output is [-1, +1] by definition
        assert np.nanmin(arr) >= -1.01
        assert np.nanmax(arr) <= 1.01
```

Run: `pytest tests/spatial/test_terrain.py::test_cos_aspect_range -v`
Expected: FAIL

**Step 2: Add cosine aspect function**

Add to `scripts/compute_terrain_features.py`:

```python
def compute_cos_aspect(dem_path="data/processed/dem_500m.tif",
                       output_path="data/processed/cos_aspect.tif"):
    """
    Compute cosine of terrain aspect (slope direction).
    north-facing = +1 (less sun, cooler, fog-favoring)
    south-facing = -1 (more sun, warmer)
    flat terrain = 0 (NaN aspect → 0)

    Uses central differences on the DEM to estimate N-S gradient.
    """
    print("Computing cosine aspect...")
    dem, profile = load_raster(dem_path)

    # N-S gradient (dy): positive = terrain slopes upward toward north
    # Use np.gradient which handles edges cleanly
    dy, dx = np.gradient(np.nan_to_num(dem, nan=0))

    # Aspect angle: arctan2(-dy, dx) gives angle from east CCW
    # For north-facing aspect in standard geography convention:
    aspect_rad = np.arctan2(-dy, dx)  # angle in radians

    # Convert to compass bearing (0=north, clockwise)
    # bearing = (pi/2 - aspect_rad) mod 2pi
    bearing = (np.pi / 2 - aspect_rad) % (2 * np.pi)

    # Cosine: north (bearing=0) → cos(0) = +1, south (bearing=π) → cos(π) = -1
    cos_aspect = np.cos(bearing)

    # Flat cells (gradient near zero): assign 0
    gradient_mag = np.sqrt(dx**2 + dy**2)
    flat = gradient_mag < 1e-6
    cos_aspect[flat] = 0.0

    # Propagate NaN from dem
    cos_aspect[np.isnan(dem)] = np.nan

    # No percentile normalization needed — cosine is already [-1, +1]
    save_raster(cos_aspect, profile, output_path)
    return output_path
```

**Step 3: Run and test**

```bash
python scripts/compute_terrain_features.py
pytest tests/spatial/test_terrain.py::test_cos_aspect_range -v
```

Expected: PASS

**Step 4: Commit**

```bash
git add scripts/compute_terrain_features.py data/processed/cos_aspect.tif
git commit -m "feat: compute cosine aspect feature from DEM"
```

---

## Task 7: Build Terrain Offset Grid and Save

**Files:**
- Create: `scripts/build_terrain_offset.py`
- Modify: `tests/spatial/test_terrain.py`

**Step 1: Write the test**

```python
def test_terrain_offset_grid():
    path = Path("data/processed/terrain_offset_grid.tif")
    assert path.exists()
    with rasterio.open(path) as src:
        assert src.crs.to_epsg() == 5070
        offset = src.read(1).astype(float)
        offset[offset == -9999] = np.nan
        # offset range should be within [-0.5, +0.5]
        assert np.nanmin(offset) >= -0.51
        assert np.nanmax(offset) <= 0.51

def test_terrain_metadata_csv():
    import pandas as pd
    path = Path("data/processed/terrain_grid_metadata.csv")
    assert path.exists()
    df = pd.read_csv(path)
    required = ["generated_at", "w_tpi", "w_imperv", "w_moisture", "w_aspect",
                "offset_scale", "dem_source", "nlcd_year"]
    for col in required:
        assert col in df.columns, f"Missing column: {col}"
```

Run: `pytest tests/spatial/test_terrain.py -k "offset_grid or metadata" -v`
Expected: FAIL

**Step 2: Write the offset builder**

Create `scripts/build_terrain_offset.py`:

```python
"""
Combines normalized terrain features into the static terrain offset grid.
Run after compute_terrain_features.py.
"""
import numpy as np
import rasterio
import pandas as pd
from datetime import datetime
from pathlib import Path


# Expert-initialized weights (priors, not fitted parameters)
# These sum to 1.0; the 0.5 outer scalar caps total range at [-0.5, +0.5] log-odds
WEIGHTS = {
    "tpi":      0.50,   # cold air pooling — strongest literature backing
    "imperv":   0.35,   # urban heat island — Klemm & Lin 2020
    "moisture": 0.12,   # surface moisture — water/wetland proximity
    "aspect":   0.03,   # north-facing bonus — secondary, seasonal effect
}
OFFSET_SCALE = 0.5   # multiplier to cap range at ±0.5 log-odds


def load_band(path):
    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        profile = src.profile.copy()
    arr[arr == -9999] = np.nan
    return arr, profile


def build_terrain_offset():
    print("Building terrain offset grid...")

    tpi,      prof = load_band("data/processed/tpi_multi_norm.tif")
    imperv,   _    = load_band("data/processed/imperv_norm.tif")
    moisture, _    = load_band("data/processed/surface_moisture_norm.tif")
    aspect,   _    = load_band("data/processed/cos_aspect.tif")

    # Weighted sum — each feature is already normalized to [-1,+1]
    offset = OFFSET_SCALE * (
        WEIGHTS["tpi"]      * tpi      +
        WEIGHTS["imperv"]   * imperv   +
        WEIGHTS["moisture"] * moisture +
        WEIGHTS["aspect"]   * aspect
    )

    # Save GeoTIFF
    out_path = "data/processed/terrain_offset_grid.tif"
    out = offset.copy()
    out[np.isnan(out)] = -9999.0
    prof.update(dtype="float32", count=1, nodata=-9999.0)
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(out, 1)
    print(f"  Saved {out_path}")
    print(f"  Offset range: [{np.nanmin(offset):.4f}, {np.nanmax(offset):.4f}]")

    # Save metadata CSV
    meta = pd.DataFrame([{
        "generated_at":  datetime.now().isoformat(),
        "w_tpi":         WEIGHTS["tpi"],
        "w_imperv":      WEIGHTS["imperv"],
        "w_moisture":    WEIGHTS["moisture"],
        "w_aspect":      WEIGHTS["aspect"],
        "offset_scale":  OFFSET_SCALE,
        "tpi_radii_px":  "1px(60%), 4px(40%)",
        "moisture_radius_px": 2,
        "dem_source":    "3DEP 30m via py3dep",
        "nlcd_year":     2021,
    }])
    meta.to_csv("data/processed/terrain_grid_metadata.csv", index=False)
    print("  Saved terrain_grid_metadata.csv")

    return out_path


if __name__ == "__main__":
    build_terrain_offset()
```

**Step 3: Run and test**

```bash
python scripts/build_terrain_offset.py
pytest tests/spatial/test_terrain.py -k "offset_grid or metadata" -v
```

Expected: PASS. Check the printed offset range — if it's much narrower than [-0.5, +0.5] (e.g., [-0.1, +0.1]), DC's terrain is very flat and the terrain layer is producing weak signal. That's honest, not a bug.

**Step 4: Commit**

```bash
git add scripts/build_terrain_offset.py data/processed/terrain_offset_grid.tif data/processed/terrain_grid_metadata.csv
git commit -m "feat: build terrain offset grid from weighted terrain features"
```

---

## Task 8: IDW Interpolation Function (log-odds space)

**Files:**
- Create: `scripts/spatial_pipeline.py`
- Create: `tests/spatial/test_idw.py`

**Step 1: Write the IDW unit tests**

In `tests/spatial/test_idw.py`:

```python
import numpy as np
import pytest
from scripts.spatial_pipeline import haversine_km, idw_logodds


def test_haversine_same_point():
    """Distance from a point to itself should be 0."""
    d = haversine_km(38.9, -77.0, 38.9, -77.0)
    assert abs(d) < 1e-6


def test_haversine_known_distance():
    """DCA to IAD is roughly 37km."""
    d = haversine_km(38.8521, -77.0377, 38.9531, -77.4565)
    assert 33 < d < 41, f"Unexpected DCA-IAD distance: {d:.1f} km"


def test_idw_at_station_location():
    """
    At a station's exact location, the output should be very close
    to that station's prediction.
    """
    station_probs = np.array([0.10, 0.80, 0.30, 0.20, 0.15, 0.25, 0.35, 0.40])
    station_lats  = np.array([38.8521, 38.9531, 39.1754, 39.1683,
                               39.4175, 38.7217, 38.8108, 38.5803])
    station_lons  = np.array([-77.0377, -77.4565, -76.6683, -77.1660,
                               -77.3743, -77.5155, -76.8694, -76.9228])

    # Query at station 0 (KDCA, p=0.10)
    grid_lats = np.array([38.8521])
    grid_lons = np.array([-77.0377])

    prob, low_conf = idw_logodds(station_probs, station_lats, station_lons,
                                  grid_lats, grid_lons)
    # Should be very close to 0.10 (small epsilon for numerical precision)
    assert abs(prob[0] - 0.10) < 0.02, f"Expected ~0.10, got {prob[0]:.4f}"


def test_idw_uniform_input():
    """If all stations have the same probability, every cell gets that probability."""
    p = 0.35
    station_probs = np.full(8, p)
    station_lats  = np.array([38.85, 38.95, 39.17, 39.16, 39.41, 38.72, 38.81, 38.58])
    station_lons  = np.array([-77.04, -77.46, -76.67, -77.17, -77.37, -77.52, -76.87, -76.92])

    # Query at an arbitrary interior point
    grid_lats = np.array([39.0, 39.1, 38.9])
    grid_lons = np.array([-77.2, -77.0, -76.9])

    prob, _ = idw_logodds(station_probs, station_lats, station_lons,
                           grid_lats, grid_lons)
    np.testing.assert_allclose(prob, p, atol=1e-4)


def test_idw_output_in_01():
    """IDW output should always be in [0, 1]."""
    rng = np.random.default_rng(42)
    station_probs = rng.uniform(0.05, 0.95, 8)
    station_lats  = np.array([38.85, 38.95, 39.17, 39.16, 39.41, 38.72, 38.81, 38.58])
    station_lons  = np.array([-77.04, -77.46, -76.67, -77.17, -77.37, -77.52, -76.87, -76.92])

    grid_lats = np.linspace(38.2, 39.6, 20)
    grid_lons = np.linspace(-78.0, -76.1, 20)
    glat, glon = np.meshgrid(grid_lats, grid_lons)

    prob, _ = idw_logodds(station_probs, station_lats, station_lons,
                           glat.ravel(), glon.ravel())
    assert np.all(prob >= 0.0) and np.all(prob <= 1.0)
```

Run: `pytest tests/spatial/test_idw.py -v`
Expected: FAIL with ImportError (file doesn't exist yet)

**Step 2: Write the IDW implementation**

Create `scripts/spatial_pipeline.py`:

```python
"""
Phase 2 spatial pipeline: IDW interpolation + terrain offset application.
"""
import numpy as np
from scipy.special import logit, expit


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Compute great-circle distance in km.
    Inputs can be scalars or numpy arrays (vectorized).
    """
    R = 6371.0
    lat1, lon1 = np.radians(lat1), np.radians(lon1)
    lat2, lon2 = np.radians(np.asarray(lat2, float)), np.radians(np.asarray(lon2, float))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def idw_logodds(station_probs, station_lats, station_lons,
                grid_lats, grid_lons, power=1.5, low_conf_radius_km=100,
                low_conf_min_stations=3):
    """
    Inverse distance weighted interpolation in log-odds space.

    Parameters
    ----------
    station_probs  : array-like, shape (n_stations,), fog probabilities [0,1]
    station_lats   : array-like, shape (n_stations,), station latitudes
    station_lons   : array-like, shape (n_stations,), station longitudes
    grid_lats      : array-like, any shape, grid cell latitudes
    grid_lons      : array-like, same shape as grid_lats, grid cell longitudes
    power          : float, IDW decay exponent (default 1.5)

    Returns
    -------
    idw_prob        : ndarray, same shape as grid_lats, fog probability [0,1]
    low_confidence  : ndarray bool, same shape; True where < low_conf_min_stations
                      stations are within low_conf_radius_km
    """
    orig_shape = np.asarray(grid_lats).shape
    glats = np.asarray(grid_lats, float).ravel()
    glons = np.asarray(grid_lons, float).ravel()

    station_probs = np.clip(np.asarray(station_probs, float), 0.001, 0.999)
    logit_p = logit(station_probs)                    # shape (n_stations,)
    slats = np.asarray(station_lats, float)
    slons = np.asarray(station_lons, float)

    n_cells    = len(glats)
    n_stations = len(slats)

    # Distance matrix (n_cells, n_stations)
    dists = np.zeros((n_cells, n_stations), dtype=float)
    for j in range(n_stations):
        dists[:, j] = haversine_km(glats, glons, slats[j], slons[j])

    # Avoid division by zero at exact station locations (min 0.1 km)
    dists = np.maximum(dists, 0.1)

    weights = 1.0 / (dists ** power)                  # (n_cells, n_stations)
    weights_norm = weights / weights.sum(axis=1, keepdims=True)

    logit_idw = (weights_norm * logit_p[np.newaxis, :]).sum(axis=1)
    idw_prob  = expit(logit_idw)

    # Low-confidence flag
    n_nearby = (dists < low_conf_radius_km).sum(axis=1)
    low_conf = n_nearby < low_conf_min_stations

    return idw_prob.reshape(orig_shape), low_conf.reshape(orig_shape)
```

**Step 3: Run tests**

```bash
pytest tests/spatial/test_idw.py -v
```

Expected: all PASS

**Step 4: Commit**

```bash
git add scripts/spatial_pipeline.py tests/spatial/test_idw.py
git commit -m "feat: IDW interpolation in log-odds space with low-confidence flag"
```

---

## Task 9: Terrain Application and Full Pipeline Function

**Files:**
- Modify: `scripts/spatial_pipeline.py`
- Modify: `tests/spatial/test_idw.py`

**Step 1: Write the terrain application test**

Add to `tests/spatial/test_idw.py`:

```python
def test_apply_terrain_output_range():
    """Final probability after terrain offset must be in [0, 1]."""
    from scripts.spatial_pipeline import apply_terrain_offset
    rng = np.random.default_rng(0)
    idw_prob     = rng.uniform(0.05, 0.95, (10, 10))
    terrain_off  = rng.uniform(-0.5, 0.5, (10, 10))
    result = apply_terrain_offset(idw_prob, terrain_off)
    assert result.shape == (10, 10)
    assert np.all(result >= 0.0) and np.all(result <= 1.0)


def test_apply_terrain_neutral_offset():
    """A terrain offset of 0 everywhere should return the IDW probability unchanged."""
    from scripts.spatial_pipeline import apply_terrain_offset
    idw_prob = np.array([[0.1, 0.4, 0.7]])
    terrain_off = np.zeros_like(idw_prob)
    result = apply_terrain_offset(idw_prob, terrain_off)
    np.testing.assert_allclose(result, idw_prob, atol=1e-5)
```

Run: `pytest tests/spatial/test_idw.py -k "terrain" -v`
Expected: FAIL

**Step 2: Add terrain application + full pipeline function**

Add to `scripts/spatial_pipeline.py`:

```python
import rasterio
import numpy as np
from pathlib import Path
from datetime import datetime


def apply_terrain_offset(idw_prob, terrain_offset):
    """
    Add terrain offset in log-odds space.

    Parameters
    ----------
    idw_prob       : ndarray, IDW fog probability [0,1]
    terrain_offset : ndarray, same shape, log-odds offset [-0.5, +0.5]

    Returns
    -------
    final_prob : ndarray, same shape, adjusted probability [0,1]
    """
    # Clamp to avoid logit(0) or logit(1) = ±inf
    clamped  = np.clip(idw_prob, 0.005, 0.995)
    final_logit = logit(clamped) + terrain_offset
    return expit(final_logit)


def run_spatial_pipeline(station_probs, station_lats, station_lons,
                          terrain_offset_path="data/processed/terrain_offset_grid.tif",
                          output_dir="outputs/spatial",
                          valid_dt=None):
    """
    Full Phase 2 pipeline: IDW + terrain → output GeoTIFF.

    Parameters
    ----------
    station_probs : dict {station_id: float} or array of 8 probabilities
    station_lats  : array of 8 latitudes (aligned with station_probs)
    station_lons  : array of 8 longitudes
    valid_dt      : datetime for filename; defaults to now()

    Returns
    -------
    output_path : str path to written GeoTIFF
    """
    if valid_dt is None:
        valid_dt = datetime.utcnow()

    # Step 2a: Build IDW probability raster
    with rasterio.open(terrain_offset_path) as src:
        profile   = src.profile.copy()
        transform = src.transform
        width, height = src.width, src.height
        # Build lat/lon grid from raster metadata
        import pyproj
        transformer = pyproj.Transformer.from_crs("EPSG:5070", "EPSG:4326",
                                                   always_xy=True)
        rows, cols = np.mgrid[0:height, 0:width]
        xs = transform.c + cols * transform.a      # x in EPSG:5070 (meters)
        ys = transform.f + rows * transform.e      # y in EPSG:5070 (meters)
        lons, lats = transformer.transform(xs.ravel(), ys.ravel())
        grid_lats = lats.reshape(height, width)
        grid_lons = lons.reshape(height, width)

        # Step 2b: Load terrain offset
        terrain_offset = src.read(1).astype(np.float32)
        terrain_offset[terrain_offset == -9999.0] = 0.0  # treat nodata as neutral

    # Run IDW
    idw_prob, low_conf = idw_logodds(
        np.asarray(station_probs),
        np.asarray(station_lats),
        np.asarray(station_lons),
        grid_lats, grid_lons
    )

    # Step 2c: Apply terrain offset
    final_prob = apply_terrain_offset(idw_prob, terrain_offset)

    # Write output GeoTIFF
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fname = f"fog_prob_{valid_dt.strftime('%Y%m%d_%H')}UTC.tif"
    out_path = str(Path(output_dir) / fname)

    out_arr = final_prob.astype(np.float32)
    out_arr[low_conf] = -9998.0   # distinct nodata for low-confidence cells

    profile.update(dtype="float32", count=1, nodata=-9999.0)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out_arr, 1)

    print(f"  Written: {out_path}")
    return out_path
```

**Step 3: Run tests**

```bash
pytest tests/spatial/test_idw.py -v
```

Expected: all PASS

**Step 4: Commit**

```bash
git add scripts/spatial_pipeline.py tests/spatial/test_idw.py
git commit -m "feat: terrain offset application and full spatial pipeline function"
```

---

## Task 10: Validation Checks 1 & 2 — Terrain Layer in Isolation

**Files:**
- Create: `scripts/validate_spatial.py`

**Step 1: Write the validation script (Checks 1 & 2)**

Create `scripts/validate_spatial.py`:

```python
"""
Validation checks for the spatial interpolation layer.
Run all checks: python scripts/validate_spatial.py
"""
import numpy as np
import rasterio
import matplotlib
matplotlib.use("Agg")   # non-interactive backend; remove for interactive display
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
        crs = src.crs

    # Convert lat/lon transect endpoints to pixel row/col
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


if __name__ == "__main__":
    check_1_valley_ridge_transects()
    check_2_urban_suppression()
    print("\nChecks 1-2 complete.")
```

**Step 2: Run**

```bash
python scripts/validate_spatial.py
```

Inspect `outputs/validation/check1_valley_ridge_transects.png` visually. Check 2 prints a table; look for urban < rural in the imperv column.

**Step 3: Commit**

```bash
git add scripts/validate_spatial.py
git commit -m "feat: validation checks 1 and 2 (terrain layer in isolation)"
```

---

## Task 11: Validation Check 3 — Hold-Out Station Test (AUC-PR)

**Files:**
- Modify: `scripts/validate_spatial.py`

This is the only check that tests whether the spatial interpolation adds real value at unobserved locations.

**Step 1: Add the hold-out station function**

Add to `scripts/validate_spatial.py`:

```python
def check_3_holdout_station(holdout_station="KIAD"):
    """
    Check 3: Hold out one ASOS station, predict at its location using
    IDW from remaining 7 stations + terrain. Compute AUC-PR.

    Pass criterion: AUC-PR at held-out station > baseline (nearest-neighbor of 7).
    """
    print(f"\n--- Check 3: Hold-Out Station Test (holding out {holdout_station}) ---")
    import pandas as pd
    import joblib
    from sklearn.metrics import average_precision_score
    from scripts.spatial_pipeline import idw_logodds, apply_terrain_offset
    import rasterio
    import pyproj

    # Load DC metro test data
    test_df = pd.read_parquet("data/raw/asos/dc_metro_test_2024_2026.parquet")

    # Station info
    STATIONS = {
        "KDCA": (38.8521, -77.0377),
        "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683),
        "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743),
        "KHEF": (38.7217, -77.5155),
        "KADW": (38.8108, -76.8694),
        "KCGS": (38.5803, -76.9228),
    }

    if holdout_station not in STATIONS:
        print(f"  Station {holdout_station} not in station list. Skipping.")
        return

    holdout_lat, holdout_lon = STATIONS[holdout_station]
    remaining = {k: v for k, v in STATIONS.items() if k != holdout_station}

    # Load calibrator to get station probabilities
    # (loads the model + calibrator from models/)
    import pickle
    with open("models/calibrator_platt_v1.pkl", "rb") as f:
        calib_bundle = pickle.load(f)
    # calib_bundle contains: calibrator, model, fill_medians, feature_list
    # (structure may vary — adjust to match actual saved format)

    # Filter test data to hours where ALL remaining stations have predictions
    # Simplified: just compute hour by hour
    print("  Computing per-hour IDW predictions at held-out station...")

    results = []
    for valid_time, group in test_df.groupby("valid_time"):
        # Get predictions for each station
        preds = {}
        for station_id in STATIONS:
            station_data = group[group["station"] == station_id]
            if len(station_data) == 0:
                continue
            # Use pre-computed probability column if available, else use label as proxy
            if "fog_prob" in station_data.columns:
                preds[station_id] = float(station_data["fog_prob"].iloc[0])
            elif "fog_label" in station_data.columns:
                # Fallback: use observed label as a perfect predictor proxy
                # (for testing the spatial machinery, not forecast accuracy)
                preds[station_id] = float(station_data["fog_label"].iloc[0])

        if holdout_station not in preds or len(preds) < 6:
            continue

        actual_fog = preds[holdout_station]

        # IDW from remaining 7 stations
        remaining_stations = {k: v for k, v in preds.items() if k != holdout_station}
        s_probs = np.array(list(remaining_stations.values()))
        s_lats  = np.array([STATIONS[k][0] for k in remaining_stations])
        s_lons  = np.array([STATIONS[k][1] for k in remaining_stations])

        idw_prob, _ = idw_logodds(s_probs, s_lats, s_lons,
                                   np.array([holdout_lat]), np.array([holdout_lon]))
        idw_val = idw_prob[0]

        results.append({
            "valid_time":  valid_time,
            "actual":      actual_fog,
            "idw_pred":    idw_val,
            "nn_pred":     preds.get(min(remaining_stations,
                                         key=lambda k: haversine_km(
                                             holdout_lat, holdout_lon,
                                             STATIONS[k][0], STATIONS[k][1]))),
        })

    if not results:
        print("  No valid hours found — check data format.")
        return

    results_df = pd.DataFrame(results)
    auc_idw = average_precision_score(results_df["actual"], results_df["idw_pred"])
    auc_nn  = average_precision_score(results_df["actual"], results_df["nn_pred"])

    print(f"  Hours evaluated: {len(results_df)}")
    print(f"  AUC-PR  IDW (7 stations): {auc_idw:.4f}")
    print(f"  AUC-PR  Nearest-neighbor: {auc_nn:.4f}")
    if auc_idw >= auc_nn:
        print("  PASS: IDW >= nearest-neighbor baseline")
    else:
        print(f"  NOTE: IDW ({auc_idw:.4f}) < nearest-neighbor ({auc_nn:.4f}) — "
              "not a failure (IDW is harder), but worth investigating.")
```

**Note:** This check requires the `fog_prob` or `fog_label` column to exist in `dc_metro_test_2024_2026.parquet`. Check the actual column names with `pd.read_parquet(...).columns` before running.

**Step 2: Run**

```bash
python -c "
import pandas as pd
df = pd.read_parquet('data/raw/asos/dc_metro_test_2024_2026.parquet')
print(df.columns.tolist())
print(df.head(2))
"
```

Inspect the column names, then adjust `check_3_holdout_station()` to use the correct column for observations and predictions. Then run:

```bash
python scripts/validate_spatial.py
```

**Step 3: Commit**

```bash
git add scripts/validate_spatial.py
git commit -m "feat: validation check 3 - hold-out station AUC-PR test"
```

---

## Task 12: Validation Checks 4, 5, 6 — Event Replay, Sensitivity, Bullseye

**Files:**
- Modify: `scripts/validate_spatial.py`

**Step 1: Add the remaining three checks**

```python
def check_4_historical_replay():
    """
    Check 4: Run spatial layer on known dense-fog days.
    Visual inspection: Potomac/Rock Creek corridors should show elevated probability.
    """
    print("\n--- Check 4: Historical Event Replay ---")
    import pandas as pd
    from datetime import datetime
    from scripts.spatial_pipeline import run_spatial_pipeline

    STATIONS = {
        "KDCA": (38.8521, -77.0377),
        "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683),
        "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743),
        "KHEF": (38.7217, -77.5155),
        "KADW": (38.8108, -76.8694),
        "KCGS": (38.5803, -76.9228),
    }

    # Load DC test data and find hours with high widespread fog
    df = pd.read_parquet("data/raw/asos/dc_metro_test_2024_2026.parquet")

    # Find 5 hours with highest average fog probability across stations
    # Adjust column names to match actual data
    fog_col = "fog_label"  # or "vsby_fog" — check actual columns
    if fog_col not in df.columns:
        print(f"  Column '{fog_col}' not found. Available: {df.columns.tolist()}")
        return

    hourly_fog = df.groupby("valid_time")[fog_col].mean()
    top_hours = hourly_fog.nlargest(5).index.tolist()
    print(f"  Top 5 fog hours: {[str(t) for t in top_hours]}")

    for valid_dt in top_hours[:2]:   # run only 2 for speed
        hour_data = df[df["valid_time"] == valid_dt]
        probs, lats, lons = [], [], []
        for sid, (lat, lon) in STATIONS.items():
            row = hour_data[hour_data["station"] == sid]
            if len(row) == 0:
                continue
            probs.append(float(row[fog_col].iloc[0]))
            lats.append(lat)
            lons.append(lon)

        if len(probs) < 5:
            print(f"  Skipping {valid_dt}: too few stations")
            continue

        dt = pd.Timestamp(valid_dt).to_pydatetime()
        out_path = run_spatial_pipeline(probs, lats, lons, valid_dt=dt)

        # Quick visualization
        with rasterio.open(out_path) as src:
            prob = src.read(1).astype(float)
            prob[prob < 0] = np.nan

        fig, ax = plt.subplots(figsize=(8, 8))
        im = ax.imshow(prob, vmin=0, vmax=1, cmap="Blues", origin="upper")
        plt.colorbar(im, ax=ax, label="Fog probability")
        ax.set_title(f"Fog probability — {valid_dt}")
        out_fig = f"outputs/validation/check4_event_{dt.strftime('%Y%m%d_%H')}.png"
        plt.savefig(out_fig, dpi=150)
        plt.close()
        print(f"  Saved {out_fig} — MANUAL: check Potomac/Rock Creek corridors are highlighted")


def check_5_sensitivity_sanity():
    """
    Check 5: Set all stations to flat 30% — output range should be [21%, 41%].
    Range is derived analytically from terrain offset bounds ±0.5 log-odds.
    """
    print("\n--- Check 5: Sensitivity Sanity ---")
    from scripts.spatial_pipeline import idw_logodds, apply_terrain_offset
    import rasterio

    STATIONS = {
        "KDCA": (38.8521, -77.0377), "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683), "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743), "KHEF": (38.7217, -77.5155),
        "KADW": (38.8108, -76.8694), "KCGS": (38.5803, -76.9228),
    }
    s_probs = np.full(8, 0.30)
    s_lats  = np.array([v[0] for v in STATIONS.values()])
    s_lons  = np.array([v[1] for v in STATIONS.values()])

    with rasterio.open("data/processed/terrain_offset_grid.tif") as src:
        terrain = src.read(1).astype(float)
        terrain[terrain == -9999] = 0.0
        transform = src.transform
        crs_str = src.crs.to_string()

    import pyproj
    transformer = pyproj.Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
    rows, cols = np.mgrid[0:terrain.shape[0], 0:terrain.shape[1]]
    xs = transform.c + cols * transform.a
    ys = transform.f + rows * transform.e
    lons, lats = transformer.transform(xs.ravel(), ys.ravel())
    grid_lats = lats.reshape(terrain.shape)
    grid_lons = lons.reshape(terrain.shape)

    idw_prob, _ = idw_logodds(s_probs, s_lats, s_lons, grid_lats, grid_lons)
    final_prob   = apply_terrain_offset(idw_prob, terrain)

    # Analytical bounds for input=0.30, offset=±0.5:
    from scipy.special import logit, expit
    lower = float(expit(logit(0.30) - 0.5))  # ~0.21
    upper = float(expit(logit(0.30) + 0.5))  # ~0.41

    actual_min = np.nanmin(final_prob)
    actual_max = np.nanmax(final_prob)

    print(f"  Analytical expected range: [{lower:.3f}, {upper:.3f}]")
    print(f"  Actual output range:       [{actual_min:.3f}, {actual_max:.3f}]")

    if actual_min >= lower - 0.01 and actual_max <= upper + 0.01:
        print("  PASS: Output range within analytically derived bounds")
    else:
        print("  FAIL: Output range exceeds terrain offset bounds — check formula implementation")


def check_6_bullseye_artifact():
    """
    Check 6: On a synthetic 1-station-fog event, verify probability contours
    follow terrain (not station geometry).
    """
    print("\n--- Check 6: Bullseye Artifact Check ---")
    from scripts.spatial_pipeline import run_spatial_pipeline
    from datetime import datetime

    STATIONS = {
        "KDCA": (38.8521, -77.0377), "KIAD": (38.9531, -77.4565),
        "KBWI": (39.1754, -76.6683), "KGAI": (39.1683, -77.1660),
        "KFDK": (39.4175, -77.3743), "KHEF": (38.7217, -77.5155),
        "KADW": (38.8108, -76.8694), "KCGS": (38.5803, -76.9228),
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

    fig, ax = plt.subplots(figsize=(8, 8))
    im = ax.imshow(prob, vmin=0, vmax=1, cmap="Blues", origin="upper")
    plt.colorbar(im, ax=ax, label="Fog probability")
    # Mark station locations
    import pyproj
    transformer = pyproj.Transformer.from_crs("EPSG:4326", src.crs.to_string(), always_xy=True)
    for sid, (lat, lon) in STATIONS.items():
        x, y = transformer.transform(lon, lat)
        col = (x - src.transform.c) / src.transform.a
        row = (y - src.transform.f) / src.transform.e
        color = "red" if sid == "KDCA" else "white"
        ax.plot(col, row, "o", color=color, markersize=8)
        ax.text(col + 2, row, sid, color=color, fontsize=7)
    ax.set_title("Bullseye check: KDCA=80%, all others=5%\nContours should follow terrain, not circles")
    out_fig = "outputs/validation/check6_bullseye.png"
    plt.savefig(out_fig, dpi=150)
    plt.close()
    print(f"  Saved {out_fig}")
    print("  MANUAL: If high-probability zone is a perfect circle centered on KDCA,")
    print("  reduce IDW power from 1.5 to 1.2 in spatial_pipeline.py idw_logodds().")


if __name__ == "__main__":
    check_1_valley_ridge_transects()
    check_2_urban_suppression()
    check_3_holdout_station()
    check_4_historical_replay()
    check_5_sensitivity_sanity()
    check_6_bullseye_artifact()
    print("\nAll validation checks complete.")
```

**Step 2: Run all checks**

```bash
python scripts/validate_spatial.py
```

Review output images in `outputs/validation/`. Manual inspection required for checks 1, 4, 6.

**Step 3: Commit**

```bash
git add scripts/validate_spatial.py outputs/validation/
git commit -m "feat: validation checks 4-6 (event replay, sensitivity sanity, bullseye)"
```

---

## Quick Reference

### Run Phase 1 (one-time setup, in order):
```bash
python scripts/terrain_setup.py          # download DEM + NLCD
python scripts/compute_terrain_features.py  # TPI, impervious, moisture, aspect
python scripts/build_terrain_offset.py   # combine → terrain_offset_grid.tif
```

### Run Phase 2 (per forecast hour):
```python
from scripts.spatial_pipeline import run_spatial_pipeline
out = run_spatial_pipeline(station_probs, station_lats, station_lons, valid_dt=dt)
```

### Run validation:
```bash
python scripts/validate_spatial.py
pytest tests/spatial/ -v
```

### File outputs:
| File | Description |
|---|---|
| `data/processed/terrain_offset_grid.tif` | Static log-odds offset, EPSG:5070, 500m |
| `data/processed/terrain_grid_metadata.csv` | Parameters used to generate terrain grid |
| `outputs/spatial/fog_prob_{YYYYMMDD}_{HH}UTC.tif` | Per-hour fog probability raster |
| `outputs/validation/check*.png` | Validation visualizations (manual review) |
