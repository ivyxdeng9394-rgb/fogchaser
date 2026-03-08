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
                grid_lats, grid_lons, power=1.2, low_conf_radius_km=100,
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
    power          : float, IDW decay exponent (default 1.2)

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


import rasterio
import rasterio.warp
import pyproj
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
    # Clamp to avoid logit(0) or logit(1) = +/-inf
    clamped = np.clip(idw_prob, 0.005, 0.995)
    final_logit = logit(clamped) + terrain_offset
    return expit(final_logit)


def run_spatial_pipeline(station_probs, station_lats, station_lons,
                          terrain_offset_path="data/processed/terrain_offset_grid.tif",
                          output_dir="outputs/spatial",
                          valid_dt=None,
                          power=1.2):
    """
    Full Phase 2 pipeline: IDW + terrain -> output GeoTIFF.

    Parameters
    ----------
    station_probs : array-like, fog probabilities (aligned with lats/lons)
    station_lats  : array-like, station latitudes
    station_lons  : array-like, station longitudes
    valid_dt      : datetime for filename; defaults to utcnow()

    Returns
    -------
    output_path : str path to written GeoTIFF
    """
    if valid_dt is None:
        valid_dt = datetime.utcnow()

    with rasterio.open(terrain_offset_path) as src:
        profile   = src.profile.copy()
        transform = src.transform
        width, height = src.width, src.height

        # Build lat/lon grid from raster metadata
        transformer = pyproj.Transformer.from_crs("EPSG:5070", "EPSG:4326",
                                                   always_xy=True)
        rows, cols = np.mgrid[0:height, 0:width]
        xs = transform.c + cols * transform.a      # x in EPSG:5070
        ys = transform.f + rows * transform.e      # y in EPSG:5070
        lons, lats = transformer.transform(xs.ravel(), ys.ravel())
        grid_lats = lats.reshape(height, width)
        grid_lons = lons.reshape(height, width)

        # Load terrain offset
        terrain_offset = src.read(1).astype(np.float32)
        terrain_offset[terrain_offset == -9999.0] = 0.0  # nodata -> neutral

    # Run IDW
    idw_prob, low_conf = idw_logodds(
        np.asarray(station_probs),
        np.asarray(station_lats),
        np.asarray(station_lons),
        grid_lats, grid_lons,
        power=power
    )

    # Apply terrain offset
    final_prob = apply_terrain_offset(idw_prob, terrain_offset)

    # Write output GeoTIFF
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    fname = f"fog_prob_{valid_dt.strftime('%Y%m%d_%H')}UTC.tif"
    out_path = str(Path(output_dir) / fname)

    out_arr = final_prob.astype(np.float32)
    out_arr[low_conf] = -9998.0   # distinct nodata for low-confidence cells

    # Write temporary GeoTIFF in source CRS (EPSG:5070)
    tmp_path = out_path + ".tmp.tif"
    profile.update(dtype="float32", count=1, nodata=-9999.0)
    with rasterio.open(tmp_path, "w", **profile) as dst:
        dst.write(out_arr, 1)

    # Reproject to EPSG:4326 (WGS84) so geoblaze.identify works with lat/lon
    dst_crs = rasterio.crs.CRS.from_epsg(4326)
    with rasterio.open(tmp_path) as src:
        transform_4326, width_4326, height_4326 = rasterio.warp.calculate_default_transform(
            src.crs, dst_crs, src.width, src.height, *src.bounds
        )
        profile_4326 = src.profile.copy()
        profile_4326.update(
            crs=dst_crs,
            transform=transform_4326,
            width=width_4326,
            height=height_4326,
            dtype="float32",
            nodata=-9999.0,
        )
        with rasterio.open(out_path, "w", **profile_4326) as dst:
            rasterio.warp.reproject(
                source=rasterio.band(src, 1),
                destination=rasterio.band(dst, 1),
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=transform_4326,
                dst_crs=dst_crs,
                resampling=rasterio.warp.Resampling.bilinear,
                src_nodata=-9999.0,
                dst_nodata=-9999.0,
            )
    Path(tmp_path).unlink()

    print(f"  Written: {out_path}")
    return out_path
