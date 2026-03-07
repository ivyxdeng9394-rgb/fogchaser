# Full HRRR Model Retraining — Session Handoff

**Date written:** 2026-03-05
**Status:** Ready to execute — all data is on disk, approach is decided
**Context:** HRRR 6-year extraction completed overnight. RAM is 8GB — cannot load all ~40M rows at once.

---

## What This Session Should Do

Retrain the ASOS+HRRR model on the full 6-year dataset (2018–2023) using a
35% stratified sample to stay within 8GB RAM. Then evaluate against the fair
comparison test set and compare to the pilot model (AUC-PR 0.358).

---

## All Training Data — Ready on Disk

Six yearly HRRR parquet files, one per year:

| File | Size | Rows (est.) |
|---|---|---|
| `data/raw/hrrr/hrrr_train_2018.parquet` | 146 MB | ~6.7M |
| `data/raw/hrrr/hrrr_train_2019.parquet` | 145 MB | ~6.7M |
| `data/raw/hrrr/hrrr_train_2020.parquet` | 146 MB | ~6.7M |
| `data/raw/hrrr/hrrr_train_2021.parquet` | 159 MB | ~6.7M |
| `data/raw/hrrr/hrrr_train_2022.parquet` | 158 MB | ~6.7M |
| `data/raw/hrrr/hrrr_train_2023.parquet` | 158 MB | ~6.7M |
| **Total** | **~912 MB** | **~40M rows** |

ASOS training data (already used, don't re-download):
- `data/raw/asos/national_train_2018_2023.parquet` — 6yr national ASOS labels

Test set (do not touch — held out):
- `data/raw/asos/dc_metro_test_2024_2026.parquet` — DC metro ground truth
- `data/raw/hrrr/hrrr_test_dc_2024.parquet` — HRRR features for test set

---

## Training Approach: 35% Stratified Sample

**Why not all 40M rows:** 8GB RAM cannot hold the full dataset in memory.
Loading all 6 years would require ~6–8 GB for the feature matrix alone,
leaving no headroom for XGBoost training.

**Why 35% is good enough:**
- 35% of 40M = ~14M rows — still 6x more than the 4-month pilot (2.2M rows)
- Covers all 6 years and all seasons — seasonal coverage is the key gap we're filling
- Stratify by `is_fog` label to preserve the ~5% fog rate in the sample

**How to sample:**
Load one year at a time, sample 35% stratified, concatenate. Never load all years at once.

```python
import pandas as pd
import numpy as np

SAMPLE_FRAC = 0.35
RANDOM_STATE = 42

yearly_samples = []
for year in range(2018, 2024):
    # Load HRRR for this year
    hrrr_yr = pd.read_parquet(f'{BASE_DIR}/data/raw/hrrr/hrrr_train_{year}.parquet')

    # Load matching ASOS labels for this year
    asos_yr = pd.read_parquet(
        f'{BASE_DIR}/data/raw/asos/national_train_2018_2023.parquet',  # or yearly file
        columns=['station','valid','is_fog','tmpf','dwpf','sknt','drct','elevation']
    )
    asos_yr = asos_yr[asos_yr['valid'].dt.year == year]

    # Merge HRRR + ASOS on station + valid_hour
    # ... (see fair_comparison.py for the merge pattern)

    # Stratified sample
    merged_yr = merged_yr.groupby('is_fog', group_keys=False).apply(
        lambda x: x.sample(frac=SAMPLE_FRAC, random_state=RANDOM_STATE)
    )
    yearly_samples.append(merged_yr)
    del hrrr_yr, asos_yr  # free memory immediately after each year

train_df = pd.concat(yearly_samples, ignore_index=True)
print(f"Training set: {len(train_df):,} rows, fog rate: {train_df['is_fog'].mean()*100:.2f}%")
```

**Memory tips:**
- Use `del` and `gc.collect()` after each year to free memory
- Cast float columns to `float32` before building the feature matrix (halves memory)
- Build the XGBoost DMatrix directly from numpy arrays, not pandas — more memory efficient

---

## Feature Engineering (identical to pilot — do not change)

**CRITICAL: Reuse the exact station list from `enhanced_asos_station_list.json`**
If a new station list is created, station_code integers will mismatch and the model
will silently use wrong stations.

```python
with open(f'{BASE_DIR}/models/enhanced_asos_station_list.json') as f:
    all_stations = json.load(f)
station_cat = pd.CategoricalDtype(categories=all_stations, ordered=False)
```

**Fresh fog filter** — apply to training data too:
`vsby_km_lag >= 1.0` (12h lag) — removes rows where fog was already present.
Without it the model learns persistence, not onset.

**ASOS features** (build from lagged values at T-12h):
- `t_td_spread_lag` — temperature minus dew point (°F)
- `wind_speed_mph_lag` — wind speed in mph
- `drct_sin_lag`, `drct_cos_lag` — wind direction encoded as sin/cos
- `elevation` — station elevation (from ASOS metadata)
- `hour_sin`, `hour_cos` — hour of day (UTC) encoded cyclically
- `month_sin`, `month_cos` — month encoded cyclically
- `station_code` — integer from CategoricalDtype encoding

**HRRR features** (f12 forecast at target hour):
- `hpbl_m` — planetary boundary layer height (metres)
- `tcdc_bl_pct` — boundary layer cloud cover (%)
- `dpt2m_k` — 2m dew point temperature (Kelvin)
- `tmp2m_k` — 2m temperature (Kelvin)
- `rh2m_pct` — 2m relative humidity (%)
- `hgt_cldbase_m` — cloud base height → **fill NaN with 10,000** (NaN = no cloud, not missing)
- `u10_ms`, `v10_ms` — 10m wind u and v components (m/s)

**Total: 18 features**

---

## Model Training

Same XGBoost config as pilot — do not change hyperparameters yet:

```python
import xgboost as xgb

model = xgb.XGBClassifier(
    n_estimators=500,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=(1 - fog_rate) / fog_rate,  # handles class imbalance
    eval_metric='aucpr',
    early_stopping_rounds=20,
    random_state=42,
    tree_method='hist',   # memory-efficient
    device='cpu'
)

model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    verbose=50
)
```

Use a small validation split (10% of training sample) for early stopping.
Save the model to: `models/xgb_asos_hrrr_full_v1.json`

---

## Evaluation

After training, evaluate using the EXACT same fair comparison test set used previously.
Reuse `/tmp/fair_comparison.py` as the template.

**Key comparison to make:**

| Model | AUC-PR | vs Random |
|---|---|---|
| Baseline rule | 0.071 | 1.3x |
| NBM soft | 0.296 | 5.5x |
| ASOS+HRRR pilot (4-month) | 0.358 | 6.7x |
| **ASOS+HRRR full (6yr) ← new** | **?** | **?** |

The new model should beat 0.358. If it doesn't improve meaningfully (< 0.01 gain),
investigate whether the sample was representative or whether the model needs tuning.

---

## If 35% Sample Still Runs Out of Memory

**Fallback Option B — Year-by-year warm start:**
```python
model = xgb.XGBClassifier(...)
model.fit(X_2018, y_2018)  # train on first year

for year in range(2019, 2024):
    model = xgb.XGBClassifier(
        ...,
        xgb_model=model.get_booster()  # warm start from previous
    )
    model.fit(X_year, y_year)
```

**Fallback Option C — Google Colab:**
- Free, 12–15GB RAM
- Upload the 6 yearly parquet files (~912MB total) to Google Drive
- Can load full dataset without sampling

---

## What to Save

- `models/xgb_asos_hrrr_full_v1.json` — the new full model
- Re-run calibration: `models/calibrator_platt_v2.pkl` — recalibrate on new model
- Update `outputs/fair_comparison_results.csv` with new model row
- Update MEMORY.md with new AUC-PR result

---

## Success Criteria

- [ ] AUC-PR > 0.358 (beats the 4-month pilot)
- [ ] Fog rate in training sample ≈ 5% (stratification worked)
- [ ] Model trained without memory error
- [ ] Fair comparison evaluation completed on same 4,289-row test set
- [ ] New model saved and calibrated
