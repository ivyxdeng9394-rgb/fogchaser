# Spatial Interpolation Layer — Design Document

**Date:** 2026-03-02
**Status:** Approved — ready for implementation planning
**Authors:** Ivy + Claude (brainstorming session with parallel subagent review)
**Follows from:** `docs/plans/2026-03-02-spatial-layer-handoff.md`

---

## What This Is

The existing model (XGBoost + Platt calibrator) predicts fog probability at 8 ASOS airport stations in the DC metro area. This spatial layer extends those 8 point predictions to a continuous 500m grid map — enabling the fog discovery use case described in the PRD (showing which corridors and terrain pockets are fog-prone, not just whether a specific airport is foggy).

**This is a display/product layer, not a model accuracy improvement.** The XGBoost model is unchanged. What changes is how predictions are served across space.

---

## Design Principles (Decisions Made)

- **Start simple.** IDW interpolation + hand-weighted terrain multiplier. No kriging, no ML terrain fitting.
- **500m output resolution.** Fine enough to show valley-vs-ridge contrast; coarse enough to compute quickly.
- **Log-odds consistency.** All operations (IDW blend, terrain offset, clamp) happen in log-odds space for mathematical coherence.
- **Terrain weights are priors, not fitted parameters.** We don't have ground truth at sub-station spatial resolution. The weights are physically motivated and validated visually; they are not derived from data.

---

## Section 1: Architecture

### Two-Phase Pipeline

**Phase 1 — One-time terrain setup** (run once; re-run only if terrain parameters change):

1. Download 3DEP 1m DEM + NLCD 30m land cover for DC metro bounding box
2. Reproject all inputs to **EPSG:5070** (Albers Equal Area, NAD83) — all distance and area computations use this CRS
3. Compute 4 terrain features at 500m resolution (see Section 3)
4. Compute terrain offset grid (see Section 4)
5. Save outputs:
   - `data/processed/terrain_offset_grid.tif` — GeoTIFF, float32, one band, EPSG:5070, nodata=-9999
   - `data/processed/terrain_grid_metadata.csv` — records all parameters used (weights, normalization bounds, DEM source, NLCD year, date generated)

**Phase 2 — Per-forecast-hour runtime** (runs once per HRRR initialization hour: 00, 06, 12, 18 UTC):

- **Step 2a:** Retrieve 8 ASOS station fog probability predictions from XGBoost+Platt calibrator → IDW blend in log-odds space → raw `IDW_logit` raster
- **Step 2b:** Load `terrain_offset_grid.tif` (immutable; loaded once at startup)
- **Step 2c:** `final_logit = IDW_logit + terrain_offset` → sigmoid → output probability raster

Output artifact: `outputs/spatial/fog_prob_{YYYYMMDD}_{HH}UTC.tif`
- Format: GeoTIFF, float32, values in [0, 1], nodata=-9999
- Filename encodes HRRR initialization hour (not valid time)

### Why Three Named Steps

Steps 2a, 2b, and 2c are independently inspectable. The IDW raster (before terrain) and the terrain offset grid (before combination) can both be examined in isolation. This is how you debug whether a bad output is caused by a bad IDW base or a bad terrain offset.

### Known Limitations

- **Post-terrain output is not a calibrated probability.** The XGBoost+Platt model is calibrated at station level. Adding a hand-weighted terrain offset in log-odds space breaks that calibration guarantee. The output raster should be interpreted as a relative fog likelihood score — useful for "where is fog more likely?" — not as a literal "X% chance of fog at this pixel."
- **Terrain offset is static.** It does not change by hour, season, or synoptic condition. It will over-correct on advection fog events (where valley position is less relevant) and may under-correct on strong radiation fog nights. This is a known simplification for MVP.
- **8 ASOS stations are all airports.** Airports are sited on flat, open terrain. They systematically undersample the exact terrain types (valleys, riverbanks) where fog is most likely to form. The terrain multiplier corrects for this after the fact but is working against the sampling bias.

---

## Section 2: Geographic Scope

### Bounding Box

**38.1°N to 39.7°N, 76.0°W to 78.1°W** — approximately 175km × 175km

| Edge | Coordinate | Terrain anchor |
|---|---|---|
| West | ~78.1°W | Blue Ridge / Appalachian front — source of katabatic cold-air drainage into DC valleys |
| East | ~76.0°W | Chesapeake Bay western shore — primary advection fog influence zone |
| North | ~39.7°N | Southern Pennsylvania / Baltimore metro |
| South | ~38.1°N | Potomac estuary influence zone |

**Grid:** ~350 × 350 cells at 500m = ~122,500 cells total. All cells computed; entire grid is available for the app map.

### Why This Box (not "50-mile radius")

The original "50-mile radius" framing was a conceptual shorthand. The implementation is always a rectangle, so the box is the real definition. More importantly, a symmetric radius from Capitol centered the box on the wrong geography: the fog-relevant terrain (Shenandoah foothills to the west, Chesapeake Bay to the east) is not symmetrically distributed. Pushing the western edge to 78.1°W captures KHGR (Hagerstown, in the Cumberland Valley) and KMRB (Martinsburg), both in fog-prone valley positions, as potential IDW contributors if station coverage expands.

### Resolution Disclaimer

**500m is the terrain feature resolution, not the forecast resolution.** The XGBoost model predicts at 8 point stations; HRRR/NBM atmospheric data is 2.5–3km. The 500m grid resolves terrain features (which are real at that scale) but does not represent independent atmospheric forecasts at 500m. The map should not be interpreted as "500m forecast skill."

### Known Limitation

**Chesapeake Bay marine fog** is partially within the eastern portion of the grid. Marine advection fog from the Bay is a distinct meteorological regime the XGBoost model was not trained on (training stations are inland airports). Probability values in the eastern third of the grid near the Bay shoreline should be treated with extra caution.

---

## Section 3: Terrain Features

Four signals, computed once from 3DEP DEM + NLCD and stored in the terrain offset grid.

All features except cosine aspect are normalized using **2nd–98th percentile clipping** before scaling to [-1, +1]. This prevents outlier cells (a deep gorge, a large reservoir) from compressing the meaningful variation across the rest of the grid.

### Feature 1: TPI_multi — Terrain Position Index (Multi-Scale)

**What it captures:** Whether a cell sits in a topographic low (valley, basin) or high (ridge, hilltop) relative to surrounding terrain. Negative TPI = valley; positive TPI = ridge.

**Why multi-scale:** DC metro terrain is relatively flat (max ~100m relief). At 1km radius only, most cells score near-zero TPI, making the feature near-uninformative. Using two scales captures both small features (Rock Creek valley, ~300–600m wide) and broader basin structure (Potomac corridor, Piedmont-Coastal Plain transition).

**Computation:**
```
TPI_500m = elevation - mean(elevation in 500m radius neighborhood)
TPI_2km  = elevation - mean(elevation in 2km radius neighborhood)
TPI_multi = 0.6 × TPI_500m + 0.4 × TPI_2km
```
Normalize to [-1, +1] using 2nd–98th percentile of TPI_multi across the grid.

**Research backing:** B7 (Morichetti et al. 2023), A2 (NWS Fog Guide), A12 (NWS Mountain/Valley Fog)

### Feature 2: Impervious Fraction (Inverted)

**What it captures:** Urban heat island effect. High impervious surface (dense pavement, rooftops) retains heat overnight, suppressing the radiative cooling that drives fog formation. High impervious = lower fog weight.

**Computation:**
```
imperv_norm = normalize(1 - NLCD_impervious_fraction)
# inversion: high impervious → low value → negative fog contribution
```
Normalize inverted value to [-1, +1].

**Research backing:** B9 (Klemm & Lin 2020) — documents "fog hole" effect over urban cores, showing urbanization inhibits low-level fog formation.

### Feature 3: Surface Moisture

**What it captures:** Surface moisture availability as a fog formation aid. Wet surfaces (rivers, reservoirs, wetlands) add water vapor to the low-level boundary layer, reducing the T-Td spread needed for fog onset.

**Computation:**
```
open_water_frac = fraction of NLCD pixels classified as open water within 1km radius
wetlands_frac   = fraction of NLCD pixels classified as wetland (any type) within 1km radius
surface_moisture = 0.7 × open_water_frac + 0.3 × wetlands_frac
surface_moisture_norm = normalize(surface_moisture)  # normalized, then clamped ≥ 0
```

**Why merged:** Open water and wetlands act through the same physical mechanism (surface evaporation → boundary layer moisture). With no ground truth at sub-station resolution to distinguish their contributions, merging them into one feature with a sensible physical weighting (open water weighted higher for stronger evaporative flux) reduces unnecessary parameters.

**Why clamped positive:** Absence of nearby water does not suppress fog — it simply removes one moisture source. Only cells near water get a positive contribution; cells away from water receive zero adjustment, not a penalty.

**Research backing:** Physically motivated; supported by fog type descriptions in the PRD (advection fog from Potomac, steam fog on reservoirs). Literature citation is weaker than TPI and impervious — treat this feature's weight with more humility.

### Feature 4: Cosine Aspect

**What it captures:** North-facing slopes receive less solar radiation, stay cooler overnight, maintain higher relative humidity into early morning when fog peaks. South-facing slopes warm and dry out faster.

**Computation:**
```
cos_aspect = cos(aspect_radians)   # north = +1, south = -1, east/west = 0
```
No normalization needed — cosine output is already bounded [-1, +1].

**Note:** Aspect primarily affects fog *persistence* (how quickly it burns off) rather than fog *formation*. Its physical relevance is also seasonal — stronger in winter when solar angle is low, weaker in summer. It carries a correspondingly low weight (0.03). If validation shows it adds noise rather than signal, it is the first feature to drop.

---

## Section 4: Terrain Offset Formula

### Formula

```python
# Step 1: Compute terrain offset (range: [-0.5, +0.5] log-odds)
terrain_offset = 0.5 * (
    0.50 * TPI_multi_norm       +   # cold air pooling — strongest backing
    0.35 * imperv_norm          +   # urban heat island suppression
    0.12 * surface_moisture_norm +  # water/wetland moisture boost
    0.03 * cos_aspect_norm          # north-facing persistence bonus
)
# Weights sum to 1.0; outer 0.5 scalar caps total range at ±0.5 log-odds

# Step 2: Apply to IDW base (in log-odds space)
IDW_prob_clamped = clip(IDW_prob, 0.005, 0.995)   # prevent logit(0)/logit(1) = ±inf
final_prob = sigmoid(logit(IDW_prob_clamped) + terrain_offset)
```

### Why Log-Odds Space

Adding in log-odds space (instead of multiplying in probability space) avoids two problems:
1. **Clipping artifacts:** multiplying a probability by a scalar > 1 can push it above 1.0, requiring clipping that destroys all discrimination at the high end
2. **Asymmetry at extremes:** additive log-odds shifts are symmetric and well-behaved near 0 and 1; multiplicative probability shifts are not

### Why ±0.5, Not ±1.0

The XGBoost+Platt model is the load-bearing part of this system (AUC-PR 0.358). The terrain layer is an uncalibrated heuristic layered on top. A ±1.0 log-odds range corresponds to a ~2.7× odds shift at the extremes — large enough to override the model's signal on a significant fraction of cells. At ±0.5, the maximum effect is a ~1.6× odds shift, keeping terrain as a spatial *adjustment* rather than a *veto*.

Practical effect at ±0.5:

| IDW input | Max terrain boost (+0.5) | Max terrain suppression (-0.5) |
|---|---|---|
| 5% | → 8.7% | → 2.9% |
| 20% | → 28% | → 13% |
| 40% | → 53% | → 28% |
| 60% | → 72% | → 47% |

### Weight Rationale

Weights are expert-initialized priors based on literature confidence:

| Feature | Weight | Rationale |
|---|---|---|
| TPI_multi | 0.50 | Strongest physical + citation backing; valley pooling is the primary radiation fog mechanism |
| Impervious fraction | 0.35 | Well-documented UHI fog suppression effect (B9); directly measurable |
| Surface moisture | 0.12 | Real physical mechanism; weaker citation; higher weight than original 0.10+0.02 after merging |
| Cosine aspect | 0.03 | Real but secondary effect; seasonal; lowest confidence |

**These weights cannot be fitted from available data.** No ground truth exists at sub-station spatial resolution. Treat them as a physically motivated starting point. If post-launch observation (photographer field reports, Mesonet comparison) shows systematic under- or over-prediction in specific terrain types, recalibrate then.

### Known Limitation

**Fog-type agnostic.** The same terrain offset applies regardless of whether the forecast is a radiation fog night or an advection fog event. Terrain effects are type-dependent: valley position matters greatly for radiation fog, much less for advection fog. This simplification will produce over-corrections on some events. Revisit if post-MVP spatial error analysis shows systematic bias by fog type or season.

---

## Section 5: IDW Interpolation

### Algorithm

```python
for each grid cell:
    for each station i in [KDCA, KIAD, KBWI, KGAI, KFDK, KHEF, ...]:  # all 8
        p_i = clip(station_prediction_i, 0.001, 0.999)   # defensive: prevent logit(0/1)
        logit_i = log(p_i / (1 - p_i))
        d_i = haversine_distance(cell_center, station_coords_i)   # kilometers
        w_i = 1.0 / (d_i ** 1.5)

    w_norm = w / sum(w)
    logit_IDW = sum(w_norm * logit_i)   # blend in log-odds space
    IDW_prob = sigmoid(logit_IDW)

    # Low-confidence flag
    n_nearby = count(d_i < 100 km for all stations)
    low_confidence = (n_nearby < 3)
```

Output per cell: `IDW_prob` (float32) and `low_confidence` (bool).

### Why Log-Odds Space for IDW

Blending raw probabilities is mathematically inconsistent with the terrain step that follows (which works in log-odds). More importantly, probability averaging at the extremes is nonlinear and biased: the midpoint between 5% and 95% is not 50% in any physically meaningful sense. Log-odds blending is the correct scale for combining evidence from multiple sources.

### IDW Power Parameter

**Power = 1.5.** Lower than the conventional default (2) to reduce "bullseye" artifacts around individual stations. With only 8 stations spread over 175km, power=2 creates noticeable halos where one station dominates. Power=1.5 decays meaningfully but preserves more regional blending signal. This is a tunable parameter — if bullseye artifacts appear in validation, adjust.

### Low-Confidence Flag

Any cell more than 100km from at least 3 stations gets flagged as low-confidence. With the current 8-station network, this primarily affects the western and northern periphery of the grid. The flag does not change the computation — it adds an honest signal about where the IDW is extrapolating vs. interpolating. The app can optionally desaturate or add a hatching pattern to flagged cells.

### Known Limitation

**IDW range ceiling.** IDW output is always within the range of the 8 input station predictions. If no station predicts above 70%, the IDW base cannot exceed ~70% before the terrain offset is applied. This is generally acceptable (airport stations are themselves somewhat fog-prone), but would become a problem if elevated stations were ever added to the network (they would pull the ceiling down). Flag as an assumption: IDW range ceiling is only safe when all stations are at similar elevation tiers.

---

## Section 6: Validation Plan

These checks are run once after the terrain setup phase, before using the system for real forecasts.

### Check 1: Valley-Ridge Transect (terrain layer in isolation)

**What it tests:** Whether TPI_multi and surface_moisture are encoding terrain structure correctly.

**Method:** Plot `terrain_offset` values along 5 cross-sectional transects through known valleys:
- Rock Creek (NW DC to Maryland border)
- Potomac River gorge section (Great Falls area)
- Anacostia River valley
- Dulles corridor / Broad Run valley
- Seneca Creek valley

**Pass criterion:** Terrain offset at valley floors is monotonically or near-monotonically higher than adjacent ridgelines. If valleys and ridges score similarly, TPI is not working (likely the neighborhood radius issue — revisit TPI_multi weighting or radius).

### Check 2: Urban Suppression Check (terrain layer in isolation)

**What it tests:** Whether the impervious fraction signal is encoding the urban heat island gradient correctly.

**Method:** Overlay the impervious contribution component of `terrain_offset` on a map of DC urban core vs. inner suburbs vs. outer suburbs. Compute mean terrain offset by rough zone.

**Pass criterion:** DC urban core (inside the Beltway, especially Capitol Hill–downtown corridor) shows clearly lower terrain offset than suburban Montgomery County, Loudoun County, and Prince George's County. KDCA's surrounding cells should show visible suppression; KIAD's surroundings should be roughly neutral.

### Check 3: Hold-Out Station Test (spatial interpolation accuracy)

**What it tests:** Whether the IDW layer is doing real interpolation at unobserved locations, or just recapitulating the nearest station.

**Method:**
1. Withhold one interior ASOS station — **KIAD (Dulles)** recommended; it is geographically interior and has a good data record
2. Run the full pipeline (IDW from remaining 7 stations + terrain) for the 2024 test period
3. Compare predicted probability at KIAD's grid cell against KIAD's actual observed fog events
4. Compute AUC-PR at the held-out station

**Pass criterion:** AUC-PR at held-out station is above naive baseline (nearest-neighbor of remaining 7 stations) and does not catastrophically degrade vs. the full 8-station model. A modest drop is expected and normal — you are predicting at a harder location.

**What this test cannot do:** KIAD is an airport (flat terrain), so this test validates IDW interpolation accuracy but says nothing about whether the terrain offset is working correctly in non-airport terrain.

### Check 4: Historical Event Replay

**What it tests:** Whether the combined IDW + terrain layer produces physically plausible spatial patterns on known fog days.

**Method:** Select 5 days from 2024 where a Dense Fog Advisory was issued for the DC metro area (check NWS LWX archives). Run the spatial layer for the forecast hour when fog was most widespread at ASOS stations. Examine the output map.

**Pass criterion (visual):**
- Potomac River valley shows elevated probability vs. adjacent DC urban core
- Rock Creek corridor shows elevated probability vs. surrounding neighborhoods
- KDCA area (riverine, low-lying) shows higher probability than elevated suburban areas in similar synoptic conditions

### Check 5: Sensitivity Sanity Test

**What it tests:** Whether the terrain offset formula is producing mathematically valid output across the full range of inputs.

**Method:** Set all 8 stations to a flat probability (30%). The IDW output is exactly 30% everywhere. Apply terrain offsets. Examine the output grid range.

**Pass criterion (formula-derived):** For input = 30% (logit ≈ -0.847):
- Maximum output = sigmoid(-0.847 + 0.5) = sigmoid(-0.347) ≈ **41%**
- Minimum output = sigmoid(-0.847 - 0.5) = sigmoid(-1.347) ≈ **21%**
- Any output outside [21%, 41%] indicates a formula or normalization bug

Repeat at 10%, 50%, and 70% to verify the formula behaves correctly across the full input range.

### Check 6: Bullseye Artifact Check

**What it tests:** Whether IDW power=1.5 is creating circular halos around individual stations that override terrain signal.

**Method:** Find a historical event where 1 station reported fog and its immediate neighbors did not. Generate the IDW output (pre-terrain) and the final output (post-terrain) for that hour.

**Pass criterion:** In the final output, probability contours near the fog-reporting station follow terrain features (river corridors, valley floors, low TPI areas) rather than forming a clean circle centered on the station's coordinates. If the circle is clearly visible in the final output and does not align with any terrain feature, reduce IDW power from 1.5 to 1.2 and re-run.

---

## Open Questions for Phase 2

These are deferred from this design but should be revisited once the MVP is running:

1. **Maryland Mesonet validation:** If MD Mesonet stations within the domain report visibility, use them as out-of-sample spatial ground truth. Check feasibility before implementing (not all Mesonet stations report visibility).

2. **Terrain-defined western boundary:** The Blue Ridge crest at ~77.9°W is a meteorologically meaningful boundary for cold-air drainage fog. If coverage expands into the Shenandoah Valley, consider defining the western edge by ridge crest rather than arbitrary longitude.

3. **Fog-type conditioning:** If spatial error analysis post-launch shows systematic under-correction on advection fog days (vs. radiation fog nights), consider a two-regime terrain weight set keyed by synoptic classification.

4. **IDW power tuning:** If validation shows bullseye artifacts that terrain cannot correct, systematically test power values (1.0, 1.2, 1.5, 2.0) using the hold-out station AUC-PR as the objective.

5. **Re-calibration layer:** The post-terrain output is not a calibrated probability. If the app ever displays probability numbers to users (not just a relative color scale), a post-hoc isotonic regression calibration against withheld station observations would restore interpretability.

---

## Bibliography References

- **B7** Morichetti et al. (2023) — sub-kilometer terrain heterogeneity and radiation fog
- **B9** Klemm & Lin (2020) — urban heat island fog suppression
- **A2** NWS Fog Forecasting Guide — fog predictor thresholds
- **A12** NWS Mountain and Valley Fog — cold air drainage mechanisms
- **C8** USGS 3DEP 1m DEM
- **C9** USGS NLCD
