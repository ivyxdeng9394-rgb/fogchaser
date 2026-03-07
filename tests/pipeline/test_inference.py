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
