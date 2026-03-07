# Spatial Interpolation Layer — Session Handoff

**Date written:** 2026-03-02
**Status:** Ready for design — start a new session for this work
**Context:** HRRR extraction and modeling session kept separate

---

## What This Is

Right now the model produces fog probability at 8 ASOS stations (all DC metro airports).
The app vision requires a continuous fog probability MAP — showing probability at arbitrary
locations like Rock Creek valley, the C&O Canal corridor, the Potomac River overlooks.
None of those places have ASOS stations.

The spatial interpolation layer is what bridges that gap. It takes the 8 station
predictions and extends them spatially using terrain data, so the app shows a map
instead of 8 dots.

**This is not a model accuracy problem. It is a display/product problem.**
The model stays the same. What changes is how we serve predictions across space.

---

## Key Decision Already Made

**Terrain as ML features → deferred.**
Adding DEM/TPI/NLCD as training features to the XGBoost model is low value right now
because all 8 test stations are at airports (flat terrain). The gain is unmeasurable
on this test set. Revisit when expanding to more cities with diverse terrain.

**Terrain as spatial layer → build now.**
This is what makes fogchaser a discovery tool instead of a weather widget.
The competitive differentiation in the PRD ("a river valley and a ridge in the same
model grid cell get different probability weights") lives entirely here.

---

## What the Spatial Layer Needs to Do

Given: fog probability predictions at 8 ASOS stations for a target hour
Output: fog probability at every pixel/point on the DC metro map

**The two-step architecture (from PRD):**

1. **Spatial interpolation** — extend the 8 station predictions across the map
   (some form of interpolation or kriging based on distance + elevation similarity)

2. **Terrain weighting** — adjust the interpolated probability up or down
   based on local terrain characteristics at each map point:
   - Valley depth (cold air pooling potential) → higher weight
   - Terrain position index / TPI (valley vs flat vs ridge classification) → valleys higher
   - Distance to nearest water body (Potomac, Anacostia, Rock Creek, reservoirs) → proximity = higher
   - Impervious surface fraction / NLCD (urban heat island) → high impervious = lower weight
   - Land cover class (wetland, forest, open water, agricultural vs urban)

---

## Data Sources Needed (all free, one-time download)

**USGS 3DEP Digital Elevation Model**
- Resolution: 1 meter (lidar-derived, full DC metro coverage)
- Download: https://apps.nationalmap.gov/downloader
- Format: GeoTIFF
- Derived features to compute: valley depth, TPI, slope aspect, flow accumulation

**USGS NLCD (National Land Cover Database)**
- Resolution: 30 meters, 21 land cover classes
- Download: https://www.mrlc.gov/data
- Format: GeoTIFF
- Derived features: impervious surface fraction, distance to nearest water body,
  dominant land cover class

**Water bodies (for distance calculation)**
- Can derive from NLCD (water class) or use NHD (National Hydrography Dataset)
- Key bodies: Potomac River, Anacostia River, Rock Creek, Chesapeake Bay influence,
  major reservoirs (Triadelphia, Rocky Gorge, Lake Needwood)

---

## Design Questions for Next Session

These need to be answered before writing any code:

**1. Interpolation method**
How do you go from 8 points to a continuous map?
- Inverse distance weighting (IDW) — simple, fast, ignores terrain
- Kriging with elevation covariate — more sophisticated, terrain-aware
- Just use the nearest station's prediction, modified by terrain — simplest
- Physics-informed: use HRRR grid (3km) as base, downscale with terrain

**2. Terrain weight formula**
How do you combine the terrain factors into a single multiplier?
- Multiplicative (each factor scales the probability)
- Additive adjustment (+/- X% based on terrain class)
- Learned weights vs manually specified

**3. Geographic bounding box**
What area does the map cover?
- PRD mentions DC metro but doesn't define the box precisely
- Rough suggestion: ~50-mile radius from Capitol, capturing Dulles corridor,
  Shenandoah foothills to the west, Chesapeake Bay influence to the east

**4. Output resolution**
What resolution does the map tile at?
- 30m (NLCD resolution) — very fine but expensive to compute
- 100m — good balance
- 1km — fast but misses sub-kilometer valley detail
- HRRR grid 3km — just annotating existing model cells, no sub-cell detail

**5. Validation**
How do we know the terrain weights are physically reasonable?
- Visual inspection: do river valleys show higher probability than adjacent ridges?
- Compare to known fog corridors from literature (Rock Creek gorge, Potomac flats)
- Backtesting: does the terrain-adjusted map predict historical fog events better?

---

## What We Have Going Into This Session

- **Model:** `models/xgb_asos_hrrr_pilot_v1.json` — ASOS+HRRR pilot (4-month training)
- **Calibrator:** `models/calibrator_platt_v1.pkl` — Platt scaling + F2 threshold (0.09)
  + fill_medians + feature list (everything needed for inference)
- **8 DC station coordinates:** available from `data/raw/asos/dc_metro_test_2024_2026.parquet`
- **HRRR grid indices:** `data/raw/hrrr/station_grid_indices.json`
- **PRD references:** B7 (terrain/radiation fog), B9 (urban heat island), C8 (3DEP DEM), C9 (NLCD)

---

## What Is Still Running (do not restart)

**HRRR full training extraction** — running in background as of 2026-03-02 evening
- Script: `/tmp/hrrr_extract_full_training.py`
- Log: `/tmp/hrrr_extract_full_log.txt`
- Output: `data/raw/hrrr/hrrr_train_{2018..2023}.parquet` (one file per year)
- Status: In progress on 2018 (~4.3hr/year, ~26hr total)
- Has checkpointing — safe to interrupt and resume
- Check progress: `tail -20 /tmp/hrrr_extract_full_log.txt`

---

## Suggested Approach for New Session

Tell Claude: "Read docs/plans/2026-03-02-spatial-layer-handoff.md and let's design
the spatial interpolation layer for fogchaser."

The session should:
1. Answer the 5 design questions above (especially interpolation method and resolution)
2. Download the DEM and NLCD data for DC metro
3. Compute terrain derivatives (valley depth, TPI, distance to water, impervious fraction)
4. Design and implement the terrain weight formula
5. Build a prototype map visualization showing fog probability across DC metro
6. Validate visually that valleys show higher probability than ridges
