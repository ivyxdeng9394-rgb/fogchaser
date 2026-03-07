# Calibration + Threshold Tuning Design

**Date:** 2026-03-02
**Status:** Approved — ready for implementation

---

## Goal

Make the ASOS+HRRR pilot model's output trustworthy as a real probability, and find the
right decision threshold for a photographer use case: it is worse to miss fog than to
get a false alarm, but predicting fog every day makes the tool useless.

---

## Approach: Platt Scaling + F2 Threshold Optimization

### 1. Calibration — Platt Scaling

**What it does:** Fits a logistic regression on top of the raw XGBoost probability scores.
Maps raw scores to true probabilities so that "40% fog chance" actually means fog occurs
40% of the time when the model says that.

**Why Platt Scaling over alternatives:**
- Isotonic regression is more flexible but can overfit on our 4,289-row test set
- Temperature scaling is mainly used for deep learning, not tree models
- Platt Scaling is the standard recommendation for XGBoost and works well on imbalanced datasets

**Implementation:** `sklearn.calibration.CalibratedClassifierCV` with `method='sigmoid'`
and `cv='prefit'` (since the XGB model is already trained).

### 2. Data Split — Time-Based 60/40

**Why time-based, not random:** Fog can persist across consecutive hours. A random
split risks temporal leakage — calibration and evaluation rows from the same fog
event end up on different sides. A chronological split is the industry standard for
time-series data.

- **Calibration set:** First 60% of test period chronologically (~2,574 rows)
- **Evaluation set:** Last 40% of test period chronologically (~1,716 rows)
- Both sets use the same fresh-fog filter (vsby_km_lag >= 1.0)

### 3. Threshold — F2 Score Optimization

**What F2 means:** A standard metric that weights recall 2x more than precision.
Directly matches the user's stated preference: missing fog is worse than false alarms,
but precision still matters.

**Formula:** F2 = 5 × (precision × recall) / (4 × precision + recall)

**Process:**
- Sweep thresholds from 0.01 to 0.99 in steps of 0.01
- Compute F2 at each threshold on the calibration set
- Select threshold that maximizes F2
- Validate on evaluation set

---

## Outputs

1. **Calibrated model scores** — saved alongside raw scores for comparison
2. **Calibration curve plot** — reliability diagram showing raw vs calibrated probabilities
   (x=predicted probability, y=actual fog fraction)
3. **Precision-recall curve** — with F2-optimal threshold marked
4. **Summary table** — at the chosen threshold:
   - Precision: "X% of fog alerts are real"
   - Recall: "catches Y% of actual fog events"
   - Alert rate: "fires Z% of hours" (the "cry wolf" metric)
5. **Saved artifacts:**
   - `models/calibrator_platt_v1.pkl` — the fitted logistic regression
   - `outputs/calibration_results.csv` — metrics at all thresholds
   - `outputs/calibration_curve.png` — reliability diagram

---

## Script

`/tmp/calibrate_model.py`

Reuses the test set construction logic from `fair_comparison.py` verbatim.
Does not retrain the XGB model — calibration is a post-processing step only.

---

## What This Does NOT Do

- Does not retrain XGBoost
- Does not add new features
- Does not change the model architecture
- The calibrated model is still limited by its 4-month (winter-only) training data
