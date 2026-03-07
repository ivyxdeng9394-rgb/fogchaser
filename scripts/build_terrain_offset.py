"""
Combines normalized terrain features into the static terrain offset grid.
Run after compute_terrain_features.py.
"""
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
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
OFFSET_SCALE = 0.5   # multiplier to cap range at +/-0.5 log-odds


def load_band(path):
    with rasterio.open(path) as src:
        arr = src.read(1).astype(np.float32)
        profile = src.profile.copy()
    arr[arr == -9999] = np.nan
    return arr, profile


def align_to_reference(src_path, ref_profile):
    """Reproject/resample src_path onto the reference grid using bilinear resampling."""
    with rasterio.open(src_path) as src:
        dst_arr = np.empty(
            (ref_profile["height"], ref_profile["width"]), dtype=np.float32
        )
        reproject(
            source=rasterio.band(src, 1),
            destination=dst_arr,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            resampling=Resampling.bilinear,
            src_nodata=-9999.0,
            dst_nodata=np.nan,
        )
    return dst_arr


def build_terrain_offset():
    print("Building terrain offset grid...")

    # Load TPI as the reference grid (highest weight, largest extent)
    tpi, prof = load_band("data/processed/tpi_multi_norm.tif")
    prof.update(dtype="float32", count=1, nodata=-9999.0)

    # Align all other layers to the TPI grid
    print(f"  Reference grid: {prof['height']}x{prof['width']}")

    def load_aligned(path):
        arr, p = load_band(path)
        if arr.shape == (prof["height"], prof["width"]):
            return arr
        print(f"  Resampling {path} from {arr.shape} -> ({prof['height']},{prof['width']})")
        return align_to_reference(path, prof)

    imperv   = load_aligned("data/processed/imperv_norm.tif")
    moisture = load_aligned("data/processed/surface_moisture_norm.tif")
    aspect   = load_aligned("data/processed/cos_aspect.tif")

    # Weighted sum — each feature is already normalized to [-1,+1]
    # TPI is negated: valley = negative TPI = fog-favoring (cold air pooling)
    offset = OFFSET_SCALE * (
        WEIGHTS["tpi"]      * (-tpi)   +
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
