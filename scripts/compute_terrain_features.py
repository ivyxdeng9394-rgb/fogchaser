"""
Compute terrain features from DEM and NLCD. Saves normalized feature rasters.
Run after terrain_setup.py.
"""
import numpy as np
import rasterio
from scipy.ndimage import uniform_filter
from pathlib import Path

Path("data/processed").mkdir(parents=True, exist_ok=True)


def load_raster(path):
    """Load a raster, return (array, profile). Nodata -> NaN for floats."""
    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        nodata = src.nodata
        profile = src.profile.copy()
    if nodata is not None:
        arr[arr == nodata] = np.nan
    return arr, profile


def save_raster(arr, profile, path):
    """Save float32 array as single-band GeoTIFF, NaN -> nodata=-9999."""
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
    Uses count-corrected uniform_filter to handle NaN edges correctly.
    """
    kernel_size = 2 * radius_pixels + 1
    nan_mask = np.isnan(dem)
    valid_mask = (~nan_mask).astype(np.float32)
    filled = np.where(nan_mask, 0.0, dem).astype(np.float32)

    # Sum of valid elevation values in the neighborhood
    sum_vals = uniform_filter(filled, size=kernel_size) * (kernel_size ** 2)
    # Count of valid cells in the neighborhood
    count_vals = uniform_filter(valid_mask, size=kernel_size) * (kernel_size ** 2)

    # Count-corrected mean: only average over valid neighbors
    neighborhood_mean = np.where(count_vals > 0, sum_vals / count_vals, np.nan)

    tpi = dem - neighborhood_mean
    tpi[nan_mask] = np.nan
    return tpi


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
    # 500m radius = 1 pixel  -> kernel_size = 3
    # 2km radius  = 4 pixels -> kernel_size = 9
    tpi_500m = compute_tpi(dem, radius_pixels=1)
    tpi_2km  = compute_tpi(dem, radius_pixels=4)

    tpi_multi = 0.6 * tpi_500m + 0.4 * tpi_2km
    tpi_norm  = percentile_normalize(tpi_multi)

    # Report spread before saving (useful diagnostic)
    spread = np.nanpercentile(tpi_norm, 75) - np.nanpercentile(tpi_norm, 25)
    print(f"  TPI IQR spread (p75-p25): {spread:.4f}")

    save_raster(tpi_norm, profile, output_path)
    print(f"  TPI range: [{np.nanmin(tpi_norm):.3f}, {np.nanmax(tpi_norm):.3f}]")
    return output_path


def compute_impervious_feature(
        imperv_path="data/processed/nlcd_impervious_500m.tif",
        output_path="data/processed/imperv_norm.tif"):
    """
    Impervious fraction (0-100 -> 0-1), inverted so high impervious = low value.
    Urban heat island suppresses radiation fog.
    """
    print("Computing impervious fraction feature...")
    arr, profile = load_raster(imperv_path)

    # NLCD impervious is 0-100 (percent); convert to 0-1 fraction
    frac = arr / 100.0
    frac = np.clip(frac, 0, 1)

    # Invert: high impervious -> low fog weight
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
      Open Water:             11
      Woody Wetlands:         90
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


def compute_cos_aspect(dem_path="data/processed/dem_500m.tif",
                       output_path="data/processed/cos_aspect.tif"):
    """
    Compute cosine of terrain aspect (slope direction).
    north-facing = +1 (less sun, cooler, fog-favoring)
    south-facing = -1 (more sun, warmer)
    flat terrain = 0 (NaN aspect -> 0)

    Uses central differences on the DEM to estimate N-S gradient.
    """
    print("Computing cosine aspect...")
    dem, profile = load_raster(dem_path)

    # N-S gradient (dy): positive = terrain slopes upward toward north
    dy, dx = np.gradient(np.nan_to_num(dem, nan=0))

    # Aspect angle: arctan2(-dy, dx) gives angle from east CCW
    aspect_rad = np.arctan2(-dy, dx)

    # Convert to compass bearing (0=north, clockwise)
    bearing = (np.pi / 2 - aspect_rad) % (2 * np.pi)

    # Cosine: north (bearing=0) -> cos(0) = +1, south (bearing=pi) -> cos(pi) = -1
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


if __name__ == "__main__":
    compute_tpi_multi()
    compute_impervious_feature()
    compute_surface_moisture()
    compute_cos_aspect()
    print("All terrain features done.")
