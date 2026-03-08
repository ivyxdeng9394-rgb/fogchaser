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
                      stations: list = None) -> pd.DataFrame:
    """
    Fetch recent ASOS observations and return lag feature DataFrame.

    Returns empty DataFrame if request fails — caller handles gracefully.
    """
    if stations is None:
        stations = DC_STATIONS
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
    except requests.RequestException as e:
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
    # IEM returns station IDs without the K prefix (e.g. "DCA" not "KDCA") — normalize
    df["station"] = df["station"].apply(lambda s: s if s.startswith("K") else "K" + s)
    df["valid"] = pd.to_datetime(df["valid"], utc=True, errors="coerce")
    df = df.dropna(subset=["valid"])

    # One row per station — most recent observation
    df = df.sort_values("valid").groupby("station").last().reset_index()

    # Check for missing stations — IEM may return partial results with HTTP 200
    returned = set(df["station"])
    missing = set(stations) - returned
    if missing:
        print(f"  WARNING: Missing stations from IEM: {sorted(missing)}")
    if df.empty:
        print("  WARNING: IEM returned 200 but no station data. Treating as failure.")
        return pd.DataFrame()

    # Compute lag features
    df["t_td_spread_lag"]   = (pd.to_numeric(df["tmpf"], errors="coerce") - pd.to_numeric(df["dwpf"], errors="coerce")).clip(lower=0)
    df["wind_speed_mph_lag"] = pd.to_numeric(df["sknt"], errors="coerce") * 1.15078
    drct_rad = np.radians(pd.to_numeric(df["drct"], errors="coerce").fillna(0))
    df["drct_sin_lag"] = np.sin(drct_rad)
    df["drct_cos_lag"] = np.cos(drct_rad)
    df["elevation"]    = pd.to_numeric(df["elevation"], errors="coerce")

    return df[["station", "elevation", "t_td_spread_lag",
               "wind_speed_mph_lag", "drct_sin_lag", "drct_cos_lag"]].copy()
