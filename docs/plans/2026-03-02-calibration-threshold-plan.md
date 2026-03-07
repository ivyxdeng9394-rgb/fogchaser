# Calibration + Threshold Tuning Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Calibrate the ASOS+HRRR pilot model so its scores are true probabilities, then find the optimal decision threshold for a recall-biased photographer use case.

**Architecture:** Post-process the existing trained XGBoost model using Platt Scaling (logistic regression on raw scores). Split the test set chronologically 60/40 — calibrate on first 60%, evaluate on last 40%. Find threshold maximizing F2 score (recall weighted 2x vs precision).

**Tech Stack:** Python 3.9, xgboost, sklearn (CalibratedClassifierCV, fbeta_score), pandas, matplotlib, pickle

---

## Context: Key Files

- **Model:** `models/xgb_asos_hrrr_pilot_v1.json`
- **Station encoding:** `models/enhanced_asos_station_list.json` — MUST reuse this exact list
- **Test set construction:** copy the logic from `/tmp/fair_comparison.py` (Steps 1–4) verbatim
- **HRRR features:** hpbl_m, tcdc_bl_pct, dpt2m_k, tmp2m_k, rh2m_pct, hgt_cldbase_m (fill NaN→10000), u10_ms, v10_ms
- **ASOS features:** t_td_spread_lag, wind_speed_mph_lag, drct_sin_lag, drct_cos_lag, elevation, hour_sin, hour_cos, month_sin, month_cos, station_code
- **BASE_DIR:** `/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/work/vibe coding/fogchaser`
- **sys.path fix:** `sys.path.insert(0, '/Users/dengzhenhua/Library/Python/3.9/lib/python/site-packages')`

---

### Task 1: Build the unified test set

**Files:**
- Create: `/tmp/calibrate_model.py`

**Step 1: Copy test set construction from fair_comparison.py**

Open `/tmp/fair_comparison.py` and copy Steps 1–4 exactly (lines 1–109).
This loads ASOS + HRRR + NBM, merges them, applies fresh-fog filter.
Result: `merged_fresh` dataframe, `y_true` series.

Add at the top of the new file:
```python
"""
Calibration + Threshold Tuning for ASOS+HRRR Pilot Model
Saves: models/calibrator_platt_v1.pkl
       outputs/calibration_results.csv
       outputs/calibration_curve.png
"""
import sys
sys.path.insert(0, '/Users/dengzhenhua/Library/Python/3.9/lib/python/site-packages')
import pickle
import numpy as np
import pandas as pd
import json
import xgboost as xgb
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, fbeta_score,
                              precision_score, recall_score, brier_score_loss)
```

**Step 2: Verify test set loaded correctly**

After copying the data-loading block, add a sanity print:
```python
print(f"\nTest set: {len(merged_fresh):,} rows, "
      f"{int(y_true.sum())} fog events, "
      f"{y_true.mean()*100:.2f}% fog rate")
print(f"Date range: {merged_fresh['valid_hour'].min()} – {merged_fresh['valid_hour'].max()}")
```

Run: `python3 /tmp/calibrate_model.py`
Expected output:
```
Test set: 4,289 rows, 231 fog events, 5.39% fog rate
Date range: 2024-... – 2024-...
```
If row count or fog rate differs, stop and check the fresh-fog filter was applied.

---

### Task 2: Time-based 60/40 split

**Files:**
- Modify: `/tmp/calibrate_model.py`

**Step 1: Sort and split chronologically**

```python
# ── Time-based 60/40 split ────────────────────────────────────────────────────
merged_sorted = merged_fresh.sort_values('valid_hour').reset_index(drop=True)
split_idx = int(len(merged_sorted) * 0.60)
split_time = merged_sorted['valid_hour'].iloc[split_idx]

cal_df  = merged_sorted.iloc[:split_idx].copy()   # calibration
eval_df = merged_sorted.iloc[split_idx:].copy()   # evaluation

y_cal  = cal_df['is_fog']
y_eval = eval_df['is_fog']

print(f"\nCalibration set: {len(cal_df):,} rows, "
      f"{int(y_cal.sum())} fog events, "
      f"{y_cal.mean()*100:.2f}% fog rate")
print(f"  Period: {cal_df['valid_hour'].min().date()} – {cal_df['valid_hour'].max().date()}")
print(f"\nEvaluation set:  {len(eval_df):,} rows, "
      f"{int(y_eval.sum())} fog events, "
      f"{y_eval.mean()*100:.2f}% fog rate")
print(f"  Period: {eval_df['valid_hour'].min().date()} – {eval_df['valid_hour'].max().date()}")
```

**Step 2: Build feature matrices for both splits**

Reuse the same feature engineering from `fair_comparison.py` (station encoding,
trig features, wind direction). Apply to both `cal_df` and `eval_df`.

```python
# ── Feature engineering (same as fair_comparison.py) ─────────────────────────
with open(f'{BASE_DIR}/models/enhanced_asos_station_list.json') as f:
    all_stations = json.load(f)
station_cat = pd.CategoricalDtype(categories=all_stations, ordered=False)

def build_features(df):
    df = df.copy()
    df['station_code'] = df['station'].astype(station_cat).cat.codes
    df['hour_utc']     = df['valid_hour'].dt.hour
    df['month']        = df['valid_hour'].dt.month
    df['hour_sin']     = np.sin(2 * np.pi * df['hour_utc'] / 24)
    df['hour_cos']     = np.cos(2 * np.pi * df['hour_utc'] / 24)
    df['month_sin']    = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos']    = np.cos(2 * np.pi * df['month'] / 12)
    drct_rad = np.deg2rad(df['drct_lag'].fillna(0))
    df['drct_sin_lag'] = np.sin(drct_rad)
    df['drct_cos_lag'] = np.cos(drct_rad)
    return df

cal_df  = build_features(cal_df)
eval_df = build_features(eval_df)

ASOS_FEATURES = ['t_td_spread_lag','wind_speed_mph_lag','drct_sin_lag','drct_cos_lag',
                 'elevation','hour_sin','hour_cos','month_sin','month_cos','station_code']
HRRR_FEATURES = ['hpbl_m','tcdc_bl_pct','dpt2m_k','tmp2m_k','rh2m_pct',
                 'hgt_cldbase_m','u10_ms','v10_ms']
ALL_FEATURES  = ASOS_FEATURES + HRRR_FEATURES

X_cal  = cal_df[ALL_FEATURES].fillna(cal_df[ALL_FEATURES].median())
X_eval = eval_df[ALL_FEATURES].fillna(eval_df[ALL_FEATURES].median())
```

**Step 3: Verify shapes**

```python
print(f"\nX_cal shape:  {X_cal.shape}")
print(f"X_eval shape: {X_eval.shape}")
assert X_cal.shape[1] == 18, f"Expected 18 features, got {X_cal.shape[1]}"
assert X_eval.shape[1] == 18
print("Feature shapes OK")
```

Run and confirm no assertion errors.

---

### Task 3: Get raw model scores

**Files:**
- Modify: `/tmp/calibrate_model.py`

**Step 1: Load model and get raw probabilities**

```python
# ── Load HRRR model and get raw scores ───────────────────────────────────────
hrrr_model = xgb.XGBClassifier()
hrrr_model.load_model(f'{BASE_DIR}/models/xgb_asos_hrrr_pilot_v1.json')

raw_cal  = hrrr_model.predict_proba(X_cal)[:, 1]
raw_eval = hrrr_model.predict_proba(X_eval)[:, 1]

print(f"\nRaw scores on calibration set:")
print(f"  Min: {raw_cal.min():.4f}  Max: {raw_cal.max():.4f}  Mean: {raw_cal.mean():.4f}")
print(f"  AUC-PR: {average_precision_score(y_cal, raw_cal):.4f}")
print(f"\nRaw scores on evaluation set:")
print(f"  AUC-PR: {average_precision_score(y_eval, raw_eval):.4f}")
```

**Step 2: Verify scores are reasonable**

Expected: AUC-PR on both splits should be in the range 0.25–0.45 (consistent with
the full test set score of 0.358). If one split is wildly different (e.g., 0.10),
the time split may have hit a very fog-sparse period — acceptable but worth noting.

---

### Task 4: Fit Platt Scaling calibrator

**Files:**
- Modify: `/tmp/calibrate_model.py`

**Step 1: Fit logistic regression on raw calibration scores**

```python
# ── Platt Scaling: fit logistic regression on raw scores ─────────────────────
calibrator = LogisticRegression(C=1.0, solver='lbfgs', max_iter=1000)
calibrator.fit(raw_cal.reshape(-1, 1), y_cal)

cal_probs_cal  = calibrator.predict_proba(raw_cal.reshape(-1, 1))[:, 1]
cal_probs_eval = calibrator.predict_proba(raw_eval.reshape(-1, 1))[:, 1]

print(f"\nCalibrated scores on evaluation set:")
print(f"  Min: {cal_probs_eval.min():.4f}  Max: {cal_probs_eval.max():.4f}")
print(f"  Mean: {cal_probs_eval.mean():.4f}  (true fog rate: {y_eval.mean():.4f})")
print(f"  AUC-PR (should match raw): {average_precision_score(y_eval, cal_probs_eval):.4f}")
print(f"  Brier score (lower=better): {brier_score_loss(y_eval, cal_probs_eval):.4f}")
print(f"  Brier raw:                  {brier_score_loss(y_eval, raw_eval):.4f}")
```

**Step 2: Verify calibration preserved AUC-PR**

Platt scaling is a monotonic transformation so AUC-PR must stay identical.
If it changes by more than 0.001, something is wrong.

---

### Task 5: Plot calibration curve (reliability diagram)

**Files:**
- Modify: `/tmp/calibrate_model.py`

**Step 1: Generate and save reliability diagram**

A reliability diagram shows: if the model says "X% fog chance", does fog actually
happen X% of the time? Perfect calibration = diagonal line.

```python
# ── Reliability diagram ───────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(7, 6))

# Raw model
frac_pos_raw, mean_pred_raw = calibration_curve(y_eval, raw_eval, n_bins=10)
ax.plot(mean_pred_raw, frac_pos_raw, 's-', color='steelblue',
        label=f'Raw XGB (Brier={brier_score_loss(y_eval, raw_eval):.3f})')

# Calibrated
frac_pos_cal, mean_pred_cal = calibration_curve(y_eval, cal_probs_eval, n_bins=10)
ax.plot(mean_pred_cal, frac_pos_cal, 's-', color='darkorange',
        label=f'Platt Calibrated (Brier={brier_score_loss(y_eval, cal_probs_eval):.3f})')

# Perfect calibration reference
ax.plot([0, 1], [0, 1], 'k--', alpha=0.5, label='Perfect calibration')

ax.set_xlabel('Mean predicted probability')
ax.set_ylabel('Fraction of positives (actual fog rate)')
ax.set_title('Calibration Curve (Reliability Diagram)\nASOSS+HRRR Pilot Model')
ax.legend(loc='upper left')
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/calibration_curve.png', dpi=150)
plt.close()
print(f"\nCalibration curve saved to outputs/calibration_curve.png")
```

Run and open `outputs/calibration_curve.png` to visually inspect.
The calibrated (orange) line should be closer to the diagonal than the raw (blue) line.

---

### Task 6: F2 threshold optimization

**Files:**
- Modify: `/tmp/calibrate_model.py`

**Step 1: Sweep thresholds on calibration set**

```python
# ── F2 threshold optimization on calibration set ─────────────────────────────
thresholds = np.arange(0.01, 0.99, 0.01)
results = []

for thresh in thresholds:
    y_pred = (cal_probs_cal >= thresh).astype(int)
    prec   = precision_score(y_cal, y_pred, zero_division=0)
    rec    = recall_score(y_cal, y_pred, zero_division=0)
    f2     = fbeta_score(y_cal, y_pred, beta=2, zero_division=0)
    alert_rate = y_pred.mean()
    results.append({
        'threshold':  thresh,
        'precision':  prec,
        'recall':     rec,
        'f2':         f2,
        'alert_rate': alert_rate,
    })

results_df = pd.DataFrame(results)
best_row   = results_df.loc[results_df['f2'].idxmax()]
best_thresh = best_row['threshold']

print(f"\nF2-optimal threshold: {best_thresh:.2f}")
print(f"  Precision:  {best_row['precision']:.3f}  "
      f"({best_row['precision']*100:.1f}% of fog alerts are real)")
print(f"  Recall:     {best_row['recall']:.3f}  "
      f"(catches {best_row['recall']*100:.1f}% of actual fog events)")
print(f"  Alert rate: {best_row['alert_rate']:.3f}  "
      f"(fires {best_row['alert_rate']*100:.1f}% of hours)")
print(f"  F2:         {best_row['f2']:.4f}")
```

**Step 2: Validate threshold on evaluation set**

```python
# ── Evaluate at best threshold on held-out evaluation set ────────────────────
y_pred_eval = (cal_probs_eval >= best_thresh).astype(int)
print(f"\nEvaluation set at threshold={best_thresh:.2f}:")
print(f"  Precision:  {precision_score(y_eval, y_pred_eval, zero_division=0):.3f}")
print(f"  Recall:     {recall_score(y_eval, y_pred_eval, zero_division=0):.3f}")
print(f"  F2:         {fbeta_score(y_eval, y_pred_eval, beta=2, zero_division=0):.4f}")
print(f"  Alert rate: {y_pred_eval.mean():.3f}")
print(f"  AUC-PR:     {average_precision_score(y_eval, cal_probs_eval):.4f}")
```

---

### Task 7: Plot precision-recall curve with threshold marked

**Files:**
- Modify: `/tmp/calibrate_model.py`

**Step 1: Generate PR curve with operating point**

```python
# ── Precision-Recall curve with F2 threshold marked ──────────────────────────
from sklearn.metrics import precision_recall_curve

precision_arr, recall_arr, thresh_arr = precision_recall_curve(y_eval, cal_probs_eval)

fig, ax = plt.subplots(figsize=(8, 6))
ax.plot(recall_arr, precision_arr, color='darkorange', lw=2, label='Calibrated model')
ax.axhline(y=y_eval.mean(), color='gray', linestyle='--',
           label=f'Random baseline ({y_eval.mean()*100:.1f}%)')

# Mark the chosen operating point
op_prec = precision_score(y_eval, y_pred_eval, zero_division=0)
op_rec  = recall_score(y_eval, y_pred_eval, zero_division=0)
ax.scatter([op_rec], [op_prec], s=120, zorder=5, color='red',
           label=f'F2 threshold={best_thresh:.2f}\n'
                 f'Prec={op_prec:.2f}, Rec={op_rec:.2f}')

ax.set_xlabel('Recall (% of fog events caught)')
ax.set_ylabel('Precision (% of alerts that are real)')
ax.set_title('Precision-Recall Curve — ASOS+HRRR Pilot (Calibrated)')
ax.legend(loc='upper right')
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/pr_curve_calibrated.png', dpi=150)
plt.close()
print(f"PR curve saved to outputs/pr_curve_calibrated.png")
```

---

### Task 8: Save calibrator and results

**Files:**
- Modify: `/tmp/calibrate_model.py`

**Step 1: Save the fitted calibrator**

```python
# ── Save calibrator ───────────────────────────────────────────────────────────
calibrator_path = f'{BASE_DIR}/models/calibrator_platt_v1.pkl'
with open(calibrator_path, 'wb') as f:
    pickle.dump({
        'calibrator':    calibrator,
        'best_threshold': best_thresh,
        'features':      ALL_FEATURES,
    }, f)
print(f"\nCalibrator saved to {calibrator_path}")
print(f"Best threshold saved: {best_thresh:.2f}")
```

**Step 2: Save full threshold sweep results**

```python
results_df['split'] = 'calibration'
eval_results = []
for thresh in thresholds:
    y_pred = (cal_probs_eval >= thresh).astype(int)
    eval_results.append({
        'threshold':  thresh,
        'precision':  precision_score(y_eval, y_pred, zero_division=0),
        'recall':     recall_score(y_eval, y_pred, zero_division=0),
        'f2':         fbeta_score(y_eval, y_pred, beta=2, zero_division=0),
        'alert_rate': y_pred.mean(),
        'split':      'evaluation',
    })
eval_results_df = pd.DataFrame(eval_results)
all_results = pd.concat([results_df, eval_results_df], ignore_index=True)
all_results.to_csv(f'{BASE_DIR}/outputs/calibration_results.csv', index=False)
print(f"Threshold sweep saved to outputs/calibration_results.csv")
```

**Step 3: Print final summary**

```python
print("\n" + "="*60)
print("CALIBRATION COMPLETE")
print("="*60)
print(f"Model:      ASOS+HRRR pilot (4-month training)")
print(f"Calibration: Platt Scaling (logistic regression on raw scores)")
print(f"Threshold:  {best_thresh:.2f} (F2-optimized, recall-biased)")
print(f"\nAt this threshold on held-out evaluation set:")
print(f"  Catches {op_rec*100:.0f}% of fog events")
print(f"  {op_prec*100:.0f}% of alerts are real fog")
print(f"  Fires {y_pred_eval.mean()*100:.1f}% of hours (= {y_pred_eval.mean()*24:.1f} alerts/day on average)")
print(f"\nArtifacts:")
print(f"  models/calibrator_platt_v1.pkl")
print(f"  outputs/calibration_curve.png")
print(f"  outputs/pr_curve_calibrated.png")
print(f"  outputs/calibration_results.csv")
```

Run the full script: `python3 /tmp/calibrate_model.py`

---

## Success Criteria

- [ ] Calibration curve plot shows calibrated line closer to diagonal than raw
- [ ] Brier score improves (decreases) after calibration
- [ ] AUC-PR is unchanged (within 0.001) — calibration must not change ranking
- [ ] Alert rate at chosen threshold is < 30% of hours (not crying wolf)
- [ ] Recall at chosen threshold is > 50% (catching majority of fog events)
- [ ] All 4 artifacts saved successfully
