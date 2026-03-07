import pandas as pd
import pytest
import requests
from unittest.mock import patch, Mock
from scripts.fetch_live_asos import fetch_asos_latest

# IEM returns CSV with a comment header line starting with #
MOCK_CSV = """# Iowa Environmental Mesonet
station,valid,tmpf,dwpf,sknt,drct,vsby,lon,lat,elev
KBWI,2024-12-10 08:54,34.0,32.0,4,220,0.25,-76.6841,39.1733,42.0
KDCA,2024-12-10 08:52,36.0,35.0,3,200,0.12,-77.0345,38.8472,20.0
KIAD,2024-12-10 08:52,33.0,32.5,2,180,0.12,-77.4473,38.9348,98.0
"""


@pytest.fixture
def mock_iem():
    with patch("scripts.fetch_live_asos.requests.get") as mock_get:
        mock_get.return_value = Mock(status_code=200, text=MOCK_CSV)
        yield mock_get


def test_returns_required_columns(mock_iem):
    """fetch_asos_latest should return a DataFrame with required lag feature columns."""
    df = fetch_asos_latest(lookback_hours=2)
    required = {"station", "elevation", "t_td_spread_lag",
                "wind_speed_mph_lag", "drct_sin_lag", "drct_cos_lag"}
    assert required.issubset(set(df.columns))


def test_one_row_per_station(mock_iem):
    """Should return at most one row per station."""
    df = fetch_asos_latest(lookback_hours=2)
    assert df["station"].nunique() == len(df)


def test_t_td_spread_non_negative(mock_iem):
    """T-Td spread must be >= 0 (temp is always >= dewpoint)."""
    df = fetch_asos_latest(lookback_hours=2)
    assert (df["t_td_spread_lag"] >= 0).all()


def test_returns_empty_on_api_failure():
    """Should return empty DataFrame (not raise) when API fails."""
    with patch("scripts.fetch_live_asos.requests.get") as mock_get:
        mock_get.side_effect = requests.ConnectionError("connection refused")
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
