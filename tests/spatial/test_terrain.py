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


def test_nlcd_files_exist_and_valid():
    """NLCD land cover and impervious files should exist at 500m in EPSG:5070."""
    for name in ["nlcd_landcover_500m.tif", "nlcd_impervious_500m.tif"]:
        path = Path(f"data/processed/{name}")
        assert path.exists(), f"Missing {name} — run scripts/terrain_setup.py"
        with rasterio.open(path) as src:
            assert src.crs.to_epsg() == 5070
            data = src.read(1)
            assert data.shape[0] >= 300


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


def test_impervious_feature_normalized():
    path = Path("data/processed/imperv_norm.tif")
    assert path.exists()
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        arr[arr == -9999] = np.nan
        # inverted: high impervious = low value
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


def test_cos_aspect_range():
    path = Path("data/processed/cos_aspect.tif")
    assert path.exists()
    with rasterio.open(path) as src:
        arr = src.read(1).astype(float)
        arr[arr == -9999] = np.nan
        # cosine output is [-1, +1] by definition
        assert np.nanmin(arr) >= -1.01
        assert np.nanmax(arr) <= 1.01


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


def test_terrain_offset_valley_is_fog_favoring():
    """
    Valleys (negative TPI) should produce a POSITIVE terrain offset after negation.
    Ridges (positive TPI) should produce a NEGATIVE terrain offset.
    This verifies the cold-air-pooling sign is correct.
    """
    with rasterio.open("data/processed/tpi_multi_norm.tif") as src:
        tpi = src.read(1).astype(float)
        tpi[tpi == -9999] = np.nan

    with rasterio.open("data/processed/terrain_offset_grid.tif") as src:
        offset = src.read(1).astype(float)
        offset[offset == -9999] = np.nan

    # Find clear valley cells (bottom 10% of TPI = deepest valleys)
    tpi_p10 = np.nanpercentile(tpi, 10)
    valley_mask = tpi < tpi_p10

    # Find clear ridge cells (top 10% of TPI = highest ridges)
    tpi_p90 = np.nanpercentile(tpi, 90)
    ridge_mask = tpi > tpi_p90

    valley_offset_mean = np.nanmean(offset[valley_mask])
    ridge_offset_mean  = np.nanmean(offset[ridge_mask])

    assert valley_offset_mean > 0, (
        f"Valley cells should have positive terrain offset (fog-favoring), "
        f"got {valley_offset_mean:.4f}"
    )
    assert ridge_offset_mean < 0, (
        f"Ridge cells should have negative terrain offset (fog-suppressing), "
        f"got {ridge_offset_mean:.4f}"
    )
    assert valley_offset_mean > ridge_offset_mean, (
        f"Valley offset ({valley_offset_mean:.4f}) should exceed "
        f"ridge offset ({ridge_offset_mean:.4f})"
    )
