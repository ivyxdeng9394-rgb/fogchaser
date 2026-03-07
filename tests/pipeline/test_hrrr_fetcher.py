import numpy as np
import pandas as pd
import pytest
import xarray as xr
from scripts.fetch_live_hrrr import extract_station_values, REQUIRED_COLS, DC_STATION_COORDS, _NO_CLOUD_M


def make_mock_ds():
    """Build a minimal mock xarray Dataset with real Herbie variable names (from MEMORY.md)."""
    coords = list(DC_STATION_COORDS.values())
    n = len(coords)
    lats = np.array([c[0] for c in coords])
    lons = np.array([c[1] + 360 if c[1] < 0 else c[1] for c in coords])

    return xr.Dataset({
        "t2m": xr.DataArray(np.full(n, 275.0), dims=["points"]),
        "d2m": xr.DataArray(np.full(n, 274.0), dims=["points"]),
        "r2":  xr.DataArray(np.full(n, 95.0),  dims=["points"]),
        "u10": xr.DataArray(np.full(n, 1.0),   dims=["points"]),
        "v10": xr.DataArray(np.full(n, -0.5),  dims=["points"]),
        "blh": xr.DataArray(np.full(n, 50.0),  dims=["points"]),
        "tcc": xr.DataArray(np.full(n, 80.0),  dims=["points"]),
        "gh":  xr.DataArray(np.full(n, np.nan), dims=["points"]),
        "latitude":  xr.DataArray(lats, dims=["points"]),
        "longitude": xr.DataArray(lons, dims=["points"]),
    })


def test_required_columns_present():
    df = extract_station_values(make_mock_ds(), DC_STATION_COORDS)
    for col in REQUIRED_COLS:
        assert col in df.columns, f"Missing: {col}"


def test_cloud_base_nan_filled():
    """hgt_cldbase_m NaN (no cloud) must become _NO_CLOUD_M sentinel."""
    df = extract_station_values(make_mock_ds(), DC_STATION_COORDS)
    assert (df["hgt_cldbase_m"] == _NO_CLOUD_M).all()


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
    df = extract_station_values(ds, {"KDCA": (38.8472, -77.0345)})
    assert len(df) == 1
    assert not df["tmp2m_k"].isna().any(), \
        "NaN result suggests longitude conversion failed — HRRR uses 0-360"
