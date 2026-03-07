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


def reproject_resample(input_path, output_path, target_crs=CRS_PROJ, res_m=RES_M,
                       resampling_method=Resampling.bilinear):
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
                    resampling=resampling_method,
                )
    print(f"  Reprojected/resampled -> {output_path} ({width}x{height} @ {res_m}m)")
    return output_path


def download_nlcd(bbox=BBOX):
    """Download NLCD 2021 land cover and impervious surface for bbox."""
    print("Downloading NLCD 2021...")
    from pygeohydro.nlcd import NLCD
    import geopandas as gpd

    # Build a one-row GeoDataFrame with the bbox polygon (required by the WMS API)
    geometry = gpd.GeoSeries([box(*bbox)], crs="EPSG:4326")
    geo_df = gpd.GeoDataFrame(geometry=geometry, crs="EPSG:4326")

    # Request only the two layers we need, at native 30m resolution
    nlcd_cover = NLCD(years={"cover": [2021]})
    ds_cover = nlcd_cover.get_map(geo_df.geometry.iloc[0], 30)
    lc_da = ds_cover["cover_2021"]
    lc_path = "data/processed/nlcd_landcover_raw.tif"
    lc_da.rio.to_raster(lc_path)
    print(f"  Saved raw land cover to {lc_path}")

    nlcd_imperv = NLCD(years={"impervious": [2021]})
    ds_imperv = nlcd_imperv.get_map(geo_df.geometry.iloc[0], 30)
    imperv_da = ds_imperv["impervious_2021"]
    imperv_path = "data/processed/nlcd_impervious_raw.tif"
    imperv_da.rio.to_raster(imperv_path)
    print(f"  Saved raw impervious to {imperv_path}")

    return lc_path, imperv_path


if __name__ == "__main__":
    # DEM (skip if already done)
    from pathlib import Path as _P
    if not _P("data/processed/dem_500m.tif").exists():
        raw = download_dem()
        reproject_resample(raw, "data/processed/dem_500m.tif")

    # NLCD — use nearest-neighbor for categorical land cover, bilinear for impervious
    lc_raw, imperv_raw = download_nlcd()
    reproject_resample(lc_raw, "data/processed/nlcd_landcover_500m.tif",
                       resampling_method=Resampling.nearest)
    reproject_resample(imperv_raw, "data/processed/nlcd_impervious_500m.tif",
                       resampling_method=Resampling.bilinear)
    print("All terrain data ready.")
