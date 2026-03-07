# Phase 1B Results + Session Handoff

**Date completed:** 2026-03-02
**Status:** Phase 1B COMPLETE — awaiting Ivy's decision on next steps

---

## What We Did This Session

1. Fixed HRRR extraction bugs (longitude convention, multi-variable merge)
2. Ran full HRRR pilot extraction (took ~5 hours total)
3. Trained ASOS+HRRR model on 4-month pilot data
4. Discovered original NBM comparison was invalid (biased test set)
5. Built fair apples-to-apples comparison on unified test set

---

## Final Results (Definitive)

**Test set:** 4,289 rows | 5.39% fog rate | same fresh-fog filter for ALL models
**Saved to:** `outputs/fair_comparison_results.csv`

| Model | AUC-PR | vs Random |
|---|---|---|
| Baseline rule | 0.071 | 1.3x |
| NBM binary (vis<1000m) | 0.170 | 3.2x |
| Enhanced ASOS — 6yr training | 0.174 | 3.2x |
| NBM soft (inverse visibility) | 0.296 | 5.5x |
| **ASOS+HRRR pilot — 4-month train** | **0.358** | **6.7x** |

**Random baseline** (= fog rate) = 0.054

### What This Means in Plain English
- ASOS-only model (our best surface-only model) is roughly tied with NBM's binary forecast
- ASOS+HRRR clearly beats NBM at its best (0.358 vs 0.296, +21%)
- The HRRR atmospheric features add real signal over surface observations alone
- HRRR model was trained on only 4 months of data — more training data should improve it further

---

## What's Already Built (don't rebuild these)

### Data — COMPLETE, don't re-extract
- `data/raw/hrrr/hrrr_train_nov2022_feb2023.parquet` — 2.2M rows, 769 stations
- `data/raw/hrrr/hrrr_test_dc_2024.parquet` — 35K rows, 8 DC stations
- `data/raw/hrrr/station_grid_indices.json` — HRRR grid indices (expensive to recompute)
- `data/raw/asos/dc_metro_test_2024_2026.parquet` — ground truth test set

### Models
- `models/xgb_enhanced_asos_v1.json` — best ASOS-only model (6yr training)
- `models/enhanced_asos_station_list.json` — station encoding list (MUST reuse in any future model)
- `models/xgb_asos_hrrr_pilot_v1.json` — ASOS+HRRR pilot model (4-month)

---

## Decisions Pending — Ivy to Review

The pilot proved HRRR adds value. Three natural next steps:

### Option A: Build the app now (fastest path to product)
Use the current ASOS+HRRR model as the backend. It's good enough (6.7x random).
Build a simple map UI for DC metro that shows fog probability for tomorrow morning.
Limitation: 4-month training data — model may be shaky in edge cases.

### Option B: Expand HRRR training first (more rigorous)
Re-run HRRR extraction for full 5-year national training period (2018–2023).
This matches the ASOS training window and should significantly improve the model.
Cost: ~1–2 weeks of extraction time (can run in background overnight).
Then retrain and compare.

### Option C: Improve model, then build app
Small targeted improvements first (calibration, lead time as a feature) before app work.
Could raise AUC-PR further without needing more training data.

---

## Technical Gotchas for Next Session

1. **Station encoding:** Any new model MUST load `enhanced_asos_station_list.json` and use
   the same CategoricalDtype. If you create a new station list, station_code integers will
   mismatch and the model will silently use wrong stations.

2. **HRRR longitude:** Always convert station lons: `slon360 = slon + 360 if slon < 0`

3. **Cloud base NaN:** `hgt_cldbase_m` has ~38% NaN = no cloud. Fill with 10,000m BEFORE
   null rate checks and before training. This is NOT a data quality problem.

4. **Timezone:** HRRR parquets may already be UTC-localized. Always check:
   `if _vt.dt.tz is None: _vt = _vt.dt.tz_localize('UTC')`

5. **Fair comparison:** When comparing models, always build a unified intersection test set
   (inner join on station+valid_hour for all sources). NBM has sparse coverage — don't
   evaluate models on different row sets.

6. **Fresh fog filter:** `vsby_km_lag >= 1.0` (12h lag). Apply to ALL models in any comparison.
   Without it, the model learns to predict fog persistence, not fog onset.
