# Phase 1: Fog Model Validation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

> **Execution rules — mandatory:**
>
> **Rule 1 — Test before proceeding.** After every step, verify the output matches the "Expected output." If wrong, missing, or erroring: stop, fix, re-run, verify. Do not proceed until the step passes. If you cannot fix it after two attempts, stop and surface the problem clearly.
>
> **Rule 2 — Record null rates before filling.** Before filling any NaN values with medians, print the null rate per column. If any column has > 10% nulls, stop — this means systematic extraction failure, not random gaps. Filling over a 30% null rate produces a corrupted feature matrix that will look fine but isn't.
>
> **Rule 3 — Verify temporal integrity explicitly.** At the start of any modeling task, assert that the maximum date in the training set is strictly earlier than the minimum date in the test set. Future data leaking into training is the most common silent error in time-series modeling and produces inflated results that evaporate in production.
>
> **Rule 4 — Check feature distributions before modeling.** Before fitting any model, print mean and standard deviation of every feature in both train and test sets side by side. If any feature differs by more than 2× between train and test, flag it and investigate before proceeding. A model evaluated outside its training distribution will produce misleading metrics.
>
> **Rule 5 — Never overwrite raw data files.** Files in `data/raw/` are read-only after creation. Always write outputs to new files. If a file already exists at a path, skip the download rather than overwriting.
>
> **Rule 6 — Monitor extraction failure rate; stop if too high.** After any bulk extraction loop (HRRR, NBM), compute the fraction of attempted records that failed. If failure rate exceeds 15%, stop — do not proceed to modeling on a corrupted dataset. Log every failed timestamp to a file and investigate the pattern before retrying.
>
> **Rule 7 — Lock the test set before any modeling; never look at it during tuning.** At the start of Task 6, define the exact rows in the test set once and reuse that exact dataframe for every model. Never use test set metrics to make decisions about features, hyperparameters, or whether to apply calibration — those decisions belong on the validation split only. Look at test metrics once, at the end, after all decisions are final.
>
> **Rule 8 — Physical sense check after every model.** After training any model, print the 20 highest-confidence fog predictions from the test set. Check: are they pre-dawn (midnight–7am)? Oct–Mar? Low-elevation stations? Low T-Td spread? If the model's most confident predictions look physically wrong, the model learned spurious patterns — regardless of aggregate AUC-PR.
>
> **Rule 9 — One random seed, defined once.** All random operations (train/test splits, model training, calibration) reference a single `RANDOM_SEED = 42` variable defined at the top of each notebook. Never hardcode 42 inline — always use the variable so results are reproducible and the seed can be changed in one place.
>
> **Rule 10 — Log every model run to a shared experiment log.** Every time a model is evaluated, append a row to `outputs/experiment_log.csv`: timestamp, model name, feature set, key metrics (AUC-PR, Brier, precision, recall). This creates a permanent record so you can always see what changed between runs and whether a change helped or hurt.
>
> **Rule 11 — Cross-source sanity check after merging ASOS and HRRR.** After any join between ASOS observations and HRRR forecast fields, verify the two sources agree on temperature. HRRR temperature (converted to °C) and ASOS temperature should match within 10°C for at least 95% of rows. Larger disagreement means the coordinate matching is wrong and the join is broken.

**Goal:** Determine the minimum viable modeling approach that produces useful fog predictions for DC metro area — before building any app.

**Architecture:** Three-phase validation pipeline. Start cheap, escalate only if needed.

**Phase 0 (NBM benchmark, fastest):** Test NOAA's professional forecast product (NBM) directly against DC metro ASOS observations. NBM already provides visibility forecasts at 2.5km resolution; we add a simple station-elevation terrain weight. If this passes the gate, we have an MVP-ready product with no ML required.

**Phase 1A (ASOS-only ML, fast):** Only run if NBM fails. Pull labeled fog data from ASOS stations. Train models using only ASOS-observable features (T-Td spread, wind speed, persistence of current conditions, lead time). Tells us if there is signal in the data that NBM is missing.

**Phase 1A.5 (Lagged ASOS forecast model):** The Phase 1A model is a *detector* — it uses current conditions to recognize fog happening right now. That's not what Alex needs. Alex needs a *forecast*: given what the weather looks like at 8pm tonight, will there be fog at 5am tomorrow? Phase 1A.5 converts the same ASOS data into a proper forecast by using evening conditions (T-12h) to predict morning fog. No new data downloads needed — just a different way of assembling the training rows. If this passes the gate, we have a working 12-hour fog forecast with no HRRR required. This is the minimum viable forecasting model.

**Phase 1B (HRRR-augmented, full pipeline):** Add HRRR **forecast** atmospheric features (boundary layer height, soil moisture, low cloud fraction, longwave radiation) that ASOS doesn't report. These should push performance further. If they don't add much over Phase 1A.5, document why and decide whether to proceed.

**Gate between Phase 0 and Phase 1A:** If NBM + terrain weight already passes the gate, stop here. You have an MVP. Skip the ML pipeline entirely and proceed to app building.

**Gate between 1A and 1A.5:** Phase 1A showed the signal exists in ASOS features. Phase 1A.5 tests whether that signal survives a 12-hour prediction gap — i.e., can we predict fog tomorrow from tonight's conditions? If yes, we may not need HRRR at all.

**Gate between 1A.5 and 1B:** If the lagged ASOS model beats NBM, we have a working MVP forecast engine. HRRR adds spatial coverage and additional variables that could improve accuracy further, but is optional for the first app version.

**Tech Stack:** Python 3, local IDE (VS Code) + iCloud (Desktop auto-syncs, 1TB storage), IEM API (ASOS data), Herbie (HRRR forecast data), pandas, xarray, scikit-learn, XGBoost, matplotlib

**Comparison table — what each phase adds:**

| Model | What it represents | Requires |
|---|---|---|
| Baseline rule | Simple rule: T-Td ≤ 2°C + wind < 5 mph | Nothing |
| NBM raw | NOAA's professional forecast, unmodified | 1 day to set up |
| NBM + elevation weight | Our first terrain-aware product | 1 day |
| Phase 1A ML | Custom model, ASOS features only (detector) | ~1 week |
| Phase 1A.5 ML | Lagged ASOS model — real 12h forecast, no HRRR | ~1 day |
| Phase 1B ML | Custom model, HRRR forecast features | Several weeks |

**Key Decisions Baked In:**
- Fog definition: visibility < 1 km (WMO standard)
- **Lead time: 12 hours is the primary forecast.** The app UX is: open at 10pm, see a fog probability map for tomorrow morning (12h ahead). Tap a spot, see hourly probability (+1h through +12h). The model is trained across multiple lead times (f06, f09, f12, f18) with `lead_time_hours` as a feature — one model, not four separate ones.
- **Geographic holdout: DC metro stations excluded from training entirely.** This is the honest test. It also proves the model will generalize when expanding to other cities later.
- **HRRR forecast fields, not analysis fields.** Analysis = what actually happened (cheating). Forecast = what HRRR predicted 6/12/18 hours ahead. We train on forecast fields to match what the model will actually receive in production.
- **No `vsby_trend` feature.** Visibility trend at the time of fog is unavailable 12 hours before. Replaced with persistence: what conditions look like *at the time the forecast is issued*.
- Training data: national ASOS stations **excluding DC metro**, Jul 2018 – Dec 2023 (HRRRv3+v4, version-flagged)
- Test data: DC metro ASOS stations only, Jan 2024 – present
- Class imbalance strategy: XGBoost `scale_pos_weight` computed from the **actual training sample** (after HRRR sampling), not the original ASOS ratio
- Accuracy target: calibration — when model predicts 80%, fog occurs ~80% of the time

---

## Background: What Each Data Source Does

Before starting, understand the two data streams and why each is used.

**ASOS via IEM** — Real weather observations from airport sensors. Reports actual visibility, temperature, dew point, and wind speed every hour. We use them for: (1) the fog *label* (did fog actually occur?), and (2) persistence features — what conditions look like at the time a forecast is issued (10pm, for example).

**HRRR via Herbie** — A weather model's predictions of atmospheric conditions. For model training, we use HRRR's **forecast fields** — specifically, what HRRR predicted 6, 9, 12, or 18 hours in advance of the fog event. This is what the app will actually have available when it runs: a forecast, not a real-time observation. HRRR forecast fields give us HPBL, soil moisture, low cloud fraction, longwave radiation — variables ASOS doesn't report.

**The two rules:**
1. **ASOS visibility = fog label.** Never use HRRR's own visibility as a label — it is modeled, not observed, and is known to be biased.
2. **HRRR forecast fields = model features.** Not HRRR analysis (that's what actually happened — it's cheating because you wouldn't have that data in real life).

**Why the lead time framing matters for the app:** For the model to power a "+1h to +12h" hourly drill-down view, it needs to have been trained at each of those lead times. By including `lead_time_hours` as a feature and training across f06/f09/f12/f18, one model can answer "how likely is fog in 6 hours?" and "how likely is fog in 12 hours?" — the same model, different lead time input.

---

## Task 1: Set Up Local Environment

**What this does:** Install Python dependencies and create the data folder structure inside your project. Your Desktop is already iCloud-synced, so everything saves locally and backs up to iCloud automatically — no extra setup needed.

**Files:**
- Create: `notebooks/01_environment_setup.ipynb`

**Step 1: Check Python is installed**

Open your terminal and run:

```bash
python3 --version
```

Expected output: `Python 3.9.x` or higher. If you get "command not found", run `brew install python3` first.

**Step 2: Install dependencies**

In terminal, run:

```bash
pip3 install herbie-data xarray zarr s3fs pandas numpy scikit-learn xgboost matplotlib seaborn jupyter
```

Expected output: Each package installs without errors. This takes 2–3 minutes.

**Step 3: Create the data folder structure**

Open a new notebook in your IDE (VS Code: Cmd+Shift+P → "Create: New Jupyter Notebook"). Name it `01_environment_setup.ipynb` and save it inside your fogchaser folder under `notebooks/`.

Paste and run this:

```python
import os

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'

os.makedirs(f'{BASE_DIR}/data/raw/asos', exist_ok=True)
os.makedirs(f'{BASE_DIR}/data/raw/hrrr', exist_ok=True)
os.makedirs(f'{BASE_DIR}/data/processed', exist_ok=True)
os.makedirs(f'{BASE_DIR}/models', exist_ok=True)
os.makedirs(f'{BASE_DIR}/outputs', exist_ok=True)
print("Folders created at:", BASE_DIR)
```

Expected output: `Folders created at: /Users/dengzhenhua/...`

**Step 4: Verify key imports**

```python
import herbie
import xarray as xr
import pandas as pd
import numpy as np
from herbie import Herbie, FastHerbie
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import CalibrationDisplay
import xgboost as xgb
import matplotlib.pyplot as plt
print(f"Herbie version: {herbie.__version__}")
print("All imports successful.")
```

Expected output: Herbie version printed, no errors. If any import fails, run `pip3 install [package-name]` in terminal and retry.

**Step 5: Pin your BASE_DIR and RANDOM_SEED for all future notebooks**

Every notebook in this plan starts with these two lines — copy them exactly:

```python
BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'
RANDOM_SEED = 42  # All random operations use this variable — never hardcode 42 inline
```

**Step 6: Verify before committing**

Run this check — all lines must print without error:

```python
# Verify all folders exist
for folder in ['data/raw/asos', 'data/raw/hrrr', 'data/processed', 'models', 'outputs']:
    path = f'{BASE_DIR}/{folder}'
    assert os.path.exists(path), f"Missing folder: {path}"
    print(f"✅ {folder}")

# Verify all imports work
import herbie, xarray, pandas, numpy, sklearn, xgboost, matplotlib
print("✅ All imports successful")
```

If any assertion fails, re-run the folder creation step. If any import fails, run `pip3 install [package-name]` in terminal and retry the import cell.

**Step 7: Commit**

Save the notebook. Verify the new folders appear in Finder inside your fogchaser folder — they will sync to iCloud automatically.

---

## Task 2: DC Metro Fog Frequency Audit

**What this does:** Before building anything, find out how often fog actually occurs at DC metro stations. This gives us the real class imbalance number, which we need to set the XGBoost class weight correctly. The research agent estimated 2–5% of hours — we verify that here.

**Files:**
- Create: `notebooks/02_fog_frequency_audit.ipynb`
- Output: `data/processed/dc_metro_fog_audit.csv`

**Step 1: Pull ASOS data for DC metro stations from IEM**

The IEM provides free hourly ASOS downloads via a URL API. We pull temperature, dew point, wind speed, visibility, and present weather for our key stations.

```python
import requests
import pandas as pd
import io

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'

# DC metro primary stations — these are HELD OUT from training
DC_STATIONS = ['KDCA', 'KIAD', 'KBWI', 'KGAI', 'KFDK', 'KHEF', 'KNYG', 'KCGS']

def fetch_iem_asos(station, year_start, year_end):
    """Pull hourly ASOS data from IEM for a station and year range."""
    url = (
        f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
        f"?station={station}"
        f"&data=tmpf&data=dwpf&data=sknt&data=drct&data=vsby&data=wxcodes&data=metar"
        f"&year1={year_start}&month1=1&day1=1"
        f"&year2={year_end}&month2=12&day2=31"
        f"&tz=Etc/UTC&format=onlycomma&latlon=yes&elev=yes&direct=no&report_type=3"
    )
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text),
                     parse_dates=['valid'],
                     na_values=['M', 'T', ''])
    df['station'] = station
    return df

# Pull 2020-2024 for DC metro audit
audit_frames = []
for station in DC_STATIONS:
    print(f"Pulling {station}...")
    df = fetch_iem_asos(station, 2020, 2024)
    audit_frames.append(df)

audit_df = pd.concat(audit_frames, ignore_index=True)
audit_df.to_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_audit_2020_2024.parquet')
print(f"Downloaded {len(audit_df):,} rows across {audit_df['station'].nunique()} stations.")
```

Expected output: ~8 station names printed, row count in the hundreds of thousands.

**Step 2: Create fog label**

Visibility in ASOS data is in miles (`vsby` column). Fog definition: visibility < 1 km = 0.621 miles.

```python
audit_df = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_audit_2020_2024.parquet')

audit_df['vsby_km'] = audit_df['vsby'] * 1.60934
audit_df['is_fog'] = (audit_df['vsby_km'] < 1.0).astype(int)
audit_df = audit_df.dropna(subset=['vsby'])
print(f"Rows after dropping missing visibility: {len(audit_df):,}")
```

**Step 3: Compute class imbalance per station**

```python
summary = (audit_df
    .groupby('station')
    .agg(
        total_hours=('is_fog', 'count'),
        fog_hours=('is_fog', 'sum')
    )
    .assign(fog_pct=lambda x: (x['fog_hours'] / x['total_hours'] * 100).round(2))
    .sort_values('fog_pct', ascending=False)
)
print(summary.to_string())
summary.to_csv(f'{BASE_DIR}/data/processed/dc_metro_fog_audit.csv')
```

Expected output: A table showing each station, total hours, fog hours, and fog %. KIAD should be the foggiest (~2–5%), KDCA the least (~1–3%). If any station shows > 15% or < 0.5%, flag it as a data quality issue.

**Step 4: Compute overall class ratio (needed for XGBoost)**

```python
total_fog = audit_df['is_fog'].sum()
total_nonfog = (audit_df['is_fog'] == 0).sum()
class_ratio = total_nonfog / total_fog

print(f"Fog hours: {total_fog:,}")
print(f"Non-fog hours: {total_nonfog:,}")
print(f"Class ratio (non-fog / fog): {class_ratio:.1f}x")
print(f"Approximate XGBoost scale_pos_weight (refine in Task 5): {class_ratio:.0f}")
```

Note: This audit ratio is just for reference. The actual `scale_pos_weight` used in modeling will be computed from the training sample after HRRR sampling (Task 5), because sampling changes the ratio.

**Step 5: Check seasonal pattern**

```python
import matplotlib.pyplot as plt

audit_df['month'] = audit_df['valid'].dt.month
monthly = audit_df.groupby('month')['is_fog'].mean() * 100

plt.figure(figsize=(10, 4))
monthly.plot(kind='bar', color='steelblue')
plt.title('Fog frequency by month (DC metro, 2020–2024)')
plt.xlabel('Month')
plt.ylabel('% of hours with fog')
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/fog_frequency_by_month.png', dpi=150)
plt.show()
```

Expected pattern: Taller bars in Nov–Mar (months 11, 12, 1, 2, 3). If summer months are equally high, check for data quality issues.

**Step 6: Verify before committing**

```python
# Verify the audit CSV was written
import os
audit_path = f'{BASE_DIR}/data/processed/dc_metro_fog_audit.csv'
assert os.path.exists(audit_path), "Audit CSV not found — re-run Step 3"

audit_check = pd.read_csv(audit_path)
assert len(audit_check) > 0, "Audit CSV is empty"
assert 'fog_pct' in audit_check.columns, "Missing fog_pct column"

# Verify fog % is within plausible range for DC metro
assert audit_check['fog_pct'].max() < 20, f"Suspiciously high fog %: {audit_check['fog_pct'].max()}"
assert audit_check['fog_pct'].min() > 0, "Some station has 0% fog — check data quality"

print("✅ Fog audit verified")
print(audit_check[['station', 'fog_pct']].to_string(index=False))
```

If any assertion fails, check whether the IEM download returned data (the raw parquet file should have > 10,000 rows). If the parquet is empty, the IEM request may have timed out — re-run Step 1.

**Step 7: Commit**

Save the notebook. You now have confirmed fog frequency numbers to ground the rest of the plan.

---

## ✅ PHASE 0 CHECKPOINT — NBM Benchmark

**Run Task 2A before any ML work.** NBM is NOAA's professionally maintained, bias-corrected visibility forecast. It takes 1–2 days to set up and backtest. If it already passes the gate, skip Tasks 3–10 entirely and proceed to app building. The ML pipeline only runs if NBM has a gap worth filling.

---

## Task 2A: NBM Benchmark (Phase 0)

**What this does:** Pull NBM 12-hour visibility forecasts for DC metro stations, apply a simple elevation-based terrain weight, and backtest against observed ASOS fog events. Compare to the simple baseline rule. This tells you whether NOAA's existing product is already good enough for MVP — before investing weeks in ML.

**Why NBM and not raw HRRR for this test:** NBM is HRRR + bias correction + model blending. It represents the best operational forecast NOAA produces. If our custom ML model can't beat NBM, it's not adding meaningful value.

**What "terrain weight" means at this stage:** We don't have a DEM yet. For this early test, we use station elevation (available in the ASOS metadata): stations at lower elevation get a higher fog probability multiplier. It's a rough proxy, but good enough to see if terrain matters at all.

**Files:**
- Create: `notebooks/02a_nbm_benchmark.ipynb`
- Output: `outputs/nbm_benchmark_results.csv`

**Step 1: Pull NBM visibility forecasts for DC metro test period**

NBM forecasts are accessed via Herbie the same way as HRRR. The `product='co'` gives the CONUS blend at 2.5km resolution.

```python
import pandas as pd
import numpy as np
import os
from herbie import Herbie

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'
DC_STATIONS = ['KDCA', 'KIAD', 'KBWI', 'KGAI', 'KFDK', 'KHEF', 'KNYG', 'KCGS']

# Load the DC metro test data already pulled in Task 2
test_df = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_audit_2020_2024.parquet')
test_df['valid'] = pd.to_datetime(test_df['valid'], utc=True)
test_df['vsby_km'] = test_df['vsby'] * 1.60934
test_df['is_fog'] = (test_df['vsby_km'] < 1.0).astype(int)
test_df = test_df.dropna(subset=['vsby'])

# Get station coordinates and elevation from the ASOS data
station_meta = (test_df
    .groupby('station')[['lat', 'lon', 'elevation']]
    .first()
    .reset_index()
    .dropna()
)
print(station_meta.to_string(index=False))
```

Expected output: A table with station IDs, lat/lon, and elevation in feet. KDCA (Reagan National, on the Potomac) should be the lowest; KFDK (Frederick) and KIAD (Dulles) higher.

**Step 2: Test Herbie NBM access**

```python
# Test: pull NBM visibility for one timestamp
# fxx=12 means the 12-hour forecast
H = Herbie('2023-10-15 18:00', model='nbm', product='co', fxx=12)
ds_vis = H.xarray('VIS')
print(ds_vis)
print("NBM access working.")
print(f"Visibility range: {float(ds_vis.vis.min()):.0f} – {float(ds_vis.vis.max()):.0f} m")
```

Expected output: An xarray Dataset with a 2D visibility field in meters. Values should range from a few hundred meters (dense fog) to 16,000+ meters (clear).

**Step 3: Extract NBM visibility at DC metro station locations**

```python
def extract_nbm_vis_at_station(init_time_str, fxx, lat, lon):
    """Pull NBM forecast visibility (meters) at a lat/lon point."""
    try:
        H = Herbie(init_time_str, model='nbm', product='co', fxx=fxx)
        ds = H.xarray('VIS')
        lon_360 = lon + 360 if lon < 0 else lon
        val = ds.sel(latitude=lat, longitude=lon_360, method='nearest')
        var_name = list(val.data_vars)[0]
        return float(val[var_name].values)
    except Exception as e:
        return np.nan

# For each hour in the test set, get the NBM 12h forecast that would have been available
# NBM forecast valid at time T comes from the model run at T-12h
# We pull the unique valid hours and work backwards
test_df['valid_hour'] = test_df['valid'].dt.floor('H')
unique_valid_hours = test_df['valid_hour'].unique()

nbm_records = []
checkpoint_nbm = f'{BASE_DIR}/data/raw/hrrr/nbm_vis_checkpoint.parquet'

done_hours = set()
if os.path.exists(checkpoint_nbm):
    existing = pd.read_parquet(checkpoint_nbm)
    nbm_records = existing.to_dict('records')
    done_hours = set(existing['valid_hour'].astype(str))
    print(f"Resuming from checkpoint: {len(done_hours)} hours done.")

for i, valid_hour in enumerate(unique_valid_hours):
    if str(valid_hour) in done_hours:
        continue

    init_time = pd.Timestamp(valid_hour) - pd.Timedelta(hours=12)
    init_str = init_time.strftime('%Y-%m-%d %H:%M')

    for _, row in station_meta.iterrows():
        nbm_vis_m = extract_nbm_vis_at_station(init_str, fxx=12, lat=row['lat'], lon=row['lon'])
        nbm_records.append({
            'station': row['station'],
            'valid_hour': valid_hour,
            'nbm_vis_m': nbm_vis_m,
            'elev_ft': row['elevation']
        })

    if (i + 1) % 100 == 0:
        pd.DataFrame(nbm_records).to_parquet(checkpoint_nbm)
        print(f"Checkpoint: {i+1}/{len(unique_valid_hours)} hours done.")

nbm_df = pd.DataFrame(nbm_records)
nbm_df.to_parquet(f'{BASE_DIR}/data/raw/hrrr/nbm_vis_dc_metro.parquet')
print(f"Saved {len(nbm_df):,} NBM records.")
```

**Step 4: Merge NBM forecasts with ASOS observations**

```python
nbm_df = pd.read_parquet(f'{BASE_DIR}/data/raw/hrrr/nbm_vis_dc_metro.parquet')
nbm_df['valid_hour'] = pd.to_datetime(nbm_df['valid_hour'], utc=True)
test_df['valid_hour'] = pd.to_datetime(test_df['valid_hour'], utc=True)

merged = test_df.merge(nbm_df, on=['station', 'valid_hour'], how='inner')
print(f"Merged rows: {len(merged):,}, fog events: {merged['is_fog'].sum():,}")
```

**Step 5: Apply terrain weight using station elevation**

The terrain weight adjusts NBM's probability based on how low a station sits relative to the other DC stations. Lower elevation = more fog-prone. This is a simple linear scaling for now.

```python
# Invert elevation: lower elevation → higher terrain weight
# Normalize to 0.5–1.5 range (so it adjusts probability, doesn't dominate it)
elev_min = merged['elev_ft'].min()
elev_max = merged['elev_ft'].max()
merged['terrain_weight'] = 1.5 - (merged['elev_ft'] - elev_min) / (elev_max - elev_min)

# NBM fog probability: convert visibility to probability
# Raw: fog if NBM predicts visibility < 1 km (1000 m)
merged['nbm_fog_raw'] = (merged['nbm_vis_m'] < 1000).astype(float)

# Terrain-adjusted probability: scale the raw prediction by terrain weight, cap at 1.0
# This lifts probability for low-elevation stations and lowers it for ridges
merged['nbm_vis_adjusted'] = merged['nbm_vis_m'] / merged['terrain_weight']
merged['nbm_fog_terrain'] = (merged['nbm_vis_adjusted'] < 1000).astype(float)

print("Terrain weights by station:")
print(merged.groupby('station')[['elev_ft', 'terrain_weight']].first().sort_values('elev_ft').to_string())
```

**Step 6: Evaluate and compare**

```python
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score

y_true = merged['is_fog']

def evaluate_model(y_true, y_prob, model_name):
    y_pred = (y_prob >= 0.5).astype(int)
    auc_pr = average_precision_score(y_true, y_prob)
    brier = brier_score_loss(y_true, y_prob)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    print(f"\n{'='*40}")
    print(f"Model: {model_name}")
    print(f"  AUC-PR:    {auc_pr:.4f}  (random = {y_true.mean():.4f})")
    print(f"  Brier:     {brier:.4f}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    return {'model': model_name, 'auc_pr': auc_pr, 'brier': brier,
            'precision': precision, 'recall': recall}

results = []

# Baseline rule (same as before)
baseline_prob = (
    ((merged['tmpf'] - merged['dwpf']) <= 2.0) &
    (merged['sknt'] * 1.15078 < 5.0)
).astype(float)
results.append(evaluate_model(y_true, baseline_prob, "Baseline Rule"))

# NBM raw
results.append(evaluate_model(y_true, merged['nbm_fog_raw'], "NBM Raw (no terrain)"))

# NBM + terrain weight
results.append(evaluate_model(y_true, merged['nbm_fog_terrain'], "NBM + Elevation Weight"))

results_df = pd.DataFrame(results)
results_df.to_csv(f'{BASE_DIR}/outputs/nbm_benchmark_results.csv', index=False)
print("\n" + results_df.to_string(index=False))
```

**Step 7: Phase 0 checkpoint decision**

```python
random_auc = y_true.mean()
nbm_terrain_auc = results_df[results_df['model'] == 'NBM + Elevation Weight']['auc_pr'].values[0]
baseline_auc = results_df[results_df['model'] == 'Baseline Rule']['auc_pr'].values[0]
improvement = nbm_terrain_auc - baseline_auc

print("\n" + "="*50)
print("PHASE 0 CHECKPOINT")
print("="*50)
print(f"Baseline AUC-PR:         {baseline_auc:.4f}")
print(f"NBM + terrain AUC-PR:    {nbm_terrain_auc:.4f}")
print(f"Improvement over baseline: {improvement:.4f}")
print(f"NBM vs random ({random_auc:.4f}): {nbm_terrain_auc / random_auc:.1f}x")

if improvement > 0.05 and nbm_terrain_auc >= 3 * random_auc:
    print("\n✅ PASS — NBM + terrain already useful. Two options:")
    print("   OPTION A: Proceed to app with NBM as the forecast engine (no ML needed).")
    print("   OPTION B: Continue to Phase 1A to see if custom ML beats NBM.")
    print("   Recommendation: Try OPTION A first. Ship fast, validate with real users.")
else:
    print("\n❌ NBM alone not passing the gate. Proceed to Phase 1A (custom ML).")
    print("   This tells you NBM has a gap worth filling with a custom model.")
```

**Step 8: Commit**

Save notebook. This result shapes the rest of the plan — read it carefully before proceeding.

---

## Task 3: Pull National ASOS Training Data

**What this does:** Download the labeled fog events (and non-events) for a national set of ASOS stations, covering Jul 2018 – Dec 2023. This becomes the training set.

**Important: DC metro stations are excluded from this training pull.** This is the geographic holdout. The model learns fog patterns from everywhere else, then we test it on DC — a geography it has never seen. This is the honest test of whether the approach generalizes, and it means the same model can be applied to other cities later without needing to re-train from scratch.

**Files:**
- Create: `notebooks/03_asos_national_pull.ipynb`
- Output: `data/raw/asos/national_train_2018_2023.parquet`

**Step 1: Define national station list (excluding DC metro)**

```python
import requests
import pandas as pd
import io
import os

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'

# DC metro stations — DO NOT include in training
DC_STATIONS = ['KDCA', 'KIAD', 'KBWI', 'KGAI', 'KFDK', 'KHEF', 'KNYG', 'KCGS']

# State ASOS networks on IEM — covers Mid-Atlantic, Southeast, Midwest, Pacific Coast
TARGET_NETWORKS = [
    'MD_ASOS', 'VA_ASOS', 'DC_ASOS', 'WV_ASOS', 'PA_ASOS',  # Mid-Atlantic
    'NC_ASOS', 'TN_ASOS', 'KY_ASOS',                          # Southeast
    'OH_ASOS', 'IN_ASOS', 'IL_ASOS', 'MO_ASOS',               # Midwest
    'OR_ASOS', 'WA_ASOS', 'CA_ASOS',                           # Pacific (advection fog)
]

def get_stations_for_network(network):
    """Fetch station list from IEM for a given state network."""
    url = f"https://mesonet.agron.iastate.edu/geojson/network/{network}.geojson"
    response = requests.get(url, timeout=30)
    data = response.json()
    stations = [f['properties']['sid'] for f in data['features']]
    return stations

all_stations = []
for network in TARGET_NETWORKS:
    stations = get_stations_for_network(network)
    all_stations.extend(stations)
    print(f"{network}: {len(stations)} stations")

# Remove duplicates
all_stations = list(set(all_stations))

# Explicitly remove DC metro stations — geographic holdout
before_count = len(all_stations)
all_stations = [s for s in all_stations if s not in DC_STATIONS]
after_count = len(all_stations)
print(f"\nTotal unique stations: {before_count}")
print(f"After removing DC metro holdout: {after_count}")
print(f"Stations excluded (DC holdout): {[s for s in DC_STATIONS if s in all_stations]}")
```

Expected output: ~400–600 unique stations. Confirm that KDCA, KIAD, KBWI are not in the list.

**Step 2: Pull ASOS data in batches (2018–2023)**

This takes time — pull one year at a time to avoid timeouts.

```python
import time

def fetch_iem_asos(station, year_start, year_end):
    """Pull hourly ASOS data from IEM for a station and year range."""
    url = (
        f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"
        f"?station={station}"
        f"&data=tmpf&data=dwpf&data=sknt&data=drct&data=vsby&data=wxcodes&data=metar"
        f"&year1={year_start}&month1=1&day1=1"
        f"&year2={year_end}&month2=12&day2=31"
        f"&tz=Etc/UTC&format=onlycomma&latlon=yes&elev=yes&direct=no&report_type=3"
    )
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    df = pd.read_csv(io.StringIO(response.text),
                     parse_dates=['valid'],
                     na_values=['M', 'T', ''])
    df['station'] = station
    return df

def pull_year_for_stations(stations, year, output_dir):
    """Pull one year of ASOS data for all stations. Saves to parquet."""
    out_path = f'{output_dir}/asos_national_{year}.parquet'
    if os.path.exists(out_path):
        print(f"{year} already exists, skipping.")
        return

    year_frames = []
    for i, station in enumerate(stations):
        try:
            df = fetch_iem_asos(station, year, year)
            if len(df) > 100:
                year_frames.append(df)
        except Exception as e:
            print(f"  Error {station}: {e}")
        if i % 50 == 0:
            print(f"  {i}/{len(stations)} stations done...")
        time.sleep(0.1)

    combined = pd.concat(year_frames, ignore_index=True)
    combined.to_parquet(out_path)
    print(f"Saved {len(combined):,} rows for {year}.")

for year in range(2018, 2024):
    print(f"\n--- Pulling {year} ---")
    pull_year_for_stations(all_stations, year, f'{BASE_DIR}/data/raw/asos')
```

Expected output: 6 parquet files, one per year. Each should have several million rows.

**Step 3: Combine and create fog labels**

```python
frames = []
for year in range(2018, 2024):
    df = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/asos_national_{year}.parquet')
    frames.append(df)

national_df = pd.concat(frames, ignore_index=True)
national_df['valid'] = pd.to_datetime(national_df['valid'], utc=True)
national_df['vsby_km'] = national_df['vsby'] * 1.60934
national_df['is_fog'] = (national_df['vsby_km'] < 1.0).astype(int)
national_df = national_df.dropna(subset=['vsby', 'tmpf', 'dwpf'])

# Derive ASOS features
national_df['t_td_spread'] = national_df['tmpf'] - national_df['dwpf']
national_df['wind_speed_mph'] = national_df['sknt'] * 1.15078

# Verify DC stations are not present
dc_in_training = national_df[national_df['station'].isin(DC_STATIONS)]
assert len(dc_in_training) == 0, f"DC stations found in training data! {dc_in_training['station'].unique()}"
print("DC holdout verified: no DC metro stations in training set.")

national_df.to_parquet(f'{BASE_DIR}/data/raw/asos/national_train_2018_2023.parquet')
print(f"Final training set: {len(national_df):,} rows")
print(f"Fog events: {national_df['is_fog'].sum():,} ({national_df['is_fog'].mean()*100:.2f}%)")
```

**Step 4: Pull DC metro test data (Jan 2024 – present)**

```python
test_frames = []
for station in DC_STATIONS:
    df = fetch_iem_asos(station, 2024, 2026)
    test_frames.append(df)

test_df = pd.concat(test_frames, ignore_index=True)
test_df['valid'] = pd.to_datetime(test_df['valid'], utc=True)
test_df['vsby_km'] = test_df['vsby'] * 1.60934
test_df['is_fog'] = (test_df['vsby_km'] < 1.0).astype(int)
test_df = test_df.dropna(subset=['vsby', 'tmpf', 'dwpf'])
test_df['t_td_spread'] = test_df['tmpf'] - test_df['dwpf']
test_df['wind_speed_mph'] = test_df['sknt'] * 1.15078

test_df.to_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_test_2024_2026.parquet')
print(f"Test set: {len(test_df):,} rows, {test_df['is_fog'].sum()} fog events")
```

**Step 5: Commit**

Save notebook. You now have labeled training and test sets, with DC cleanly held out.

---

---

## ✅ PHASE 1A CHECKPOINT — ASOS-Only Early Signal

**Only run this if Phase 0 (NBM benchmark) failed the gate.** Tasks 1–3 give you labeled fog data. Task 3A trains models on ASOS-only features and checks if they beat NBM. If yes: there is signal the custom model is capturing that NBM misses — worth the HRRR pipeline investment. If no: the gap is not in the features, investigate the data quality first.

---

## Task 3A: ASOS-Only Model (Early Checkpoint)

**What this does:** Use only the features available in ASOS data — no HRRR needed. But now structured correctly: features represent what you'd know *at the time of issuing the forecast*, not at the time of fog.

**The lead time concept for ASOS-only:** Since ASOS doesn't have forecast fields, we approximate the 12-hour lead time by using current conditions as a proxy for what you'd know the night before. This is a simplification — the full HRRR pipeline (Phase 1B) does this properly with actual forecast fields. The ASOS-only checkpoint is just for a quick signal: does the physical relationship between these variables and fog actually show up in the data?

**ASOS-only features:**
- `t_td_spread` — temperature minus dew point (°F). The single strongest fog predictor. Low spread = air near saturation = fog-prone.
- `wind_speed_mph` — calm wind favors fog formation
- `persist_vsby_km` — current visibility (proxy for "how foggy is it right now at the forecast hour"). Not the same as vsby_trend.
- `hour_sin`, `hour_cos` — time of day (fog peaks pre-dawn)
- `month_sin`, `month_cos` — season (fog peaks Nov–Mar)
- `lead_time_hours` — set to 12 for this simplified model (we're approximating one lead time)

**Note on what's intentionally excluded:** `vsby_trend` (change in visibility over the previous hour) is NOT included. At 10pm when the forecast is issued, you don't have 4am's visibility data. Including it would make the model look better than it actually is — but the performance would evaporate when you tried to run it in real life.

**Files:**
- Create: `notebooks/03a_asos_only_model.ipynb`

**Step 1: Load training and test data, build features**

```python
import pandas as pd
import numpy as np
import os

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'
DC_STATIONS = ['KDCA', 'KIAD', 'KBWI', 'KGAI', 'KFDK', 'KHEF', 'KNYG', 'KCGS']

train = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/national_train_2018_2023.parquet')
test = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_test_2024_2026.parquet')

for df in [train, test]:
    df['valid'] = pd.to_datetime(df['valid'], utc=True)
    df['t_td_spread'] = df['tmpf'] - df['dwpf']
    df['wind_speed_mph'] = df['sknt'] * 1.15078
    df['hour_utc'] = df['valid'].dt.hour
    df['month'] = df['valid'].dt.month
    df['hour_sin'] = np.sin(2 * np.pi * df['hour_utc'] / 24)
    df['hour_cos'] = np.cos(2 * np.pi * df['hour_utc'] / 24)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
    df['vsby_km'] = df['vsby'] * 1.60934
    df['is_fog'] = (df['vsby_km'] < 1.0).astype(int)
    # Persistence: current visibility (what you'd observe at forecast issuance time)
    df['persist_vsby_km'] = df['vsby_km']
    # Approximate lead time (fixed at 12h for ASOS-only; Phase 1B uses real forecast horizons)
    df['lead_time_hours'] = 12

ASOS_FEATURES = [
    't_td_spread', 'wind_speed_mph', 'persist_vsby_km',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
    'lead_time_hours'
]

train_clean = train.dropna(subset=ASOS_FEATURES + ['is_fog'])
test_clean = test.dropna(subset=ASOS_FEATURES + ['is_fog'])

X_train = train_clean[ASOS_FEATURES]
y_train = train_clean['is_fog']
X_test = test_clean[ASOS_FEATURES]
y_test = test_clean['is_fog']

print(f"Training: {len(X_train):,} rows, {y_train.sum():,} fog events ({y_train.mean()*100:.2f}%)")
print(f"Test (DC metro): {len(X_test):,} rows, {y_test.sum():,} fog events ({y_test.mean()*100:.2f}%)")
```

**Step 2: Baseline rule**

```python
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score

def evaluate_model(y_true, y_prob, model_name, results_list):
    y_pred = (y_prob >= 0.5).astype(int)
    metrics = {
        'model': model_name,
        'auc_pr': average_precision_score(y_true, y_prob),
        'brier': brier_score_loss(y_true, y_prob),
        'precision': precision_score(y_true, y_pred, zero_division=0),
        'recall': recall_score(y_true, y_pred, zero_division=0),
    }
    results_list.append(metrics)
    print(f"\n{model_name}")
    for k, v in metrics.items():
        if k != 'model':
            print(f"  {k}: {v:.4f}")
    return metrics

results = []

# Baseline: T-Td spread ≤ 2°F AND wind < 5 mph
baseline_prob = (
    (test_clean['t_td_spread'] <= 2.0) &
    (test_clean['wind_speed_mph'] < 5.0)
).astype(float)

evaluate_model(y_test, baseline_prob, "Baseline Rule", results)
```

**Step 3: Logistic regression on ASOS features**

```python
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
lr.fit(X_train_scaled, y_train)

lr_prob = lr.predict_proba(X_test_scaled)[:, 1]
evaluate_model(y_test, lr_prob, "Logistic Regression (ASOS only)", results)
```

**Step 4: XGBoost on ASOS features**

```python
import xgboost as xgb
from sklearn.model_selection import train_test_split

class_ratio = (y_train == 0).sum() / (y_train == 1).sum()
print(f"scale_pos_weight: {class_ratio:.1f}")

X_tr, X_val, y_tr, y_val = train_test_split(
    X_train, y_train, test_size=0.1, random_state=42, stratify=y_train
)

xgb_asos = xgb.XGBClassifier(
    n_estimators=300,
    max_depth=5,
    learning_rate=0.05,
    scale_pos_weight=class_ratio,
    eval_metric='aucpr',
    early_stopping_rounds=20,
    random_state=42,
    tree_method='hist',
)
xgb_asos.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=50)

xgb_prob = xgb_asos.predict_proba(X_test)[:, 1]
evaluate_model(y_test, xgb_prob, "XGBoost (ASOS only)", results)
```

**Step 5: Checkpoint decision**

```python
results_df = pd.DataFrame(results)
baseline_auc = results_df[results_df['model'] == 'Baseline Rule']['auc_pr'].values[0]
best_auc = results_df[results_df['model'] != 'Baseline Rule']['auc_pr'].max()
improvement = best_auc - baseline_auc
random_auc = y_test.mean()

print("\n" + "="*50)
print("PHASE 1A CHECKPOINT")
print("="*50)
print(results_df.to_string(index=False))
print(f"\nAUC-PR improvement over baseline: {improvement:.4f}")
print(f"Best model vs random ({random_auc:.4f}): {best_auc/random_auc:.1f}x")

# Also compare against NBM benchmark from Phase 0
nbm_results = pd.read_csv(f'{BASE_DIR}/outputs/nbm_benchmark_results.csv')
nbm_auc = nbm_results[nbm_results['model'] == 'NBM + Elevation Weight']['auc_pr'].values[0]
beats_nbm = best_auc > nbm_auc

print(f"\nNBM + terrain AUC-PR (Phase 0):  {nbm_auc:.4f}")
print(f"Best ML model AUC-PR (Phase 1A): {best_auc:.4f}")
print(f"ML beats NBM: {'✅ YES' if beats_nbm else '❌ NO'}")

if improvement > 0.05 and best_auc >= 3 * random_auc and beats_nbm:
    print("\n✅ PASS — ASOS-only ML beats both baseline and NBM. Proceed to Phase 1B (HRRR features).")
elif improvement > 0.05 and best_auc >= 3 * random_auc and not beats_nbm:
    print("\n⚠️  ML beats baseline but NOT NBM.")
    print("   NBM is already doing better than our custom model with ASOS features.")
    print("   Options:")
    print("   1. Proceed to Phase 1B (HRRR) — HRRR features may push ML above NBM.")
    print("   2. Accept NBM as MVP forecast engine — no custom ML needed.")
else:
    print("\n❌ STOP — Model not beating baseline with ASOS features alone.")
    print("   Do NOT proceed to HRRR pipeline. Investigate first:")
    print("   1. Are fog labels correct? Spot-check a few rows.")
    print("   2. Is the t_td_spread feature sensible? Print min/max/mean for fog vs no-fog rows.")
    print("   3. Is class imbalance too severe? Check fog % in training set.")
```

**Step 6: Save checkpoint results**

```python
results_df.to_csv(f'{BASE_DIR}/outputs/phase1a_checkpoint_results.csv', index=False)
xgb_asos.save_model(f'{BASE_DIR}/models/xgb_asos_only_v1.json')
print("Checkpoint results saved.")
```

**Step 7: Commit**

Save notebook. Do not proceed to Task 4 until this checkpoint passes.

---

## ⏩ PHASE 1A.5 — Lagged ASOS Forecast Model (run before HRRR)

**Why this phase exists:** Phase 1A proved that fog signal exists in ASOS features. But the Phase 1A model was a *detector* — it used temperature spread and wind speed from the *same timestamp* as the fog event. That's not a forecast. Alex needs to decide at 8pm whether to wake up at 5am. Phase 1A.5 tests whether the signal survives a 12-hour prediction gap.

**The key insight from fog physics:** Radiative fog (the most common type around DC and Shenandoah) forms overnight through a specific chain: clear sky → surface radiates heat → air cools → if temperature reaches the dew point, water droplets form. If the air at sunset is already moist and calm (narrow T-Td spread, low wind speed), overnight cooling will almost certainly close the gap and produce fog by dawn. That means *evening conditions are a genuine predictor of morning fog* — not just a correlation, but a physically grounded mechanism.

**What changes from Phase 1A:** Instead of using features from time T to predict fog at time T, we use features from time T-12h (the evening before) to predict fog at time T (the next morning). We build this by joining each training observation with the same station's reading from 12 hours earlier — no new downloads, just a different assembly of the same rows.

**Feature set:**
- From T-12h (the "evening before" reading): `t_td_spread_lag`, `wind_speed_mph_lag`, `vsby_km_lag`
- From T (the target time): `hour_sin`, `hour_cos` (what time is the forecast for?), `month_sin`, `month_cos` (what season?), `station_code`

**Files:**
- Create: `notebooks/03b_lagged_asos_forecast.ipynb`
- Output: `models/xgb_lagged_asos_v1.json`, `outputs/phase1a5_checkpoint_results.csv`

---

## Task 3B: Lagged ASOS Forecast Model

**Step 1: Build lagged training pairs**

```python
import sys
sys.path.insert(0, '/Users/dengzhenhua/Library/Python/3.9/lib/python/site-packages')
import pandas as pd
import numpy as np

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/work/vibe coding/fogchaser'
RANDOM_SEED = 42
LAG_HOURS = 12

train_raw = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/national_train_2018_2023.parquet')
train_raw['valid'] = pd.to_datetime(train_raw['valid'], utc=True)
train_raw['valid_hour'] = train_raw['valid'].dt.floor('h')  # round to hour
train_raw['vsby_km'] = train_raw['vsby'] * 1.60934
train_raw['is_fog'] = (train_raw['vsby_km'] < 1.0).astype(int)
train_raw['t_td_spread'] = train_raw['tmpf'] - train_raw['dwpf']
train_raw['wind_speed_mph'] = train_raw['sknt'] * 1.15078

# Keep one row per (station, hour) — last observation in each hour
hourly = train_raw.sort_values('valid').groupby(['station', 'valid_hour']).last().reset_index()

# Build lag: create a shifted copy of features, join on station + (valid_hour + 12h)
lag_cols = ['t_td_spread', 'wind_speed_mph', 'vsby_km']
lag_df = hourly[['station', 'valid_hour'] + lag_cols].copy()
lag_df['valid_hour_target'] = lag_df['valid_hour'] + pd.Timedelta(hours=LAG_HOURS)
lag_df = lag_df.rename(columns={c: f'{c}_lag' for c in lag_cols})

# Merge: each target row gets its lag features from 12h earlier
train_lagged = hourly.merge(
    lag_df[['station', 'valid_hour_target'] + [f'{c}_lag' for c in lag_cols]],
    left_on=['station', 'valid_hour'],
    right_on=['station', 'valid_hour_target'],
    how='inner'
).drop(columns='valid_hour_target')

print(f"Training rows after lag join: {len(train_lagged):,}")
print(f"Fog events: {train_lagged['is_fog'].sum():,} ({train_lagged['is_fog'].mean()*100:.2f}%)")
```

**Step 2: Add cyclical time features and station encoding**

```python
train_lagged['hour_utc'] = train_lagged['valid_hour'].dt.hour
train_lagged['month'] = train_lagged['valid_hour'].dt.month
train_lagged['hour_sin'] = np.sin(2 * np.pi * train_lagged['hour_utc'] / 24)
train_lagged['hour_cos'] = np.cos(2 * np.pi * train_lagged['hour_utc'] / 24)
train_lagged['month_sin'] = np.sin(2 * np.pi * train_lagged['month'] / 12)
train_lagged['month_cos'] = np.cos(2 * np.pi * train_lagged['month'] / 12)

# Station encoding — must be shared with test set
test_raw = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_test_2024_2026.parquet')
all_stations_combined = sorted(set(train_lagged['station']) | set(test_raw['station']))
station_cat = pd.CategoricalDtype(categories=all_stations_combined, ordered=False)
train_lagged['station_code'] = train_lagged['station'].astype(station_cat).cat.codes

LAG_FEATURES = [
    't_td_spread_lag', 'wind_speed_mph_lag', 'vsby_km_lag',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
    'station_code'
]

train_clean = train_lagged.dropna(subset=LAG_FEATURES + ['is_fog'])

# Rule 2: null rates
null_rates = train_clean[LAG_FEATURES].isnull().mean()
for col, rate in null_rates.items():
    flag = ' ⚠️ >10% — STOP' if rate > 0.10 else ''
    print(f'  {col}: {rate*100:.2f}%{flag}')
assert null_rates.max() <= 0.10, f'Column with >10% nulls found'
print('✅ Null rates acceptable')
```

**Step 3: Build test set with same lag structure**

```python
test_raw['valid'] = pd.to_datetime(test_raw['valid'], utc=True)
test_raw['valid_hour'] = test_raw['valid'].dt.floor('h')
test_raw['vsby_km'] = test_raw['vsby'] * 1.60934
test_raw['is_fog'] = (test_raw['vsby_km'] < 1.0).astype(int)
test_raw['t_td_spread'] = test_raw['tmpf'] - test_raw['dwpf']
test_raw['wind_speed_mph'] = test_raw['sknt'] * 1.15078

test_hourly = test_raw.sort_values('valid').groupby(['station', 'valid_hour']).last().reset_index()

test_lag_df = test_hourly[['station', 'valid_hour'] + lag_cols].copy()
test_lag_df['valid_hour_target'] = test_lag_df['valid_hour'] + pd.Timedelta(hours=LAG_HOURS)
test_lag_df = test_lag_df.rename(columns={c: f'{c}_lag' for c in lag_cols})

test_lagged = test_hourly.merge(
    test_lag_df[['station', 'valid_hour_target'] + [f'{c}_lag' for c in lag_cols]],
    left_on=['station', 'valid_hour'],
    right_on=['station', 'valid_hour_target'],
    how='inner'
).drop(columns='valid_hour_target')

test_lagged['hour_utc'] = test_lagged['valid_hour'].dt.hour
test_lagged['month'] = test_lagged['valid_hour'].dt.month
test_lagged['hour_sin'] = np.sin(2 * np.pi * test_lagged['hour_utc'] / 24)
test_lagged['hour_cos'] = np.cos(2 * np.pi * test_lagged['hour_utc'] / 24)
test_lagged['month_sin'] = np.sin(2 * np.pi * test_lagged['month'] / 12)
test_lagged['month_cos'] = np.cos(2 * np.pi * test_lagged['month'] / 12)
test_lagged['station_code'] = test_lagged['station'].astype(station_cat).cat.codes

test_clean = test_lagged.dropna(subset=LAG_FEATURES + ['is_fog'])

# Rule 3: temporal integrity
assert train_clean['valid_hour'].max() < test_clean['valid_hour'].min(), 'Temporal leakage!'
print(f'Temporal integrity OK: train ends {train_clean["valid_hour"].max().date()}, test starts {test_clean["valid_hour"].min().date()}')
print(f'Test: {len(test_clean):,} rows, {test_clean["is_fog"].sum():,} fog events ({test_clean["is_fog"].mean()*100:.2f}%)')
```

**Step 4: Train XGBoost on lagged features**

```python
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import average_precision_score, brier_score_loss, precision_score, recall_score

X_train = train_clean[LAG_FEATURES]
y_train = train_clean['is_fog']
X_test = test_clean[LAG_FEATURES]
y_test = test_clean['is_fog']

class_ratio = (y_train == 0).sum() / (y_train == 1).sum()
print(f'scale_pos_weight: {class_ratio:.1f}')

X_tr, X_val, y_tr, y_val = train_test_split(
    X_train, y_train, test_size=0.1, random_state=RANDOM_SEED, stratify=y_train
)

xgb_lagged = xgb.XGBClassifier(
    n_estimators=300, max_depth=5, learning_rate=0.05,
    scale_pos_weight=class_ratio, eval_metric='aucpr',
    early_stopping_rounds=20, random_state=RANDOM_SEED, tree_method='hist'
)
xgb_lagged.fit(X_tr, y_tr, eval_set=[(X_val, y_val)], verbose=50)

prob = xgb_lagged.predict_proba(X_test)[:, 1]
auc = average_precision_score(y_test, prob)
print(f'Lagged ASOS XGBoost AUC-PR: {auc:.4f}')
```

**Step 5: Compare against NBM on identical rows (same clean comparison as Phase 1A)**

Follow the same fair-comparison approach used in Phase 1A: join with `nbm_vis_dc_metro.parquet` rows, filter to 2024 only, score both NBM and this lagged model on identical rows.

**Step 6: Physical sense check (Rule 8)**

Print top 20 highest-confidence predictions. Verify the *lag features* look physically sensible — low t_td_spread_lag (moist evening), low wind_speed_mph_lag (calm evening), and the target hour is pre-dawn.

**Step 7: Save and log**

```python
xgb_lagged.save_model(f'{BASE_DIR}/models/xgb_lagged_asos_v1.json')
results_df.to_csv(f'{BASE_DIR}/outputs/phase1a5_checkpoint_results.csv', index=False)
```

**Gate:** If lagged AUC-PR > NBM on 2024-only comparison → the model is a genuine 12-hour fog forecast. Proceed to app design or Phase 1B. If not → the 12-hour signal doesn't survive; HRRR features (boundary layer height, soil moisture) are likely needed.

---

## ⏩ PHASE 1B — Add HRRR Features (only if Phase 1A passes)

**Why bother with HRRR if ASOS already works?** ASOS tells us what conditions are like *at the airport right now*. HRRR tells us what the atmosphere is predicted to do *across the whole region* in the future — including places with no ASOS sensors (valley floors, river corridors). For a fog discovery app that maps fog probability across DC metro, we need spatial coverage. HRRR also gives us planetary boundary layer height and soil moisture that ASOS doesn't report at all, and that the literature shows are strong fog predictors.

**The key shift in Phase 1B:** We use HRRR *forecast* fields, not analysis. For a fog event at 6am, we pull what HRRR predicted at 6, 9, 12, and 18 hours in advance. This is what the model will actually receive when running in production.

---

## Task 4: Extract HRRR Forecast Features for Training Stations

**What this does:** For each fog event in the training set, pull HRRR's *forecast* of atmospheric conditions at that time — at four different lead times (6h, 9h, 12h, 18h ahead). Each fog event becomes four training rows, one per lead time. `lead_time_hours` becomes a feature the model uses.

**Why multiple lead times:** The app shows fog probability from +1h to +12h. By training across lead times, one model can answer both "how likely is fog in 6 hours?" and "how likely is fog in 12 hours?" — the lead time is just another input.

**How HRRR forecast fields work:** If fog occurs at 06Z on Jan 16, the 12-hour forecast for that event comes from the HRRR model run initialized at 18Z on Jan 15. Herbie retrieves this as: `Herbie('2022-01-15 18:00', model='hrrr', fxx=12)`. The `fxx` parameter is the forecast hour.

**Files:**
- Create: `notebooks/04_hrrr_forecast_extraction.ipynb`
- Output: `data/raw/hrrr/hrrr_features_train.parquet`

**Step 1: Get station coordinates**

```python
import pandas as pd
import numpy as np
import os
from herbie import Herbie

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'
DC_STATIONS = ['KDCA', 'KIAD', 'KBWI', 'KGAI', 'KFDK', 'KHEF', 'KNYG', 'KCGS']

national_df = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/national_train_2018_2023.parquet')
station_coords = (national_df
    .groupby('station')[['lat', 'lon']]
    .first()
    .reset_index()
    .dropna()
)
print(f"Training stations with coordinates: {len(station_coords)}")

# Verify DC is not present
assert not any(station_coords['station'].isin(DC_STATIONS)), "DC stations found in training coords!"
print("DC holdout verified in station coords.")
```

**Step 2: Define HRRR forecast variables to pull**

```python
# These are the HRRR surface variables available via Herbie
# 'searchString' values are GRIB2 variable names used by Herbie
HRRR_VARS = {
    'TMP:2 m':    'hrrr_temp_k',       # 2m temperature (Kelvin)
    'DPT:2 m':    'hrrr_dewp_k',       # 2m dew point (Kelvin)
    'RH:2 m':     'hrrr_rh',           # Relative humidity (%)
    'UGRD:10 m':  'hrrr_ugrd',         # 10m wind U-component (m/s)
    'VGRD:10 m':  'hrrr_vgrd',         # 10m wind V-component (m/s)
    'HPBL':       'hrrr_hpbl',         # Planetary boundary layer height (m)
    'LCDC':       'hrrr_lcdc',         # Low cloud fraction (%)
    'SOILW:0-0.1 m': 'hrrr_soilw',    # Soil moisture 0-10cm
    'DLWRF':      'hrrr_dlwrf',        # Downward longwave radiation (W/m²)
    'VIS':        'hrrr_vis',          # Modeled visibility (m) — feature only, not label
}

LEAD_TIMES = [6, 9, 12, 18]  # forecast hours to extract
```

**Step 3: Test Herbie connection for one timestamp**

Before running the full extraction, verify access works and the variable names are correct.

```python
# Test: pull 2m temperature for a known HRRR run
# This fetches the HRRR run initialized at 2022-01-15 18Z, forecast hour 12
# = what HRRR predicted for 2022-01-16 06Z, 12 hours in advance
H = Herbie('2022-01-15 18:00', model='hrrr', product='sfc', fxx=12)
print(H)

# Pull temperature field
ds_tmp = H.xarray('TMP:2 m')
print(ds_tmp)
print("Herbie forecast access working.")
print(f"Grid shape: {ds_tmp.t2m.shape}")
print(f"Value range: {float(ds_tmp.t2m.min()):.1f} – {float(ds_tmp.t2m.max()):.1f} K")
```

Expected output: An xarray Dataset with a 2D temperature field. Values should be in Kelvin (~250–310 K). If you get an error, check the `searchString` syntax — Herbie is picky about exact variable names.

**Step 4: Test point extraction at station locations**

```python
def extract_point_from_ds(ds, lat, lon):
    """Extract the HRRR grid value nearest to a station lat/lon."""
    # Herbie xarray output uses 'latitude' and 'longitude' coordinate names
    # and longitude is in 0–360 range for HRRR
    lon_360 = lon + 360 if lon < 0 else lon
    val = ds.sel(
        latitude=lat,
        longitude=lon_360,
        method='nearest'
    )
    # Get the first data variable's value
    var_name = list(val.data_vars)[0]
    return float(val[var_name].values)

def extract_hrrr_forecast_at_stations(init_time, fxx, station_coords_df):
    """
    Pull HRRR forecast initialized at init_time with lead time fxx hours.
    Returns a DataFrame with one row per station and one column per variable.
    valid_time = init_time + fxx hours.
    """
    results = []
    valid_time = pd.Timestamp(init_time) + pd.Timedelta(hours=fxx)

    for search_str, col_name in HRRR_VARS.items():
        try:
            H = Herbie(init_time, model='hrrr', product='sfc', fxx=fxx)
            ds = H.xarray(search_str)

            for _, row in station_coords_df.iterrows():
                val = extract_point_from_ds(ds, row['lat'], row['lon'])
                results.append({
                    'station': row['station'],
                    'valid_time': valid_time,
                    'init_time': pd.Timestamp(init_time),
                    'lead_time_hours': fxx,
                    col_name: val
                })
        except Exception as e:
            print(f"  Warning — {search_str} fxx={fxx}: {e}")

    if not results:
        return pd.DataFrame()

    # Pivot: one row per (station, valid_time, lead_time)
    df = pd.DataFrame(results)
    df = df.groupby(['station', 'valid_time', 'init_time', 'lead_time_hours']).first().reset_index()
    return df

# Test on a few stations
sample_stations = station_coords.head(3)
sample_result = extract_hrrr_forecast_at_stations('2022-01-15 18:00', fxx=12, station_coords_df=sample_stations)
print(sample_result)
print(f"\nColumns: {sample_result.columns.tolist()}")
```

Expected output: A DataFrame with 3 rows (one per station), columns for each HRRR variable, `lead_time_hours=12`. Temperature values should be ~280–290 K for a winter date.

**Step 5: Build the list of (init_time, fxx) pairs to extract**

For each fog event hour in the training set, we need forecasts from 4 different HRRR runs. Strategy: keep all fog event hours plus 1-in-6 non-fog hours (to keep download volume manageable).

```python
national_df['valid'] = pd.to_datetime(national_df['valid'], utc=True)
national_df['valid_hour'] = national_df['valid'].dt.floor('H')
national_df['vsby_km'] = national_df['vsby'] * 1.60934
national_df['is_fog'] = (national_df['vsby_km'] < 1.0).astype(int)

fog_hours = national_df[national_df['is_fog'] == 1]['valid_hour'].unique()
all_hours = national_df['valid_hour'].unique()
nonfog_hours = np.setdiff1d(all_hours, fog_hours)
sampled_nonfog = nonfog_hours[::6]

target_valid_hours = np.union1d(fog_hours, sampled_nonfog)
target_valid_hours = np.sort(target_valid_hours)
print(f"Fog hours: {len(fog_hours):,}")
print(f"Sampled non-fog hours: {len(sampled_nonfog):,}")
print(f"Total valid times to cover: {len(target_valid_hours):,}")

# For each valid time, compute the init_time for each lead time
extraction_jobs = []
for valid_time in target_valid_hours:
    vt = pd.Timestamp(valid_time)
    for fxx in LEAD_TIMES:
        init_time = vt - pd.Timedelta(hours=fxx)
        # HRRR runs on the hour, so init_time must be on the hour — it already is
        extraction_jobs.append({'valid_time': vt, 'init_time': init_time, 'fxx': fxx})

print(f"Total HRRR extraction jobs: {len(extraction_jobs):,}  ({len(target_valid_hours):,} times × {len(LEAD_TIMES)} lead times)")
```

**Step 6: Run full HRRR forecast extraction with checkpointing**

This is the most time-intensive step. It will take several hours. The checkpoint saves progress every 200 valid times so you can resume if interrupted.

```python
checkpoint_path = f'{BASE_DIR}/data/raw/hrrr/hrrr_forecast_checkpoint.parquet'
failure_log_path = f'{BASE_DIR}/data/raw/hrrr/hrrr_extraction_failures.csv'
hrrr_records = []
failure_log = []  # Rule 6: log every failure for post-run analysis

# Load checkpoint if resuming
done_keys = set()
if os.path.exists(checkpoint_path):
    existing = pd.read_parquet(checkpoint_path)
    hrrr_records = existing.to_dict('records')
    done_keys = set(
        zip(existing['valid_time'].astype(str), existing['lead_time_hours'].astype(str))
    )
    print(f"Resuming from checkpoint: {len(done_keys)} (valid_time, fxx) pairs already done.")

jobs_remaining = [
    j for j in extraction_jobs
    if (str(j['valid_time']), str(j['fxx'])) not in done_keys
]
print(f"Jobs remaining: {len(jobs_remaining):,}")

checkpoint_every = 200  # save every N valid times processed
processed_count = 0
last_valid = None

for job in jobs_remaining:
    if job['valid_time'] != last_valid:
        # New valid time — extract all lead times for this batch together
        last_valid = job['valid_time']
        processed_count += 1

    try:
        result_df = extract_hrrr_forecast_at_stations(
            init_time=job['init_time'],
            fxx=job['fxx'],
            station_coords_df=station_coords
        )
        if not result_df.empty:
            hrrr_records.extend(result_df.to_dict('records'))
    except Exception as e:
        failure_log.append({'init_time': str(job['init_time']), 'fxx': job['fxx'], 'error': str(e)})

    if processed_count % checkpoint_every == 0:
        pd.DataFrame(failure_log).to_csv(failure_log_path, index=False)  # Rule 6: persist failure log
        pd.DataFrame(hrrr_records).to_parquet(checkpoint_path)
        print(f"Checkpoint: {processed_count} valid times processed.")

hrrr_df = pd.DataFrame(hrrr_records)
hrrr_df.to_parquet(f'{BASE_DIR}/data/raw/hrrr/hrrr_features_train.parquet')
print(f"Saved {len(hrrr_df):,} HRRR forecast records.")
print(f"Lead times present: {hrrr_df['lead_time_hours'].value_counts().to_dict()}")

# Rule 6: Monitor extraction failure rate
total_jobs = len(extraction_jobs)
successful_valid_times = hrrr_df['valid_time'].nunique() if 'valid_time' in hrrr_df.columns else 0
expected_valid_times = len(target_valid_hours)
failure_rate = 1 - (successful_valid_times / expected_valid_times)
print(f"\nExtraction failure rate: {failure_rate*100:.1f}%  ({expected_valid_times - successful_valid_times} of {expected_valid_times} valid times missing)")
if failure_rate > 0.15:
    print("⚠️  STOP — failure rate exceeds 15%. Check logs/hrrr_failures.log for patterns.")
    print("   Do not proceed to feature engineering on a dataset with this many gaps.")
else:
    print(f"✅ Failure rate acceptable ({failure_rate*100:.1f}% < 15%)")
```

**Step 7: Extract HRRR forecast features for DC metro test set**

```python
test_df = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_test_2024_2026.parquet')
test_df['valid'] = pd.to_datetime(test_df['valid'], utc=True)
test_df['valid_hour'] = test_df['valid'].dt.floor('H')

dc_station_coords = station_coords[station_coords['station'].isin(DC_STATIONS)]

# For the test set, we only need the primary lead time (12h) for the main evaluation
# We'll also extract f06 for the drill-down performance check in Task 9
test_lead_times = [6, 12]

test_jobs = []
for valid_time in test_df['valid_hour'].unique():
    vt = pd.Timestamp(valid_time)
    for fxx in test_lead_times:
        init_time = vt - pd.Timedelta(hours=fxx)
        test_jobs.append({'valid_time': vt, 'init_time': init_time, 'fxx': fxx})

hrrr_test_records = []
for job in test_jobs:
    try:
        result_df = extract_hrrr_forecast_at_stations(
            init_time=job['init_time'],
            fxx=job['fxx'],
            station_coords_df=dc_station_coords
        )
        if not result_df.empty:
            hrrr_test_records.extend(result_df.to_dict('records'))
    except Exception as e:
        print(f"  Skipping {job['init_time']} fxx={job['fxx']}: {e}")

hrrr_test_df = pd.DataFrame(hrrr_test_records)
hrrr_test_df.to_parquet(f'{BASE_DIR}/data/raw/hrrr/hrrr_features_test.parquet')
print(f"Saved {len(hrrr_test_df):,} HRRR test records.")
```

**Step 8: Verify HRRR extraction before committing**

```python
hrrr_check = pd.read_parquet(f'{BASE_DIR}/data/raw/hrrr/hrrr_features_train.parquet')

assert len(hrrr_check) > 0, "HRRR training file is empty — extraction failed"

# Must have all 4 lead times
lead_times_found = set(hrrr_check['lead_time_hours'].unique())
assert {6, 9, 12, 18}.issubset(lead_times_found), \
    f"Missing lead times: {({6,9,12,18}) - lead_times_found}"

# Temperature must be physically sensible (Kelvin: ~250–320 K)
assert hrrr_check['hrrr_temp_k'].between(240, 330).mean() > 0.99, \
    "Temperature values outside expected Kelvin range — check units or variable name"

# HPBL must be positive and not absurdly large
assert hrrr_check['hrrr_hpbl'].between(0, 5000).mean() > 0.95, \
    "HPBL values out of range — check extraction"

# DC stations must NOT be present (geographic holdout)
if 'station' in hrrr_check.columns:
    DC_STATIONS = ['KDCA', 'KIAD', 'KBWI', 'KGAI', 'KFDK', 'KHEF', 'KNYG', 'KCGS']
    dc_found = hrrr_check[hrrr_check['station'].isin(DC_STATIONS)]
    assert len(dc_found) == 0, f"DC stations found in HRRR training data — holdout violated!"

print(f"✅ HRRR training data: {len(hrrr_check):,} rows")
print(f"✅ Lead times: {sorted(lead_times_found)}")
print(f"✅ Temperature range: {hrrr_check['hrrr_temp_k'].min():.1f}–{hrrr_check['hrrr_temp_k'].max():.1f} K")
print(f"✅ HPBL range: {hrrr_check['hrrr_hpbl'].min():.0f}–{hrrr_check['hrrr_hpbl'].max():.0f} m")
print("✅ DC holdout confirmed: no DC stations in training HRRR data")
```

If any assertion fails, do not proceed to Task 5. Bad HRRR data will silently corrupt the feature matrix.

**Step 9: Commit**

Save notebook. You now have HRRR forecast features (not analysis) for both train and test sets, at multiple lead times.

---

## Task 5: Feature Engineering — Merge and Derive

**What this does:** Combine the ASOS labels with HRRR forecast features, add persistence features (what conditions look like at forecast issuance time), and build the final feature matrix for modeling.

**Files:**
- Create: `notebooks/05_feature_engineering.ipynb`
- Output: `data/processed/train_features.parquet`, `data/processed/test_features.parquet`

**Step 1: Load and merge training data**

```python
import pandas as pd
import numpy as np
import os

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'

asos_train = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/national_train_2018_2023.parquet')
hrrr_train = pd.read_parquet(f'{BASE_DIR}/data/raw/hrrr/hrrr_features_train.parquet')

asos_train['valid'] = pd.to_datetime(asos_train['valid'], utc=True)
hrrr_train['valid_time'] = pd.to_datetime(hrrr_train['valid_time'], utc=True)

# Round ASOS timestamps to the hour to match HRRR valid times
asos_train['valid_hour'] = asos_train['valid'].dt.floor('H')

# Merge on station + valid hour + lead time
# hrrr_train has one row per (station, valid_time, lead_time_hours)
train = asos_train.merge(
    hrrr_train.rename(columns={'valid_time': 'valid_hour'}),
    on=['station', 'valid_hour'],
    how='inner'
)
print(f"Merged training rows: {len(train):,}")
print(f"Lead times present: {train['lead_time_hours'].value_counts().to_dict()}")
print(f"Fog events in merged set: {train['is_fog'].sum():,} ({train['is_fog'].mean()*100:.2f}%)")

# Rule 11: Cross-source sanity check — HRRR and ASOS temperature should roughly agree
# ASOS tmpf is in Fahrenheit; convert to Celsius for comparison
train['asos_temp_c'] = (train['tmpf'] - 32) * 5/9
train['hrrr_temp_c_check'] = train['hrrr_temp_k'] - 273.15
train['temp_delta_c'] = (train['hrrr_temp_c_check'] - train['asos_temp_c']).abs()
pct_within_10c = (train['temp_delta_c'] < 10).mean()
print(f"\nCross-source temperature agreement (within 10°C): {pct_within_10c*100:.1f}%")
if pct_within_10c < 0.95:
    print("⚠️  STOP — HRRR and ASOS temperatures disagree for > 5% of rows.")
    print("   This suggests the station-to-grid coordinate matching is wrong.")
    print("   Check Task 4 extraction: verify lat/lon sign, longitude 0-360 conversion.")
else:
    print("✅ HRRR and ASOS temperatures agree for merged dataset.")
```

**Step 2: Derive features**

```python
# T-Td spread from HRRR forecast fields (Kelvin — spread in Kelvin = spread in Celsius)
train['hrrr_t_td_spread'] = train['hrrr_temp_k'] - train['hrrr_dewp_k']

# Wind speed from U and V components
train['hrrr_wind_ms'] = np.sqrt(train['hrrr_ugrd']**2 + train['hrrr_vgrd']**2)

# Persistence: current ASOS conditions at time of forecast issuance
# "What does it look and feel like right now, the night before?"
# These use ASOS observations — they're available at forecast time
train['persist_t_td_spread'] = train['tmpf'] - train['dwpf']   # current spread at ASOS (°F)
train['persist_vsby_km'] = train['vsby_km']                     # current visibility (km)

# Time features: fog is strongly tied to time of day and season
train['hour_utc'] = train['valid_hour'].dt.hour
train['month'] = train['valid_hour'].dt.month
train['hour_sin'] = np.sin(2 * np.pi * train['hour_utc'] / 24)
train['hour_cos'] = np.cos(2 * np.pi * train['hour_utc'] / 24)
train['month_sin'] = np.sin(2 * np.pi * train['month'] / 12)
train['month_cos'] = np.cos(2 * np.pi * train['month'] / 12)

# HRRR version flag (v3: Jul 2018 - Nov 2020, v4: Dec 2020 onward)
train['hrrr_v4'] = (train['valid_hour'] >= pd.Timestamp('2020-12-02', tz='UTC')).astype(int)

print("Derived features added.")
```

**Step 3: Define final feature columns**

```python
FEATURE_COLS = [
    # HRRR forecast atmospheric state (what HRRR predicted, not what happened)
    'hrrr_t_td_spread',    # How close is the forecasted air to saturation?
    'hrrr_wind_ms',        # Forecasted wind speed
    'hrrr_rh',             # Forecasted relative humidity
    'hrrr_hpbl',           # Forecasted boundary layer height: low = stable = fog-prone
    'hrrr_lcdc',           # Forecasted low cloud fraction
    'hrrr_soilw',          # Forecasted soil moisture
    'hrrr_dlwrf',          # Forecasted longwave radiation: nocturnal cooling driver
    'hrrr_vis',            # HRRR modeled visibility (as feature, not label)
    # Persistence: current conditions at forecast issuance time (what you know at 10pm)
    'persist_t_td_spread', # Current T-Td spread at ASOS station
    'persist_vsby_km',     # Current visibility at ASOS station
    # Lead time: how far ahead is this forecast? Lets model learn skill vs. horizon
    'lead_time_hours',
    # Time
    'hour_sin', 'hour_cos',    # Time of day (cyclical encoding)
    'month_sin', 'month_cos',  # Season (cyclical encoding)
    # Model flag
    'hrrr_v4',
]

TARGET_COL = 'is_fog'

print("Feature columns defined:")
for f in FEATURE_COLS:
    print(f"  {f}")

print(f"\nMissing values:")
print(train[FEATURE_COLS + [TARGET_COL]].isnull().sum())
```

**Step 4: Handle missing values and compute final class ratio**

```python
# Drop rows missing the label or key forecast features
train_clean = train.dropna(subset=[TARGET_COL] + ['hrrr_t_td_spread', 'hrrr_wind_ms', 'hrrr_hpbl'])

# Fill remaining NaN with column medians (conservative)
medians = train_clean[FEATURE_COLS].median()
train_clean = train_clean.copy()
train_clean[FEATURE_COLS] = train_clean[FEATURE_COLS].fillna(medians)
medians.to_csv(f'{BASE_DIR}/data/processed/feature_medians.csv')

print(f"Training rows after cleaning: {len(train_clean):,}")
print(f"Fog events: {train_clean[TARGET_COL].sum():,} ({train_clean[TARGET_COL].mean()*100:.2f}%)")

# Compute class ratio from the ACTUAL training sample (after HRRR sampling)
# This is the correct value for scale_pos_weight — not the original ASOS ratio
y_train_all = train_clean[TARGET_COL]
class_ratio_sampled = (y_train_all == 0).sum() / (y_train_all == 1).sum()
print(f"\nscale_pos_weight from actual training sample: {class_ratio_sampled:.1f}")
print("(Save this value — use it in Task 8.)")

train_clean[FEATURE_COLS + [TARGET_COL, 'station', 'valid_hour', 'lead_time_hours']].to_parquet(
    f'{BASE_DIR}/data/processed/train_features.parquet'
)
```

**Step 5: Repeat for test set**

```python
asos_test = pd.read_parquet(f'{BASE_DIR}/data/raw/asos/dc_metro_test_2024_2026.parquet')
hrrr_test = pd.read_parquet(f'{BASE_DIR}/data/raw/hrrr/hrrr_features_test.parquet')

asos_test['valid'] = pd.to_datetime(asos_test['valid'], utc=True)
hrrr_test['valid_time'] = pd.to_datetime(hrrr_test['valid_time'], utc=True)
asos_test['valid_hour'] = asos_test['valid'].dt.floor('H')

test = asos_test.merge(
    hrrr_test.rename(columns={'valid_time': 'valid_hour'}),
    on=['station', 'valid_hour'],
    how='inner'
)

# Apply same feature derivations
test['hrrr_t_td_spread'] = test['hrrr_temp_k'] - test['hrrr_dewp_k']
test['hrrr_wind_ms'] = np.sqrt(test['hrrr_ugrd']**2 + test['hrrr_vgrd']**2)
test['persist_t_td_spread'] = test['tmpf'] - test['dwpf']
test['persist_vsby_km'] = test['vsby_km']
test['hour_utc'] = test['valid_hour'].dt.hour
test['month'] = test['valid_hour'].dt.month
test['hour_sin'] = np.sin(2 * np.pi * test['hour_utc'] / 24)
test['hour_cos'] = np.cos(2 * np.pi * test['hour_utc'] / 24)
test['month_sin'] = np.sin(2 * np.pi * test['month'] / 12)
test['month_cos'] = np.cos(2 * np.pi * test['month'] / 12)
test['hrrr_v4'] = (test['valid_hour'] >= pd.Timestamp('2020-12-02', tz='UTC')).astype(int)

test_clean = test.dropna(subset=[TARGET_COL] + ['hrrr_t_td_spread', 'hrrr_wind_ms', 'hrrr_hpbl'])
test_clean = test_clean.copy()
test_clean[FEATURE_COLS] = test_clean[FEATURE_COLS].fillna(medians)

test_clean[FEATURE_COLS + [TARGET_COL, 'station', 'valid_hour', 'lead_time_hours']].to_parquet(
    f'{BASE_DIR}/data/processed/test_features.parquet'
)
print(f"Test rows: {len(test_clean):,}, fog events: {test_clean[TARGET_COL].sum():,}")
print(f"Lead times in test: {test_clean['lead_time_hours'].value_counts().to_dict()}")
```

**Step 6: Sanity check — fog rows should show different atmospheric state**

```python
# These relationships should hold if the data and features are correct
fog_rows = train_clean[train_clean['is_fog'] == 1]
nonfog_rows = train_clean[train_clean['is_fog'] == 0]

checks = [
    ('hrrr_t_td_spread', 'lower for fog'),
    ('hrrr_wind_ms', 'lower for fog'),
    ('hrrr_hpbl', 'lower for fog'),
    ('persist_vsby_km', 'lower for fog'),
]

print("Sanity check — fog vs. non-fog means:")
for col, expectation in checks:
    fog_mean = fog_rows[col].mean()
    nonfog_mean = nonfog_rows[col].mean()
    direction = "✅" if fog_mean < nonfog_mean else "❌ UNEXPECTED"
    print(f"  {col}: fog={fog_mean:.2f}, non-fog={nonfog_mean:.2f}  ({expectation}) {direction}")
```

Expected: All four checks show lower values for fog rows. If any show the opposite, investigate the data.

**Step 6b: Temporal integrity check**

```python
# Verify no future data leaked into training
train_max_date = train_clean['valid_hour'].max()
test_min_date = test_clean['valid_hour'].min()
assert train_max_date < test_min_date, \
    f"Temporal leakage! Training goes up to {train_max_date}, test starts at {test_min_date}"
print(f"✅ Temporal integrity confirmed: training ends {train_max_date}, test starts {test_min_date}")
```

**Step 6c: Distribution check — train vs. test**

```python
# Print feature distributions for both sets side by side
# Large differences (> 2x) indicate the model will be evaluated outside its training distribution
print("\nFeature distribution check (train vs. test):")
print(f"{'Feature':<25} {'Train mean':>12} {'Train std':>10} {'Test mean':>12} {'Test std':>10} {'Flag':>6}")
print("-" * 80)
for col in FEATURE_COLS:
    t_mean = train_clean[col].mean()
    t_std  = train_clean[col].std()
    v_mean = test_clean[col].mean()
    v_std  = test_clean[col].std()
    flag = "⚠️" if t_std > 0 and abs(v_mean - t_mean) / (t_std + 1e-9) > 2 else "✅"
    print(f"{col:<25} {t_mean:>12.3f} {t_std:>10.3f} {v_mean:>12.3f} {v_std:>10.3f} {flag:>6}")

print("\nFlag (⚠️) = test mean is > 2 standard deviations from training mean.")
print("These features need investigation before modeling — not necessarily blocking, but must be understood.")
```

**Step 7: Verify feature matrices before committing**

```python
train_check = pd.read_parquet(f'{BASE_DIR}/data/processed/train_features.parquet')
test_check = pd.read_parquet(f'{BASE_DIR}/data/processed/test_features.parquet')

# Both files must have data
assert len(train_check) > 1000, f"Training set too small: {len(train_check)} rows"
assert len(test_check) > 100,  f"Test set too small: {len(test_check)} rows"

# Fog label must be present and binary
assert set(train_check['is_fog'].unique()).issubset({0, 1}), "Fog label has unexpected values"
assert train_check['is_fog'].mean() < 0.3, "Fog rate > 30% — label or sampling problem"
assert train_check['is_fog'].mean() > 0.001, "Fog rate < 0.1% — something went wrong"

# All feature columns must exist and have no all-NaN columns
for col in FEATURE_COLS:
    assert col in train_check.columns, f"Missing feature column: {col}"
    null_rate = train_check[col].isnull().mean()
    assert null_rate < 0.1, f"Column {col} has {null_rate*100:.1f}% nulls — check extraction"

# Sanity check: fog rows should have lower T-Td spread
fog_spread = train_check[train_check['is_fog'] == 1]['hrrr_t_td_spread'].mean()
nonfog_spread = train_check[train_check['is_fog'] == 0]['hrrr_t_td_spread'].mean()
assert fog_spread < nonfog_spread, \
    f"Fog T-Td spread ({fog_spread:.2f}) >= non-fog ({nonfog_spread:.2f}) — data problem"

print(f"✅ Training rows: {len(train_check):,}, fog rate: {train_check['is_fog'].mean()*100:.2f}%")
print(f"✅ Test rows: {len(test_check):,}, fog rate: {test_check['is_fog'].mean()*100:.2f}%")
print(f"✅ All {len(FEATURE_COLS)} feature columns present with < 10% nulls")
print(f"✅ Sanity check: fog T-Td spread ({fog_spread:.2f}) < non-fog ({nonfog_spread:.2f})")
```

If any assertion fails, do not proceed to modeling. Fix the merge or feature derivation first.

**Step 8: Commit**

Save notebook. The feature matrices are ready for modeling.

---

## Task 6: Baseline Model (Simple Meteorological Rule)

**What this does:** Establish the bar we need to beat. The baseline is a simple rule: if T-Td spread ≤ 2°C AND wind speed < 2.5 m/s (~5 mph), predict fog. No machine learning — this is what a meteorologist would use as a first cut. We evaluate it on the 12-hour lead time subset of the test set, since that's our primary forecast horizon.

**Files:**
- Create: `notebooks/06_baseline_model.ipynb`

**Step 1: Lock the test set — run this once, reuse across all modeling tasks**

Rule 7: Define the test set here, once. Tasks 6, 7, 8, and 9 all reuse this exact dataframe.
Never re-filter or re-load test data inside a modeling task — doing so risks accidentally
changing which rows are included and making model comparisons unfair.

```python
import pandas as pd
import numpy as np

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'
RANDOM_SEED = 42

FEATURE_COLS = [
    'hrrr_t_td_spread', 'hrrr_wind_ms', 'hrrr_rh', 'hrrr_hpbl', 'hrrr_lcdc',
    'hrrr_soilw', 'hrrr_dlwrf', 'hrrr_vis',
    'persist_t_td_spread', 'persist_vsby_km',
    'lead_time_hours',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
    'hrrr_v4',
]
TARGET_COL = 'is_fog'

train = pd.read_parquet(f'{BASE_DIR}/data/processed/train_features.parquet')
test_all = pd.read_parquet(f'{BASE_DIR}/data/processed/test_features.parquet')

# Lock the test set: 12-hour lead time only, fixed here for all models
test = test_all[test_all['lead_time_hours'] == 12].copy().reset_index(drop=True)
test.to_parquet(f'{BASE_DIR}/data/processed/test_set_locked_12h.parquet')  # save locked version

X_test = test[FEATURE_COLS]
y_test = test[TARGET_COL]

print(f"Test set LOCKED: {len(test):,} rows, {y_test.sum():,} fog events ({y_test.mean()*100:.2f}%)")
print(f"Saved to test_set_locked_12h.parquet — all models use this exact file.")
```

**Step 2: Apply baseline rule**

```python
from sklearn.metrics import (
    average_precision_score, brier_score_loss,
    precision_score, recall_score, f1_score
)

import datetime

def evaluate_model(y_true, y_prob, model_name, feature_cols=None):
    """Compute, print, and log all evaluation metrics. Rule 10: appends to experiment log."""
    y_pred = (y_prob >= 0.5).astype(int)

    auc_pr = average_precision_score(y_true, y_prob)
    brier = brier_score_loss(y_true, y_prob)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    print(f"\n{'='*40}")
    print(f"Model: {model_name}")
    print(f"{'='*40}")
    print(f"AUC-PR:    {auc_pr:.4f}  (higher = better; random = {y_true.mean():.4f})")
    print(f"Brier:     {brier:.4f}  (lower = better; perfect = 0)")
    print(f"Precision: {precision:.4f}  (when we predict fog, how often is it right?)")
    print(f"Recall:    {recall:.4f}  (of all fog events, how many did we catch?)")
    print(f"F1:        {f1:.4f}")

    result = {'model': model_name, 'auc_pr': auc_pr, 'brier': brier,
              'precision': precision, 'recall': recall, 'f1': f1}

    # Rule 10: append to experiment log so every run is permanently recorded
    log_row = {
        'timestamp': datetime.datetime.now().isoformat(),
        'model': model_name,
        'n_features': len(feature_cols) if feature_cols else 'unknown',
        'test_rows': len(y_true),
        'fog_events': int(y_true.sum()),
        **result
    }
    log_path = f'{BASE_DIR}/outputs/experiment_log.csv'
    log_df = pd.DataFrame([log_row])
    if os.path.exists(log_path):
        log_df.to_csv(log_path, mode='a', header=False, index=False)
    else:
        log_df.to_csv(log_path, index=False)

    return result

results = []

# Baseline: HRRR forecast T-Td spread ≤ 2°C AND forecast wind < 2.5 m/s
baseline_prob = (
    (test['hrrr_t_td_spread'] <= 2.0) &
    (test['hrrr_wind_ms'] < 2.5)
).astype(float)

results.append(evaluate_model(y_test, baseline_prob, "Baseline Rule (12h lead time)"))
```

Record the baseline AUC-PR and Brier score. These are the numbers we need to beat.

**Step 3: Commit**

Save notebook with baseline metrics printed clearly.

---

## Task 7: Logistic Regression Model

**What this does:** Train a logistic regression — the simplest proper ML model. Fast, interpretable, and a good sanity check before XGBoost. Trained on all lead times combined (lead_time_hours is a feature), evaluated at 12h.

**Files:**
- Create: `notebooks/07_logistic_regression.ipynb`

**Step 1: Train**

```python
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'

FEATURE_COLS = [
    'hrrr_t_td_spread', 'hrrr_wind_ms', 'hrrr_rh', 'hrrr_hpbl', 'hrrr_lcdc',
    'hrrr_soilw', 'hrrr_dlwrf', 'hrrr_vis',
    'persist_t_td_spread', 'persist_vsby_km',
    'lead_time_hours',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
    'hrrr_v4',
]
TARGET_COL = 'is_fog'

train = pd.read_parquet(f'{BASE_DIR}/data/processed/train_features.parquet')
# Rule 7: always load the locked test set — never re-filter from test_all
test = pd.read_parquet(f'{BASE_DIR}/data/processed/test_set_locked_12h.parquet')

X_train = train[FEATURE_COLS]
y_train = train[TARGET_COL]
X_test = test[FEATURE_COLS]
y_test = test[TARGET_COL]

assert len(X_test) > 0, "Locked test set is empty — check Task 6 ran successfully"
print(f"Test set rows: {len(X_test):,} (must match Task 6 and Task 8 exactly)")

# Logistic regression needs scaled features
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

lr = LogisticRegression(class_weight='balanced', max_iter=1000, random_state=42)
lr.fit(X_train_scaled, y_train)
print("Logistic regression trained.")
```

**Step 2: Evaluate**

```python
lr_prob = lr.predict_proba(X_test_scaled)[:, 1]
results.append(evaluate_model(y_test, lr_prob, "Logistic Regression"))
```

**Step 3: Check feature importance (coefficients)**

```python
import matplotlib.pyplot as plt

coef_df = pd.DataFrame({
    'feature': FEATURE_COLS,
    'coefficient': lr.coef_[0]
}).sort_values('coefficient', ascending=False)

plt.figure(figsize=(8, 6))
plt.barh(coef_df['feature'], coef_df['coefficient'])
plt.title('Logistic Regression Coefficients\n(positive = fog predictor, negative = anti-fog)')
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/lr_coefficients.png', dpi=150)
plt.show()
```

Expected: `hrrr_t_td_spread` should have a strong negative coefficient (low spread = more fog). `hrrr_hpbl` should be negative. `hrrr_wind_ms` should be negative. `persist_vsby_km` should be negative (currently low visibility → fog more likely soon). `lead_time_hours` should be negative (longer forecast horizon → lower confidence). If these are reversed, investigate the data.

**Step 4: Commit**

---

## Task 8: XGBoost Model

**What this does:** Train XGBoost — the stronger ML model that can capture non-linear relationships. Trained on all lead times (lead_time_hours is a feature), evaluated at 12h.

**Files:**
- Create: `notebooks/08_xgboost.ipynb`

**Step 1: Load data and class ratio**

```python
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import train_test_split

BASE_DIR = '/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/vibe coding/fogchaser'

FEATURE_COLS = [
    'hrrr_t_td_spread', 'hrrr_wind_ms', 'hrrr_rh', 'hrrr_hpbl', 'hrrr_lcdc',
    'hrrr_soilw', 'hrrr_dlwrf', 'hrrr_vis',
    'persist_t_td_spread', 'persist_vsby_km',
    'lead_time_hours',
    'hour_sin', 'hour_cos', 'month_sin', 'month_cos',
    'hrrr_v4',
]
TARGET_COL = 'is_fog'

train = pd.read_parquet(f'{BASE_DIR}/data/processed/train_features.parquet')
# Rule 7: always load the locked test set
test = pd.read_parquet(f'{BASE_DIR}/data/processed/test_set_locked_12h.parquet')

X_train = train[FEATURE_COLS]
y_train = train[TARGET_COL]
X_test = test[FEATURE_COLS]
y_test = test[TARGET_COL]

assert len(X_test) > 0, "Locked test set is empty — check Task 6 ran successfully"
print(f"Test set rows: {len(X_test):,} (must match Tasks 6 and 7 exactly)")

# Use class ratio from the actual training sample (computed in Task 5)
# This accounts for the HRRR sampling — not the original ASOS ratio
class_ratio = (y_train == 0).sum() / (y_train == 1).sum()
print(f"scale_pos_weight: {class_ratio:.1f}")
```

**Step 2: Train XGBoost**

```python
X_tr, X_val, y_tr, y_val = train_test_split(
    X_train, y_train, test_size=0.1, random_state=RANDOM_SEED, stratify=y_train
)

xgb_model = xgb.XGBClassifier(
    n_estimators=500,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=class_ratio,
    eval_metric='aucpr',
    early_stopping_rounds=20,
    random_state=RANDOM_SEED,  # Rule 9: always use RANDOM_SEED variable
    tree_method='hist',
)

xgb_model.fit(
    X_tr, y_tr,
    eval_set=[(X_val, y_val)],
    verbose=50
)
print("XGBoost trained.")
```

**Step 3: Evaluate**

```python
xgb_prob = xgb_model.predict_proba(X_test)[:, 1]
results.append(evaluate_model(y_test, xgb_prob, "XGBoost"))
```

**Step 4: Feature importance**

```python
import matplotlib.pyplot as plt

importances = pd.DataFrame({
    'feature': FEATURE_COLS,
    'importance': xgb_model.feature_importances_
}).sort_values('importance', ascending=False)

plt.figure(figsize=(8, 6))
plt.barh(importances['feature'], importances['importance'])
plt.title('XGBoost Feature Importance')
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/xgb_feature_importance.png', dpi=150)
plt.show()
print(importances.to_string(index=False))
```

Expected: `hrrr_t_td_spread`, `hrrr_hpbl`, `hrrr_wind_ms`, and `persist_vsby_km` should dominate. `lead_time_hours` should appear — a meaningful coefficient here means the model correctly learns that longer lead times reduce confidence. If time features (hour_sin/cos) dominate over atmospheric variables, the model is overfitting to time patterns rather than learning physics — flag this.

**Step 5: Save model**

```python
xgb_model.save_model(f'{BASE_DIR}/models/xgb_fog_v1.json')
print("Model saved.")
```

**Step 6: Commit**

---

## Task 9: Calibration and Final Validation

**What this does:** Three things. (1) Compare all models side by side at 12h lead time. (2) Draw a calibration curve — the core check that probability outputs are trustworthy. (3) Check performance by lead time, to verify the model correctly shows lower confidence at longer horizons (which should feed the +1h to +12h drill-down view).

**Files:**
- Create: `notebooks/09_calibration_validation.ipynb`

**Step 1: Print model comparison table (12h lead time)**

```python
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import average_precision_score, brier_score_loss
from sklearn.calibration import calibration_curve

results_df = pd.DataFrame(results)
print("\nModel Comparison — DC Metro Test Set, 12h Lead Time")
print("="*60)
print(results_df.to_string(index=False))
```

Expected: XGBoost outperforms logistic regression, which outperforms baseline. If baseline beats both ML models, something is wrong.

**Step 2: Plot calibration curve**

This is the most important chart in the whole plan. It shows whether the model's probability outputs are trustworthy — "when it says 70%, does fog occur ~70% of the time?"

```python
y_prob = xgb_prob

fraction_of_positives, mean_predicted_value = calibration_curve(
    y_test, y_prob, n_bins=10, strategy='quantile'
)

plt.figure(figsize=(8, 6))
plt.plot(mean_predicted_value, fraction_of_positives,
         marker='o', linewidth=2, label='XGBoost (12h)')
plt.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')
plt.xlabel('Mean predicted probability')
plt.ylabel('Fraction of positives (actual fog rate)')
plt.title('Calibration Curve — DC Metro Test Set\n'
          '"When we predict X% fog probability, fog occurs Y% of the time"')
plt.legend()
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/calibration_curve.png', dpi=150)
plt.show()
```

A well-calibrated model: points fall close to the diagonal. If they bow above, model is underconfident. If below, overconfident.

**Step 3: If calibration is poor, apply Platt scaling**

Only apply if the calibration curve shows significant deviation from the diagonal. Note: Platt scaling needs a separate calibration set — use a different portion of the validation split, not the same X_val used for early stopping.

```python
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import train_test_split

# Split X_val into calibration and reserve (never mix early-stopping data with calibration fitting)
X_tr2, X_cal, y_tr2, y_cal = train_test_split(X_tr, y_tr, test_size=0.15, random_state=99, stratify=y_tr)

calibrated_xgb = CalibratedClassifierCV(xgb_model, method='sigmoid', cv='prefit')
calibrated_xgb.fit(X_cal, y_cal)

calibrated_prob = calibrated_xgb.predict_proba(X_test)[:, 1]
results.append(evaluate_model(y_test, calibrated_prob, "XGBoost (Calibrated)"))

fraction_cal, mean_cal = calibration_curve(y_test, calibrated_prob, n_bins=10, strategy='quantile')
plt.figure(figsize=(8, 6))
plt.plot(mean_predicted_value, fraction_of_positives, marker='o', label='XGBoost (uncalibrated)')
plt.plot(mean_cal, fraction_cal, marker='s', label='XGBoost (calibrated)')
plt.plot([0, 1], [0, 1], 'k--', label='Perfect')
plt.legend()
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/calibration_curve_comparison.png', dpi=150)
plt.show()
```

**Step 3b: Physical sense check (Rule 8)**

The calibration curve tells you the model is well-calibrated. This check tells you it learned the right *reasons*. Print the 20 highest-confidence fog predictions and inspect them with your eyes.

```python
test_check = test.copy()
test_check['xgb_prob'] = xgb_prob
top20 = test_check.nlargest(20, 'xgb_prob')[
    ['station', 'valid_hour', 'xgb_prob', 'hrrr_t_td_spread',
     'hrrr_wind_ms', 'hrrr_hpbl', 'persist_vsby_km', 'is_fog']
].copy()
top20['hour'] = pd.to_datetime(top20['valid_hour']).dt.hour
top20['month'] = pd.to_datetime(top20['valid_hour']).dt.month

print("Top 20 highest-confidence fog predictions:")
print(top20.to_string(index=False))

# Check that the model's most confident predictions are physically sensible
pct_predawn = (top20['hour'].between(0, 7)).mean()
pct_cool_months = (top20['month'].isin([10, 11, 12, 1, 2, 3])).mean()
pct_low_spread = (top20['hrrr_t_td_spread'] < 3).mean()
pct_actually_fog = top20['is_fog'].mean()

print(f"\nPhysical sense check on top-20 predictions:")
print(f"  Pre-dawn (midnight–7am):  {pct_predawn*100:.0f}%  (expect > 60%)")
print(f"  Cool months (Oct–Mar):    {pct_cool_months*100:.0f}%  (expect > 60%)")
print(f"  Low T-Td spread (< 3°C):  {pct_low_spread*100:.0f}%  (expect > 70%)")
print(f"  Actually fog (is_fog=1):  {pct_actually_fog*100:.0f}%  (hope for > 70%)")

if pct_predawn < 0.4 or pct_cool_months < 0.4 or pct_low_spread < 0.5:
    print("\n⚠️  Model's top predictions look physically suspicious.")
    print("   Check feature importance — model may have learned time patterns over atmospheric physics.")
else:
    print("\n✅ Top predictions look physically sensible.")
```

**Step 4: Performance by lead time**

This tells you whether the model correctly loses confidence as the forecast horizon gets longer — which is the right behavior, and essential for the +1h to +12h drill-down.

```python
test_all = pd.read_parquet(f'{BASE_DIR}/data/processed/test_features.parquet')

lead_time_results = []
for fxx in sorted(test_all['lead_time_hours'].unique()):
    subset = test_all[test_all['lead_time_hours'] == fxx].copy()
    if len(subset) < 100:
        continue
    X_sub = subset[FEATURE_COLS]
    y_sub = subset[TARGET_COL]
    prob = xgb_model.predict_proba(X_sub)[:, 1]
    auc = average_precision_score(y_sub, prob)
    brier = brier_score_loss(y_sub, prob)
    lead_time_results.append({
        'lead_time_hours': fxx,
        'auc_pr': auc,
        'brier': brier,
        'n': len(subset),
        'fog_events': y_sub.sum()
    })

lt_df = pd.DataFrame(lead_time_results)
print("\nPerformance by Lead Time:")
print(lt_df.to_string(index=False))

# Plot AUC-PR vs lead time
plt.figure(figsize=(8, 4))
plt.plot(lt_df['lead_time_hours'], lt_df['auc_pr'], marker='o')
plt.xlabel('Lead time (hours)')
plt.ylabel('AUC-PR')
plt.title('Model skill vs. forecast horizon\n(should decrease with longer lead time)')
plt.tight_layout()
plt.savefig(f'{BASE_DIR}/outputs/skill_vs_lead_time.png', dpi=150)
plt.show()
```

Expected: AUC-PR should decrease as lead time increases — the model is less confident the further out it predicts. This is the correct behavior. If AUC-PR is the same or higher at 18h than 6h, something is wrong with the feature setup.

**Step 5: Performance by station**

```python
DC_STATIONS = ['KDCA', 'KIAD', 'KBWI', 'KGAI', 'KFDK', 'KHEF', 'KNYG', 'KCGS']

test_12h = test_all[test_all['lead_time_hours'] == 12].copy()
test_12h['xgb_prob'] = xgb_model.predict_proba(test_12h[FEATURE_COLS])[:, 1]

station_results = []
for station in DC_STATIONS:
    station_df = test_12h[test_12h['station'] == station]
    if len(station_df) < 50:
        continue
    auc = average_precision_score(station_df['is_fog'], station_df['xgb_prob'])
    brier = brier_score_loss(station_df['is_fog'], station_df['xgb_prob'])
    station_results.append({
        'station': station, 'auc_pr': auc, 'brier': brier,
        'n': len(station_df), 'fog_events': station_df['is_fog'].sum()
    })

print(pd.DataFrame(station_results).sort_values('auc_pr', ascending=False).to_string(index=False))
```

**Step 6: Save all outputs**

```python
results_df = pd.DataFrame(results)
results_df.to_csv(f'{BASE_DIR}/outputs/model_comparison.csv', index=False)
lt_df.to_csv(f'{BASE_DIR}/outputs/skill_by_lead_time.csv', index=False)
pd.DataFrame(station_results).to_csv(f'{BASE_DIR}/outputs/per_station_results.csv', index=False)
print("All outputs saved.")
```

**Step 7: Commit**

---

## Task 10: Gate Decision

**What this does:** Make the explicit go/no-go decision. Compare XGBoost against the baseline rule. Check geographic transfer (DC was held out — does the model actually work there?). Write up findings. Decide whether to proceed to Phase 2.

**Files:**
- Create: `notebooks/10_gate_decision.ipynb`
- Output: `docs/phase1-findings.md` (written manually based on results)

**Step 1: Apply the gate criteria**

The gate requires ALL THREE of the following:

```python
import pandas as pd

results_df = pd.read_csv(f'{BASE_DIR}/outputs/model_comparison.csv')
y_test_mean = test[TARGET_COL].mean()

baseline_auc = results_df[results_df['model'] == 'Baseline Rule (12h lead time)']['auc_pr'].values[0]
best_auc = results_df[results_df['model'].str.contains('XGBoost')]['auc_pr'].max()
auc_improvement = best_auc - baseline_auc

# Load NBM benchmark from Phase 0
nbm_results = pd.read_csv(f'{BASE_DIR}/outputs/nbm_benchmark_results.csv')
nbm_auc = nbm_results[nbm_results['model'] == 'NBM + Elevation Weight']['auc_pr'].values[0]

print("GATE DECISION — 12h Lead Time on DC Metro (held-out geography)")
print("="*60)
print(f"\nFull comparison:")
print(f"  Baseline rule:        {baseline_auc:.4f}")
print(f"  NBM + terrain (Phase 0): {nbm_auc:.4f}")
print(f"  XGBoost (Phase 1B):   {best_auc:.4f}")

print(f"\nGate 1 — AUC-PR improvement > 0.05 over baseline:")
print(f"  Baseline AUC-PR: {baseline_auc:.4f}")
print(f"  Best model AUC-PR: {best_auc:.4f}")
print(f"  Improvement: {auc_improvement:.4f}")
print(f"  {'✅ PASS' if auc_improvement > 0.05 else '❌ FAIL'}")

print(f"\nGate 1b — Does custom ML beat NBM? (the honest bar)")
print(f"  NBM AUC-PR: {nbm_auc:.4f}")
print(f"  ML AUC-PR:  {best_auc:.4f}")
print(f"  {'✅ ML beats NBM — custom model adds value' if best_auc > nbm_auc else '⚠️  ML does NOT beat NBM — NBM is the better MVP forecast engine'}")

print(f"\nGate 2 — AUC-PR at least 3x random classifier:")
print(f"  Random AUC-PR (= fog base rate): {y_test_mean:.4f}")
print(f"  Best model AUC-PR: {best_auc:.4f}")
print(f"  Ratio: {best_auc / y_test_mean:.1f}x")
print(f"  {'✅ PASS' if best_auc >= 3 * y_test_mean else '❌ FAIL'}")

print(f"\nGate 3 — Calibration reasonable:")
print(f"  Review calibration_curve.png in outputs/")
print(f"  Is the curve close to the diagonal? [Manual check required]")

print(f"\nGate 4 — Geographic transfer confirmed:")
print(f"  The model was trained WITHOUT any DC metro stations.")
print(f"  Passing Gates 1-3 on DC data means it genuinely generalized to a new geography.")
print(f"  This also means the same approach should transfer to other cities later.")
```

**Step 2: Check skill-vs-horizon is sensible**

```python
lt_df = pd.read_csv(f'{BASE_DIR}/outputs/skill_by_lead_time.csv')
print("\nSkill vs. lead time (should decrease as lead time increases):")
print(lt_df[['lead_time_hours', 'auc_pr']].to_string(index=False))

# Check that 6h is better than 12h (expected)
auc_6h = lt_df[lt_df['lead_time_hours'] == 6]['auc_pr'].values[0]
auc_12h = lt_df[lt_df['lead_time_hours'] == 12]['auc_pr'].values[0]
print(f"\n6h AUC-PR: {auc_6h:.4f} vs 12h AUC-PR: {auc_12h:.4f}")
print(f"{'✅ Expected: 6h better than 12h' if auc_6h > auc_12h else '⚠️  Unexpected: 12h >= 6h — investigate'}")
```

**Step 3: Write the findings document**

After running the analysis, manually write `docs/phase1-findings.md` covering:
- Confirmed fog frequency at DC metro stations (actual numbers)
- Model comparison table (paste it in)
- Whether all four gate criteria were met
- Key observations from feature importance
- Skill-by-lead-time: does the model behave sensibly across the +1h to +12h range?
- Decision: proceed to Phase 2 (app) or investigate further
- If not proceeding: what specific questions to investigate next

**Step 4: If the gate fails**

Do not proceed to building the app. Investigate:
- Are fog labels correct? Spot-check rows where fog was labeled but model predicted no fog.
- Are HRRR forecast values physically sensible? Print min/max for `hrrr_temp_k` (expect ~260–310 K), `hrrr_hpbl` (expect ~50–2000 m), `hrrr_t_td_spread` (expect 0–30 K).
- Is geographic transfer the failure point? Check if AUC-PR is materially worse for DC than the national validation would predict.
- Is the temporal split clean? Verify no 2024+ data leaked into training.

**Step 5: If the gate passes**

You have a working fog model that generalizes geographically. Proceed to Phase 2:
- Retrain final model on all available data (2018–2025, including DC test period)
- Package the model as a Python function that takes HRRR forecast fields and returns fog probability
- Design the DC metro spatial inference grid (where to generate predictions)
- Begin app planning

---

## Summary: What Success Looks Like

By the end of Phase 1, you should have:

1. **Confirmed fog frequency** for DC metro stations (actual numbers, not estimates)
2. **A labeled dataset** trained on geographically diverse national data, with DC strictly held out
3. **Three model benchmarks**: baseline rule, logistic regression, XGBoost — all evaluated on DC test data the model never saw during training
4. **A calibration curve** showing the model is trustworthy when it predicts high fog probability
5. **A skill-by-lead-time chart** showing the model correctly loses confidence at longer horizons — validating it can power the +1h to +12h hourly drill-down
6. **A clear go/no-go decision** with written rationale

If XGBoost achieves AUC-PR > 3× random and > 0.05 over the simple baseline on held-out DC data, and the calibration curve looks reasonable, and skill decreases sensibly with lead time — you have strong evidence the approach will generalize when you expand to other cities.

---

## Known Limitations (Deferred to Future Refinement)

These are real methodological issues that are not worth fixing for MVP but should be revisited before claiming the model is production-ready or before academic publication.

**1. Spatial autocorrelation inflates all metrics.** Stations within the same region respond to the same weather systems simultaneously. During a fog event, multiple stations all go foggy at once, which inflates your row count while contributing fewer truly independent signals. Your reported AUC-PR is optimistic. Quantify this by comparing station-clustered cross-validation against the current approach before claiming a specific accuracy number.

**2. No confidence intervals on metrics.** With a finite test set and rare fog events, AUC-PR estimates have sampling uncertainty. Bootstrap confidence intervals (resample the test set 1,000 times, compute AUC-PR each time) would tell you how stable the reported number is. With ~2,000–4,000 fog events in the test set, uncertainty could be ±0.02–0.05 AUC-PR.

**3. Fog threshold not validated against photographer needs.** The 1 km definition is meteorological convention. A photographer might care more about visibility < 500m (dramatic fog) or might find 2–3 km mist equally photogenic. Running the same analysis at 0.5 km and 2 km thresholds would tell you if the choice matters, and which threshold better matches what makes a shoot worthwhile.

**4. Geographic transfer is assumed, not stress-tested.** Passing the DC holdout test is evidence of generalization, but not proof. Before expanding to a new city, run the same geographic holdout for that city and verify the model works there too. Don't assume one successful transfer means unlimited transfer.

**5. HRRR variable naming and coordinate system not fully verified.** The Herbie extraction code uses `method='nearest'` for lat/lon selection on HRRR's native Lambert Conformal Conic projection. This is an approximation — geographic errors of a few kilometers are possible near the edges of the domain. Verify extracted values against known station observations before using for production. Also: HRRR `searchString` values in Herbie are version-sensitive and should be tested against the actual GRIB2 catalogue for the target date range.

**6. Hyperparameters not cross-validated.** XGBoost parameters (n_estimators, max_depth, learning_rate) are reasonable starting values but not tuned. Grid search or Bayesian optimization on a proper cross-validation fold structure could improve performance meaningfully. Low priority for MVP; revisit before claiming optimal model.

**7. Class imbalance: sampling strategy could be improved.** The 1-in-6 non-fog sampling for HRRR extraction is uniform random. It could instead be stratified by season and time-of-day to ensure all fog-relevant conditions are adequately represented. Low impact for MVP.

---

## Data Flow Reference

```
IEM ASOS API ─────────────────────────────────────┐
  (visibility < 1km = fog label)                   │
  (T, Td, wind = persistence features)             │
  (DC metro stations EXCLUDED from training)        │
                                                    ▼
HRRR via Herbie ──────────────────────────► Feature Matrix ──► Models ──► Metrics
  (FORECAST fields: fxx=6, 9, 12, 18)       (merged on           Baseline
  (NOT analysis fields)                      station + hour       LogReg
  (TMP, DPT, RH, HPBL, LCDC,                + lead_time)         XGBoost
   SOILW, DLWRF, VIS, UGRD, VGRD)                                     │
                                                                       ▼
                                                           Calibration Curve
                                                           Skill vs. Lead Time
                                                           Gate Decision
                                                           (DC holdout = geographic transfer test)
```
