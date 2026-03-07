# Spatial Layer Implementation Guide

**Fogchaser — DC Metro Fog Probability Map**
Last updated: 2026-03-03

---

## What This Layer Does

The fogchaser XGBoost model predicts fog probability at eight specific airport weather stations around DC. That gives you eight dots on a map. This spatial layer takes those eight numbers and spreads them across a continuous grid of roughly 120,000 cells, each 500 meters across — so instead of "Dulles Airport: 35% chance of fog," you get a full map showing which river corridors, valley floors, and suburban pockets have elevated fog risk, not just what's happening at the airports. It does this by combining two things: a distance-weighted blend of the station predictions, and a one-time terrain map that knows which parts of the landscape naturally collect cold, damp air.

---

## The Two-Phase Architecture

The pipeline is split into two distinct phases. Understanding why they're separate matters for knowing when to re-run things.

**Phase 1 runs once** (or once per year at most). It downloads elevation and land cover data for the DC metro area and computes a static "terrain personality" map — which areas tend to collect fog based purely on physical geography. This map never changes unless the terrain itself changes or you decide to adjust the weighting formula. Running it takes time and internet access; you don't want to repeat it every forecast hour.

**Phase 2 runs per forecast hour** — in production, this would be four times a day (at 00, 06, 12, and 18 UTC). It takes the latest eight station predictions, blends them across the grid using distance weighting, then applies the static terrain map as a final adjustment. The heavy terrain computation is already done; Phase 2 is relatively fast.

Separating them means that if you want to tweak the terrain weights or upgrade the land cover data, you re-run Phase 1 and leave Phase 2 untouched. If the model improves and produces better station predictions, you only update Phase 2 inputs. The two phases can evolve independently.

---

## Phase 1: Terrain Setup

Phase 1 consists of three scripts run in order. Each feeds into the next.

---

### Script 1: `scripts/terrain_setup.py`

**Run once. Downloads source data and standardizes it.**

This script downloads two publicly available datasets from the US government and rescales them to a common format.

**What it downloads:**

- **3DEP elevation data (the DEM):** "3DEP" stands for 3D Elevation Program, a USGS project that maps terrain elevation for the entire US. The raw data is at 30-meter resolution — one elevation reading every 30 meters. Think of it as a very fine-grained topographic map encoded as a grid of numbers.

- **NLCD land cover data:** NLCD stands for National Land Cover Database, also from the USGS (2021 edition). It classifies every 30-meter cell in the US into a land type: open water, wetlands, developed land, forest, and so on. We use two layers from it: what type of land cover is present, and what percentage of each cell is covered by pavement and rooftops (the "impervious" layer).

**Why download these specifically:**

- Elevation tells us where valleys and ridges are. Cold, dense air drains downhill and pools in valley bottoms on calm nights — that's how radiation fog forms. You can't know where fog is likely to collect without knowing the shape of the land.
- Land cover tells us about two other fog-relevant signals: where there's water (rivers, reservoirs, wetlands add moisture to the air) and how urban an area is (dense pavement retains heat overnight and suppresses fog).

**What the script does with the data:**

After downloading, it reprojects everything to a standardized coordinate system (EPSG:5070, which is a flat projection of the US that measures distances accurately in meters) and resamples everything to 500-meter cells. Starting at 30m and going to 500m means each output cell averages together the values of roughly 278 original cells — a significant smoothing, but appropriate for a fog forecast product where sub-kilometer precision in the terrain isn't meaningful given that the atmospheric inputs are 2–3km resolution.

**Outputs:**
- `data/processed/dem_500m.tif` — elevation grid
- `data/processed/nlcd_landcover_500m.tif` — land type grid
- `data/processed/nlcd_impervious_500m.tif` — pavement fraction grid

---

### Script 2: `scripts/compute_terrain_features.py`

**Run after terrain_setup.py. Converts raw elevation and land cover into four fog-relevant signals.**

Raw elevation numbers aren't directly useful. "This cell is at 85 meters" tells you nothing about fog. What matters is whether 85 meters is *low relative to the surrounding terrain*. This script transforms the raw data into four features that each capture something physically meaningful about fog likelihood. Each feature is scaled to a range of -1 to +1 so they can be combined fairly in the next step.

---

#### Feature 1: TPI — "How much lower is this spot than its surroundings?"

**Plain English:** TPI stands for Terrain Position Index. For each cell, it computes: *is this cell in a low spot (valley, basin) or a high spot (ridge, hilltop) relative to what's nearby?*

A negative TPI means the cell is lower than its neighbors — it sits in a valley or basin. A positive TPI means it's higher — it's on a ridge or hilltop.

**Why it matters for fog:** On calm, clear nights, cold air is denser than warm air and literally flows downhill like an invisible liquid, collecting in valley bottoms and hollows. This is the primary mechanism for radiation fog. A cell with a strongly negative TPI (deep valley floor) is a natural fog collector. A cell on a ridge crest is the last place fog forms.

**The multi-scale twist:** The DC area is relatively flat — the biggest elevation changes are only about 100 meters. At a single neighborhood scale, most cells score near-zero TPI, making the feature nearly useless. To fix this, the script computes TPI at two scales and blends them:

- At 500-meter radius (1 cell), it captures small features like Rock Creek valley, which is only 300–600 meters wide.
- At 2-kilometer radius (4 cells), it captures broader basins like the Potomac corridor.

The blend is 60% small-scale + 40% large-scale. This gives meaningful contrast across the grid even where terrain is subtle.

**Important gotcha:** TPI raw values are negative for valleys and positive for ridges. But valley = fog-favoring. So in the terrain offset formula (next step), TPI is *negated* — the sign is flipped — so that valleys end up with a positive fog contribution. This is not an error; it's intentional. See the "Key Gotchas" section.

---

#### Feature 2: Impervious Fraction — "How much pavement is here?"

**Plain English:** This measures what fraction of each cell is covered by hard, impermeable surfaces: roads, parking lots, rooftops. Downtown DC scores near 100%. Rural Poolesville scores near zero.

**Why it matters for fog:** Dense urban areas trap heat. The concrete and asphalt absorb solar radiation during the day and re-radiate it at night, keeping the surface warmer than it would naturally be. Fog requires surfaces to cool below the dew point. If a neighborhood stays 3–5°F warmer than its surroundings overnight due to the urban heat island effect, it may never reach the temperature threshold for fog to form — even during the same event that fogged in nearby suburban or rural areas. This "fog hole" effect over urban cores is well-documented in the literature (Klemm & Lin 2020).

**How it's encoded:** The feature is inverted before use: high impervious fraction → low feature value. So dense urban areas get a negative contribution (suppression), and rural areas get a near-zero contribution (neutral). A grassy suburban area isn't *better* for fog than a forest — both are just "not urban" — so the feature only penalizes, it doesn't reward.

---

#### Feature 3: Surface Moisture — "Is there water nearby?"

**Plain English:** This looks at whether each cell has rivers, reservoirs, or wetlands within about 1 kilometer. Cells near the Potomac River, near Broad Run reservoir, or in wetland areas score higher.

**Why it matters for fog:** Open water surfaces continuously evaporate, adding moisture to the air directly above them. On nights when the air is almost-but-not-quite saturated, a bit of extra moisture from a nearby river or wetland can push the local air over the threshold into fog. This is a supporting factor, not the primary one.

**How it's computed:** The script counts the fraction of NLCD land-cover cells classified as open water (class 11) or wetlands (classes 90, 95) within a 1km radius of each cell. Open water gets 70% weight and wetlands 30% — because open water evaporates more actively. The result is then clamped so it can only be zero or positive: absence of nearby water is neutral, not a fog penalty. You're not punished for not being next to a river.

---

#### Feature 4: Cosine Aspect — "Which direction does this slope face?"

**Plain English:** Aspect is the compass direction a hillside faces. A north-facing slope never sees direct midday sun; a south-facing slope gets full sun. The *cosine* of the aspect angle encodes this as a number: north-facing = +1, south-facing = -1, east- or west-facing = 0.

**Why it matters for fog:** North-facing slopes stay cooler overnight because they receive less solar heating during the day. Cooler surfaces are more likely to reach the dew point, so fog tends to form and linger longer on north-facing terrain.

**Caveat:** This effect is real but secondary. It matters more for fog *persistence* (how long it hangs around in the morning) than for fog *formation*. It's also more important in winter (when the sun is low) than in summer. This feature carries the lowest weight in the formula (3%) and is the first candidate for removal if it turns out to add noise instead of signal.

---

### Script 3: `scripts/build_terrain_offset.py`

**Run after compute_terrain_features.py. Combines the four features into a single adjustment grid.**

This script takes the four normalized features from the previous step and blends them into one number per cell: the **terrain offset**. This offset will later be added to (or subtracted from) the model's probability estimate for that cell.

**The weights:**

| Feature | Weight | Why this weight |
|---|---|---|
| TPI (valley/ridge position) | 50% | Strongest scientific backing for radiation fog; cold-air pooling in valleys is the dominant mechanism |
| Impervious fraction (urban) | 35% | Urban heat island suppression is well-documented and highly measurable |
| Surface moisture (water nearby) | 12% | Real effect, weaker citation support; treated with appropriate humility |
| Cosine aspect (slope direction) | 3% | Real but secondary and seasonal |

**What the offset number means:**

The output is not a probability; it's a shift in "log-odds space." The value at each cell ranges from about -0.5 to +0.5. A positive offset means terrain pushes fog probability up at this location; a negative offset means terrain pushes it down.

The outer scale factor of 0.5 (the multiplier applied to the whole formula) was deliberately chosen to keep terrain as an *adjustment*, not an *override*. A ±0.5 log-odds shift corresponds to about a 1.6× change in the odds of fog — meaningful but not enough to completely reverse a strong model prediction. This preserves the XGBoost model's signal as the authoritative source of truth, with terrain as a spatial refinement layer on top.

**Outputs:**
- `data/processed/terrain_offset_grid.tif` — the main terrain map, one number per 500m cell
- `data/processed/terrain_grid_metadata.csv` — records all parameters used (weights, sources, date generated), so you know what went into any given map

---

## Phase 2: Per-Hour Pipeline

**Script: `scripts/spatial_pipeline.py`**

This script runs once per forecast hour. It takes the eight station probability predictions and produces a full map.

---

### Step 1: IDW Interpolation — "Spreading eight points across 120,000 cells"

**What IDW means:** IDW stands for Inverse Distance Weighting. The intuition is simple: *closer stations matter more*.

If you want to estimate fog probability at a point in Fairfax County, and Dulles (KIAD) is 20km away while Reagan National (KDCA) is 35km away, Dulles should contribute more to your estimate than Reagan National. IDW formalizes this: each station's contribution is inversely proportional to its distance from the cell. Double the distance → roughly half the weight (depending on the power parameter).

**Why log-odds instead of probabilities:** The blending happens in log-odds space, not in raw probability space. Log-odds is how you convert a probability into a number that can be added and averaged fairly.

Think of it this way: averaging "5% fog" and "95% fog" gives you 50% — but that average has no physical meaning. Those two stations are telling completely different stories about the atmosphere. In log-odds space, 5% becomes -2.94 and 95% becomes +2.94. Averaging those gives zero, which converts back to 50% — the same answer, but now it's reached through a mathematically coherent path that behaves correctly near the extremes of the probability scale.

More practically: all the operations in this pipeline (IDW blending, terrain offset addition) are additions and averages in log-odds space. Doing everything in the same space keeps the math consistent from start to finish.

**The power parameter — why 1.2, not higher:**

The standard default for IDW power is 2. With only 8 stations spread across 175 kilometers of terrain, power=2 creates "bullseye" artifacts: a circular halo of elevated probability centered precisely on each station, dropping off sharply to the station's surroundings. This looks unphysical on a map and would make the terrain signal hard to see.

Power=1.2 decays more gently with distance, allowing stations to influence a broader area and blend more smoothly into each other. It's lower than what the design document originally specified (1.5) — validation Check 6 showed the bullseye was still visible at 1.5, and 1.2 fixed it. See "Key Gotchas" below.

**Low-confidence flag:** Any cell that has fewer than 3 stations within 100km gets flagged as low-confidence. This mostly affects the western and northern edges of the grid. The probability is still computed there, but the app can display those cells differently (hatched, faded, or grayed out) to signal "we're extrapolating here, not interpolating."

---

### Step 2: Adding the Terrain Offset

Once IDW gives a base probability for every cell, the terrain offset from Phase 1 is added. This happens in log-odds space:

1. Convert the IDW probability to log-odds
2. Add the terrain offset (positive = fog boost, negative = fog suppression)
3. Convert back to a probability with the sigmoid function

The result: cells in valley floors get a small upward nudge; cells in the urban core get a small downward nudge; cells on ridges get a small downward nudge. The nudge is capped at ±0.5 log-odds so terrain can never completely override the model.

**What the output probability means:** After applying the terrain offset, the probability is no longer strictly "calibrated" in a statistical sense. The XGBoost model was carefully calibrated at airport stations — when it says 30%, it means roughly 30% of similar situations historically had fog. The terrain offset is a physically motivated adjustment, not a fitted correction, so it breaks that calibration guarantee. The output should be read as a *relative likelihood score* — "this valley is more likely to have fog than that ridge, given the same atmospheric conditions" — rather than a literal percentage.

---

### Output

Each run produces one file:

`outputs/spatial/fog_prob_YYYYMMDD_HHUTC.tif`

This is a GeoTIFF — a standard geographic image format readable in QGIS, ArcGIS, Python, or any mapping tool. Each pixel is a float32 value between 0 and 1 (fog probability after terrain adjustment). Cells flagged as low-confidence are stored with the special value -9998 so they can be identified and displayed differently. Missing-data cells are -9999.

---

## How to Run It — From Scratch

Run these commands in order from the project root directory. Phase 1 only needs to run once; Phase 2 runs each forecast cycle.

**Phase 1 (one-time setup):**

```
python scripts/terrain_setup.py
python scripts/compute_terrain_features.py
python scripts/build_terrain_offset.py
```

**Validation (run once after Phase 1, before using in production):**

```
python scripts/validate_spatial.py
```

**Phase 2 (run each forecast hour, passing real model predictions):**

The Phase 2 script (`spatial_pipeline.py`) is designed to be called from another script that feeds it the eight station probabilities. For manual testing or inspection, import and call `run_spatial_pipeline()` directly with lists of probabilities, latitudes, and longitudes for the eight stations.

**Notes on environment:**

- Phase 1 requires an internet connection to download 3DEP and NLCD data.
- Phase 1 DEM download can take a few minutes depending on connection speed.
- If `data/processed/dem_500m.tif` already exists, `terrain_setup.py` skips the DEM download automatically.
- All outputs land in `data/processed/` (terrain files) and `outputs/spatial/` (forecast maps).

---

## Validation — What Was Tested

Six checks were designed to verify the spatial layer before use. All are in `scripts/validate_spatial.py`. Here's what each one tests in plain terms.

---

**Check 1: Valley-Ridge Transects**

*What it tests:* Does the terrain offset actually go up in valleys and down on ridges?

Five cross-sections were drawn through known DC-area valleys: Rock Creek east-west, the Dulles corridor, the Potomac near DC, a Fairfax County ridge-valley, and the Patuxent River corridor. For each one, the terrain offset values were plotted from one side to the other.

*Pass criterion:* Valley bottoms show higher terrain offset than the adjacent ridges in at least 3 of 5 transects.

*What to watch for:* If valleys and ridges look the same, the TPI computation has a bug. The most common cause would be the NaN-boundary issue in the TPI calculation (see "Key Gotchas").

---

**Check 2: Urban Suppression**

*What it tests:* Does the impervious fraction feature correctly show lower fog likelihood in the dense urban core?

Six specific locations were sampled: downtown DC, Crystal City (urban), Rockville (suburban), Dulles Airport area, Poolesville (rural), and Great Falls (rural). The impervious feature value was read at each.

*Pass criterion:* Urban zones (downtown, Crystal City) show lower impervious feature values than rural zones. Lower value = more urban heat island suppression = lower terrain offset.

*What to watch for:* If the NLCD download fails or covers the wrong area, urban and rural values will look similar. Check whether the downloaded `nlcd_impervious_500m.tif` covers the DC metro area correctly.

---

**Check 3: Hold-Out Station Test**

*What it tests:* Is IDW doing actual spatial interpolation, or is it just copying the nearest station?

Dulles Airport (KIAD) was held out of the station set. The pipeline was run using the remaining 7 stations only, and the predicted probability at KIAD's location was compared against KIAD's actual fog observations over 2024.

*Pass criterion:* IDW from 7 stations achieves AUC-PR at least as good as simply using the nearest station's reading. (A small drop from the full 8-station model is expected and normal.)

*What to watch for:* This test uses binary 0/1 fog labels as proxy probabilities, not real model predictions. Binary inputs can saturate IDW in log-odds space (see "Key Gotchas"). The test still validates the spatial machinery, but interpret the absolute AUC-PR numbers with caution — they reflect spatial interpolation accuracy with crude inputs, not forecast accuracy with calibrated inputs.

---

**Check 4: Historical Event Replay**

*What it tests:* On real historical fog days, does the output map look physically plausible?

The 5 hours in the 2024 test data where the most stations simultaneously reported fog were identified. The spatial pipeline was run for the top 2 of those hours and maps were saved.

*Pass criterion:* Visual inspection — Potomac and valley corridors should show elevated probability; urban DC should show suppression relative to surroundings.

*What to watch for:* This check uses binary 0/1 labels again (same saturation caveat as Check 3). On hours where all 8 stations simultaneously reported fog, the IDW surface saturates at very high values everywhere — the terrain offset nudges can barely be seen relative to the near-1.0 base. The maps still show correct spatial structure, but interpret them knowing the base is inflated. In real use, calibrated probabilities (0.05–0.40 range) will make the terrain differentiation much more visible.

---

**Check 5: Sensitivity Sanity Test**

*What it tests:* Is the math correct? Does the output stay within analytically predictable bounds?

All 8 stations were set to exactly 30% fog probability. Since all inputs are identical, IDW should give exactly 30% everywhere. The terrain offset then shifts each cell up or down by at most ±0.5 log-odds.

*Pass criterion:* Output must stay within the analytically derived bounds: minimum ~21%, maximum ~41%. Any output outside that range indicates a formula or normalization bug.

*What to watch for:* This is a clean mathematical test — if it fails, something is wrong with the terrain offset formula or the way features were normalized. Check `build_terrain_offset.py` first.

---

**Check 6: Bullseye Artifact Check**

*What it tests:* Does IDW create unnatural circular halos around individual stations?

A synthetic scenario was constructed: Reagan National (KDCA) reports 80% fog; all 7 other stations report 5%. The output map was saved and visually inspected.

*Pass criterion:* The high-probability zone near KDCA should follow terrain features (Potomac riverfront, low-lying areas) rather than forming a perfect circle centered on KDCA's coordinates.

*What to watch for:* If you see a crisp circular halo, IDW power is too high. The design document originally specified power=1.5, but the bullseye was visible at that value. The implementation uses power=1.2, which passed this check. If you re-tune the power parameter, re-run this check.

---

## Known Limitations

These are not bugs — they're deliberate simplifications made for MVP that should be revisited over time.

**Static terrain offset.** The terrain map never changes based on the weather type. Valley fog from cold air pooling is very different from advection fog blowing in off the Chesapeake Bay, but both get the same terrain adjustment. On heavy advection fog nights, the valley-bias correction will over-fire (valleys won't be disproportionately foggier than usual), and on strong radiation fog nights it may under-fire. The terrain layer is always "on" regardless of whether it's appropriate for that night's fog type.

**500-meter resolution is a terrain resolution, not a forecast resolution.** The grid is fine enough to distinguish Rock Creek valley from the adjoining neighborhoods, but the atmospheric information feeding it (from 8 stations and 3km HRRR data) does not support 500m forecast skill. The map shows where fog is *terrain-favored*, not where there's an independent 500m atmospheric forecast.

**Airport sampling bias.** All 8 stations are airports — flat, open, low-obstruction sites at similar elevations. Airports are systematically not in the places where fog is most likely to form (valley floors, river bottoms, wetland edges). The terrain layer partially corrects for this after the fact, but it's working against the grain of the sampling design. Spots like the C&O Canal towpath or the Potomac floodplain near Seneca may routinely have fog that no station ever sees.

**Check 4 saturation with binary inputs.** When validation runs use raw 0/1 fog labels as inputs to the IDW, hours where many stations simultaneously reported fog saturate the output at near-100% everywhere. The terrain differentiation is real in the formula but invisible in the map because the base is so high. This is a validation artifact, not a real-world problem — in production, calibrated probabilities in the 0.05–0.40 range give the terrain offset room to show contrast.

**Eastern grid edge near Chesapeake Bay.** Marine advection fog from the Bay operates on different physics than the radiation fog the model was trained on. Probability values near the eastern edge of the grid (roughly east of the Patuxent River) should be treated with extra caution.

---

## Key Implementation Decisions and Gotchas

These are the things most likely to cause confusion if you revisit this code later or hand it off to someone else.

---

**TPI sign is flipped in the formula — this is intentional.**

Raw TPI is negative for valleys (lower than surroundings) and positive for ridges (higher than surroundings). But valleys are *fog-favoring*. So in `build_terrain_offset.py`, the TPI term is written as `(-tpi)` — the negative sign is explicitly there to flip it. After negation: valley = positive contribution = fog boost. Ridge = negative contribution = fog suppression.

This is correct physics. Do not "fix" it.

---

**IDW power = 1.2, not the design document's 1.5.**

The design document (`docs/plans/2026-03-02-spatial-layer-design.md`) specified power=1.5. After implementing and running Check 6 (the bullseye check), the circular halo artifact was still visible at 1.5 with only 8 stations. Power was reduced to 1.2, which resolved the artifact. The code in `spatial_pipeline.py` uses 1.2 as the default. The design doc is now out of date on this specific parameter.

---

**Never feed raw 0/1 binary labels into IDW in production.**

IDW in log-odds space requires probabilities, not binary outcomes. Feeding in 0 or 1 is mathematically catastrophic: logit(0) = -infinity, logit(1) = +infinity. The code clips inputs to [0.001, 0.999] as a defense, but this means a raw "1" (fog observed) becomes 0.999, which in log-odds is about +6.9 — an extremely large number that will dominate the weighted average for most of the grid. The result is a near-saturated map that looks like fog everywhere, regardless of terrain.

In production, always feed calibrated model probabilities. The XGBoost+Platt model produces values in the 0.05–0.40 range for most situations — these are the right inputs. The validation scripts used binary labels as a convenience (to avoid needing the model at test time), and Check 4 explicitly notes the saturation issue as a consequence.

---

**TPI NaN boundaries use count-corrected mean, not zero-fill.**

At the edges of the grid, a neighborhood average needs to handle cells that fall outside the data boundary. The naive approach is to fill NaN boundary cells with zero before averaging. This is wrong: it would make edge cells look artificially lower or higher than their surroundings, creating false TPI signals along the data boundary.

The correct approach (implemented in `compute_terrain_features.py`) computes the average only over *valid* cells in the neighborhood: sum of valid values divided by count of valid values. This is called a "count-corrected mean." The result is that boundary cells get a fair TPI relative to the neighbors they actually have, rather than being compared to phantom zero-elevation cells.

---

**All coordinate transforms follow the same pattern: WGS84 download → EPSG:5070 processing → WGS84 for IDW.**

The terrain files are stored in EPSG:5070 (a flat projected coordinate system accurate in meters, suitable for the US). The IDW computation uses geographic coordinates (latitude/longitude) and haversine distances in kilometers. Phase 2 (`spatial_pipeline.py`) handles the conversion automatically — it reads the terrain raster's EPSG:5070 grid, converts cell centers to latitude/longitude using pyproj, then passes those to the haversine distance function. You don't need to think about this in normal use, but if you ever modify the pipeline to output to a different coordinate system, watch for this conversion step.

---

*End of guide.*
