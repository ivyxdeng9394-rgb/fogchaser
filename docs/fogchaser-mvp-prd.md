# Fogchaser — Product Requirements Document

**Last updated:** 2026-02-28
**Status:** Draft — in progress
**Author:** Ivy + Claude

> **Citation format:** Inline markers like [B3] refer to the Bibliography at the end of this document. Sources are grouped by category: [A] = NOAA/NWS Official Resources, [B] = Academic Research Papers, [C] = Data Sources & Access Tools, [D] = Industry & Community Sources.

---

## Table of Contents

1. [Vision & Problem](#1-vision--problem)
2. [Target Users & Pain Points](#2-target-users--pain-points)
3. [Competitive Landscape & Differentiation](#3-competitive-landscape--differentiation)
4. [Product Concept & MVP Definition](#4-product-concept--mvp-definition)
5. [Data Sources](#5-data-sources)
6. [Modeling Approach](#6-modeling-approach)
7. [UI/UX](#7-uiux)
8. [Success Metrics & North Star](#8-success-metrics--north-star)
9. [Accuracy & Testing Plan](#9-accuracy--testing-plan)
10. [What We Are Not Building](#10-what-we-are-not-building)
11. [Open Questions](#11-open-questions)
12. [Bibliography](#12-bibliography)

---

## 1. Vision & Problem

**Product Vision**
Fogchaser is a mobile-first planning tool that synthesizes atmospheric conditions into a location-specific fog probability score for the DC metro area — so photographers can make an informed go/no-go decision the night before, rather than guessing or cross-referencing multiple technical sources.

---

**Problem Statement**

Fog is one of the hardest weather phenomena to forecast accurately. According to NOAA's own research, current operational model performance for fog prediction "is still poor in comparison to precipitation forecasts" [B1], and forecast skill degrades substantially beyond 6 hours [B2]. The 6–24 hour window — exactly when photographers are planning their next morning shoot — is where current models perform worst.

Tools that exist today fall into two categories, both with real limitations:

**Category 1: General weather apps used by photographers**
Windy, Ventusky, and Clear Outside all display fog-related data (visibility layers, dew point, humidity). Windy even has a dedicated fog map overlay. But Windy's own documentation acknowledges the overlay "only indicates a relative possibility of fog occurring in an area due to prevailing forecast conditions" [D5] — it is not a fog probability product. Photographers use these tools but describe the workflow as a patchwork: combining 2–4 apps, manually checking raw meteorological variables, and relying on local terrain knowledge to make a judgment call [D6] [D7].

**Category 2: Photography-specific weather apps**
Viewfindr (Europe-focused), PhotoHound, Fotocast, PhotoWeather, and Fog Forecast all exist and have fog features. Viewfindr is the most sophisticated — it was developed with meteorologists and claims ~80% forecast accuracy [D1]. However, it focuses on Central Europe at 2.8km resolution. No comparable product exists for the US market with similar fog-specific sophistication.

**The specific gap for US photographers:**
- No US-focused app synthesizes atmospheric conditions into a fog probability score with photographer-specific framing
- No consumer app shows fog probability as a spatial map at neighborhood resolution in the US — the best available public model data (HRRR) is 3km [A3], and no app currently serves this in a photographer-friendly map UI for US locations
- NWS issues Dense Fog Advisories, but these are reactive (issued once fog is already forming), not probabilistic forecasts hours in advance [A1]
- The localization problem is real and unsolved: fog can fill one valley while a ridge 2 miles away stays clear, at scales no current public model can resolve [B2] [D4]

**What this means for Fogchaser:**
We are not building in a vacuum — tools exist. Our bet is that a US-focused, photographer-specific tool that clearly communicates probabilistic fog likelihood (not false precision) on a map, for the DC metro area's specific terrain (Potomac River, Rock Creek, low-elevation pockets), provides meaningfully better planning signal than the current patchwork. The honest constraint is that no tool — including ours — can reliably predict fog at street level 12+ hours out. We frame this as a probability aid, not a guarantee.

---

## 2. Target Users & Pain Points

**Primary User (MVP)**
Landscape and urban photographers in the DC metro area who actively seek atmospheric conditions — fog, mist, moody light — as creative opportunities. These are hobbyists to semi-professionals who plan shoots deliberately, not casually.

Characteristics:
- Already check weather apps before shoots
- Familiar with concepts like golden hour, blue hour, and shooting in specific conditions
- Willing to wake up at 4–5am and drive 30–60 minutes *if* conditions are worth it
- Currently rely on a manual, multi-app process to assess fog likelihood [D6] [D7]

**The core pain point**
The decision of whether to get up early for a fog shoot has to be made hours in advance — typically the night before. But the data needed to make that decision is scattered across technical sources that require meteorological literacy to interpret. There is no single, clear answer to: *"Is it worth going out tomorrow morning?"*

The cost of a false positive is high: wasted sleep, wasted drive time, wasted effort. The cost of a false negative is a missed creative opportunity. Right now, both happen frequently because the planning signal is weak.

**Secondary users (not the focus of MVP)**
Other potential audiences include drone operators, real estate photographers, and urban aesthetics creators. We are explicitly not designing for these users in the MVP. We are also not positioning this as a safety or navigation tool (pilots, transportation) — that introduces regulatory and liability complexity outside our scope.

**Who this is NOT for**
- Casual photographers who shoot opportunistically
- Anyone looking for safety-critical fog warnings (that's NWS's job)
- Non-US users

---

## 3. Competitive Landscape & Differentiation

**Existing tools (what's out there)**

| Tool | What it does for fog | Key limitation |
|---|---|---|
| Windy | Fog map overlay, visibility layer, dew point/humidity data | Fog overlay is "relative possibility," not probability [D5]. Requires meteorological literacy to interpret. |
| Clear Outside | Hourly fog % row, dew point, visibility | Point forecasts only, no map view [D3]. |
| Ventusky | Fog and visibility map layers | Premium feature, regional scale only, requires manual interpretation. |
| Viewfindr | Fog probability, dense fog, fog height for photographers | Europe-focused (2.8km resolution for Central Europe only) [D1]. No US coverage. |
| PhotoHound | Flags fog-likely hours based on humidity/dew point spread | Point-based, not a map [D2]. UK/Europe primary focus. |
| Fotocast | Fog notifications, "Fotoscore" | Reviews cite fog notifications as unreliable. |
| PhotoWeather | Custom alert rules including fog conditions | Alert/notification only, no map. |
| Fog Forecast | Hourly fog probability, notifications | Point forecast only, no map. Uses Apple WeatherKit (limited meteorological depth). Not yet launched. |
| NWS Dense Fog Advisory | Warning when fog is imminent | Reactive, not predictive. County/zone level, not neighborhood [A1]. |

**Where we stand out**
- The only US-focused tool with photographer-specific fog probability on a terrain-aware map
- Synthesizes multiple atmospheric variables (dew point spread, wind, humidity, cloud cover) with terrain and water proximity into a spatial probability — rather than showing raw data the user has to interpret
- DC metro terrain-aware: accounts for Potomac River proximity, Rock Creek, low-elevation pockets that fog differently than surrounding areas
- Discovery-oriented: helps users find where to go, not just confirm a spot they already have in mind

**Where we don't stand out (honest)**
- We cannot beat Viewfindr's meteorological sophistication (built with professional meteorologists, years of model refinement for their region [D1])
- We cannot offer better raw model resolution than HRRR 3km — that's the best publicly available US data [A3]
- We are not solving the fundamental scientific problem of fog predictability beyond 6–12 hours [B1] [B2]; we are making the existing signal more accessible, spatial, and usable
- Windy already shows fog on a map [D5] — our differentiation is the terrain-aware synthesis and US/photographer-specific framing, not the map concept itself

**The honest competitive position**
We are not building a meteorologically superior product. We are building a better *discovery tool* for a specific user (DC metro photographer) that the existing tools don't serve — either because they're European-focused, require technical literacy, are point forecasts without spatial context, or don't account for local terrain.

---

## 4. Product Concept & MVP Definition

**Core concept: Fog discovery, not fog forecasting**

Fogchaser is not a "will it be foggy at my spot" tool. It answers a different question: *"Where should I go tomorrow morning to find fog?"* This is a spatial discovery tool built for the act of chasing — you open the map, see which corridors and terrain pockets look promising, and decide where to go.

This framing is what separates Fogchaser from every existing tool. Point forecast apps (Fog Forecast, Clear Outside, PhotoWeather) require you to already know where you're going. Fogchaser helps you find where to go.

---

**What the MVP does**

- Displays a fog probability map of the DC metro area
- Probability is terrain-aware: atmospheric model data (3km resolution) is weighted by elevation and water proximity so that river corridors, low-lying valleys, and areas near the Potomac and Rock Creek show higher probability than ridges and elevated terrain in the same model cell [B7] [B8]
- Shows hourly probability for the next 12–24 hours (the most reliable forecast window per the scientific literature [B2])
- Mobile-first web app — works in your phone browser, no installation

**What the MVP does not do**

- Sunrise/sunset quality scoring (future phase)
- Notifications or alerts
- User accounts or saved locations
- Multi-city support — DC metro only
- Native mobile app
- Historical fog data or trends
- Other weather phenomena

**Why these boundaries**

The 12–24 hour window is where fog prediction skill is highest — scientific research shows skill degrades substantially beyond that [B2]. DC metro only keeps the terrain modeling tractable for a proof of concept. No accounts or notifications keeps the build simple. Sunrise/sunset is the clear second feature but fog alone is enough to validate whether the core discovery concept works.

---

## 5. Data Sources

All claims in this section are based on peer-reviewed research, NOAA documentation, and the meteorological literature reviewed as part of this PRD process.

### Primary Forecast Source: National Blend of Models (NBM)

The NBM is NOAA's operational multi-model ensemble blend. It takes HRRR as a key input, then bias-corrects it against historical observations and blends in ECMWF, GEFS, and other models. Research and operational practice confirm NBM outperforms raw HRRR for visibility/fog forecasting [B3] [A5]. This is what we serve to users in the app.

- Resolution: 2.5km (CONUS)
- Update frequency: Hourly
- Forecast variables: Visibility, cloud ceiling, cloud cover, temperature, dew point, wind
- Access: Free on AWS S3 (`noaa-nbm-pds` bucket), also NOMADS [C5]
- Why not raw HRRR: HRRR has documented systematic biases in fog intensity and timing [B1]. Raw HRRR visibility is diagnosed, not directly predicted, and carries compounding errors [A4]. NBM corrects these. Research confirms that post-processed HRRR blends outperform raw HRRR for ceiling and visibility [B3].

### Raw Model Source for Custom Model Building: HRRR

When we build our own fog probability model (Phase 1), we train it on raw HRRR model state variables — not NBM output. HRRR gives us the underlying atmospheric physics (cloud liquid water mixing ratio, planetary boundary layer height, soil moisture, longwave radiation flux) that NBM doesn't expose.

- Resolution: 3km
- Update frequency: Hourly
- Key fog-relevant variables: VIS (visibility), CEIL (ceiling height), LCDC (low cloud cover), TMP/DPT at 2m (temperature/dew point), RH at 2m, UGRD/VGRD at 10m (wind), HPBL (boundary layer height), SOILW (soil moisture at multiple depths), DLWRF/ULWRF (longwave radiation flux), CLWMR (cloud liquid water mixing ratio) [A3] [A6]
- Access: Free on AWS S3 (`noaa-hrrr-bdp-pds`), via Python `herbie` library [C4]
- Note: HRRR already includes soil moisture (SOILW) — no separate soil moisture data source needed [A6]
- Practical challenge: GRIB2 format, files >100MB each; `herbie` library handles byte-range requests to download only specific variables [C4]

### Observation Data: ASOS/METAR via Iowa Environmental Mesonet (IEM)

Surface observation station data is essential — not just supplementary. It serves two critical roles: (1) provides historical fog event labels for model training (was there actually fog at this location at this time?), and (2) provides real-time near-surface state variables as input features [B10] [B12].

- DC metro coverage: ~15–20 ASOS/AWOS stations within 50 miles, including KDCA, KIAD, KBWI, KGAI, KFDK, KHEF, and others [C1]
- Key variables: Visibility (1/4 SM increments), present weather codes (FG = fog, BR = mist), ceiling height, temperature, dew point, wind speed/direction, pressure [C1]
- Access: Iowa Environmental Mesonet (IEM) — free, clean CSV format, all US ASOS back to ~1995; no registration required [C2]
- Also accessible via: NOAA Integrated Surface Database (ISD) on AWS [C3]
- Limitation: Station network is airport-centric; ~300–600 square miles per station. Fog in narrow river valleys (Rock Creek gorge) may not register at any ASOS until already well-developed [C1].

### Supplementary: Maryland Mesonet

The University of Maryland operates a 75-station mesonet across Maryland at ~10-mile spacing, measuring temperature, humidity, wind, precipitation, solar radiation, and soil moisture at 5 depths with 1-minute sampling [C6]. This is substantially denser than ASOS and directly relevant to our DC metro focus area.

- Access: UMD Mesonet portal and potentially via Synoptic Data API (free research tier) [C7]
- Priority: High for Phase 1 model validation; assess for operational inclusion in Phase 2

### Static Terrain Layers: USGS 3DEP + NLCD (One-Time Setup)

These are downloaded once and used as static feature layers. They don't require ongoing ingestion.

**USGS 3DEP Digital Elevation Model (DEM)**
- Resolution: 1 meter (lidar-derived, full coverage for DC metro area)
- Access: USGS National Map (apps.nationalmap.gov) — free, no account required, GeoTIFF format [C8]
- Derived variables we compute: valley depth (how low a point is relative to surrounding terrain), terrain position index (TPI: valley/flat/ridge classification), slope aspect, flow accumulation (proxy for cold air pooling potential)
- Why it matters: Even 20–30 meters of elevation difference determines whether a location sits in a cold-air pool or just above it. Research confirms sub-kilometer terrain heterogeneity is a primary driver of spatial variability in radiation fog [B7].

**USGS National Land Cover Database (NLCD)**
- Resolution: 30 meters, 21 land cover classes (urban at 4 intensity levels, forest, wetlands, open water, agricultural)
- Also provides: impervious surface percentage, tree canopy cover
- Access: MRLC Consortium (mrlc.gov) — free, GeoTIFF format [C9]
- Why it matters: Land cover drives surface energy balance. Urban areas (high impervious surface) store heat and suppress radiative cooling — producing the "urban heat island fog hole" effect documented in research across multiple US cities [B9]. Our map should reflect this gradient.
- Derived variables: impervious surface fraction, distance to nearest water body, dominant land cover class

### Data Sources Comparison Table

| Source | Role | Resolution | Update Freq | Cost | Format | Priority |
|---|---|---|---|---|---|---|
| NBM [A5] | Operational forecast (served to users) | 2.5km | Hourly | Free | GRIB2 | Essential |
| HRRR [A3] | Custom model training features | 3km | Hourly | Free | GRIB2 | Essential |
| ASOS/IEM [C1] [C2] | Training labels + real-time features | Point (15–20 stations) | Hourly | Free | CSV | Essential |
| USGS 3DEP DEM [C8] | Static terrain features | 1m | Static | Free | GeoTIFF | Essential |
| NLCD [C9] | Static land cover features | 30m | Static (~3yr) | Free | GeoTIFF | Essential |
| Maryland Mesonet [C6] | Dense DC observations, soil moisture | ~10mi spacing | 1-min | Free/research | API | High |
| GOES-16 [C10] | Nowcasting validation (future) | 2km | 5 min | Free | netCDF | Future |
| ERA5 Reanalysis [C11] | Extended historical training | 31km | Hourly | Free | NetCDF | Future |

### What We Decided Not to Use (and Why)

- **OpenWeather / Tomorrow.io**: Less meteorological depth than NBM/HRRR; cost at volume; less transparency about methodology
- **Apple WeatherKit** (used by Fog Forecast): Proprietary, no control over model, limited fog-specific variables
- **Separate SMAP soil moisture**: Unnecessary — HRRR already outputs SOILW at multiple soil depths [A6]; SMAP's 2–3-day revisit time limits operational utility
- **GOES-16 for MVP**: Useful for 0–6 hour nowcasting [B13], but daytime limitations [C10], 2km resolution misses narrow valley fog, and adds technical overhead. Revisit in Phase 2.

---

## 6. Modeling Approach

This section describes the high-level approach. Detailed implementation is Phase 1 work.

### The Core Challenge (Stated Honestly)

Fog is one of the meteorologically hardest phenomena to predict. NOAA's own research states that "performance of low visibility/fog forecasts from NWP models is still poor in comparison to precipitation forecasts" [B1]. NWS documentation requires grid spacing ≤ 50m for adequate turbulence representation [A2]; the best operational model (HRRR) runs at 3km [A3]. Fog formation is genuinely non-linear and multivariate — no single variable is sufficient [B4] [B5].

Our approach accepts these limits and works within them: we provide a probability aid that is better than the current patchwork, not a guarantee.

### Fog Types Relevant to DC Metro (Validated by Research)

**Radiation fog (dominant):** Forms in the early hours between midnight and dawn under clear skies, light winds (1–3 m/s), high humidity, and overnight radiative cooling [A2]. Peaks October–March. Most common in low-lying terrain: river corridors (Potomac, Anacostia, Rock Creek), suburban valleys, Dulles Airport corridor.

**Valley fog (subtype of radiation fog):** Cold dense air drains off slopes into valley floors (katabatic flow) [A2]. Rock Creek gorge (up to 130 feet deep through NW DC), Anacostia River valley, and the broader Shenandoah Valley system to the west. These are the most reliably and intensely foggy spots in the metro area.

**Advection fog (secondary):** Warm moist air from the Gulf / Chesapeake Bay moves over colder surfaces [A2]. Most relevant in winter months along the Potomac estuary and Chesapeake Bay influence zone. The "Foggy Bottom" neighborhood name directly derives from centuries of this fog type [D8].

**Steam fog (minor):** Cold air over warmer river/reservoir surfaces [A2]. Visible but typically shallow — photographically striking on the Potomac and Rock Creek, but usually insufficient for Dense Fog Advisory-level events.

### Urban Heat Island Effect on Our Map

Research confirms a "fog hole" effect over dense urban cores — the DC urban center is systematically less fog-prone than surrounding suburbs due to the urban heat island (2–5°C warmer than surrounding rural areas) [B9]. Dulles (KIAD) is far more fog-prone than Reagan National (KDCA) for this reason. Our terrain-aware probability map should reflect this gradient: suburban and rural corridors outside the urban core get higher baseline fog weights. The impervious surface fraction derived from NLCD [C9] is the key input for this correction.

### Primary Fog Predictors (Validated by Research)

These are the variables our model will be built on, ordered by importance:

| Variable | Threshold | Source | Why it matters |
|---|---|---|---|
| Dew point depression (T − Td) | ≤ 2°C = possible; ≤ 1°C = likely; > 3°C = unlikely | [A2] [B4] | Most direct saturation indicator. Fog forms when T ≈ Td. |
| Wind speed | 1–3 m/s optimal; > 4–5 m/s suppresses radiation fog | [A2] [B4] | Paradoxical role: some mixing needed, too much breaks the inversion |
| Cloud cover | ≤ 2/8 sky cover required for radiation fog | [A2] | Clouds act as blanket, reduce radiative cooling |
| Relative humidity | ≥ 95% = dense fog possible; ≥ 90% = plausible | [B4] | Mathematical complement of dew point depression |
| Atmospheric stability (inversion) | Surface-based inversion required | [B6] | Stable layer traps cooled moist air near surface |
| Soil moisture (HRRR SOILW) | Relative anomaly vs. climatological mean | [B7] [B8] | Wet soil increases near-surface vapor pressure; shifts onset timing by 30 min – 5 hours |
| Longwave radiation flux | Net negative (outgoing > incoming) | [A2] | Actual driver of surface cooling for radiation fog |
| Synoptic pressure pattern | Anticyclone (+5 hPa anomaly) | [B4] | High pressure promotes clear skies, sinking air, light winds |
| Visibility trend (rate of change) | Rapidly decreasing = imminent dense fog | [B5] [B11] | ML research finds this temporal derivative is among top predictors |

### Terrain Weighting (What Makes This a Discovery Tool)

On top of the atmospheric probability score, we apply static terrain weights derived from our DEM and land cover data:

- **Valley depth**: How much lower the point is than surrounding terrain → cold air pooling potential [B7]
- **Terrain position index (TPI)**: Valley/flat/ridge classification → valleys get higher fog weight [C8]
- **Distance to nearest water body**: Rivers, reservoirs, tidal areas → moisture source proximity
- **Impervious surface fraction (NLCD)**: High impervious = urban heat island → lower fog weight [B9] [C9]
- **Land cover class**: Forest, wetland, open water, agricultural vs. urban — each has distinct surface energy characteristics [C9]

This is what allows us to show meaningful spatial variation *within* a 3km model grid cell: a river valley and a ridge in the same model cell get different probability weights.

### Model Evolution Path

**MVP (Phase 1 validation → Phase 2 app):**
Rule-based weighted heuristic — combine atmospheric conditions into a fog probability index (0–100), then apply terrain weights. Validated against ASOS historical observations before serving to users.

**Phase 2:**
XGBoost or gradient boosted model trained on ASOS fog event labels + HRRR atmospheric features + terrain static features. Literature shows this approach achieves AUC 0.92–0.95 for fog/no-fog classification at airport stations [B10] [B11]. Feature engineering (visibility trend, T-Td spread, stability indicators, time-of-day) matters more than adding exotic data sources [B12].

**Not building (MVP):** Deep learning, ML ensembles, nowcasting from satellite imagery. These are Phase 3+ considerations.

---

## 7. UI/UX

**Core interface: Fog discovery map**

- Mobile-first web app (works in phone browser; no installation)
- Map centered on DC metro area, zoomable
- Fog probability displayed as a spatial overlay — color gradient from low to high probability
- Terrain-aware: river corridors, valley floors, and suburban open land show higher probability than urban core and ridgelines under the same atmospheric conditions [B7] [B9]
- Tap/click any point on the map → hourly fog probability timeline for the next 12–24 hours
- Fog probability displayed as a **Fog Risk Score (1–5)** with a plain-language label, plus relative risk framing (e.g., "3× more likely than a typical morning"). Raw calibrated probability shown as a secondary detail for users who want it.

  | Score | Label | Probability | What it means |
  |---|---|---|---|
  | 1 | Low | < 8% | Near baseline — no real signal |
  | 2 | Moderate | 8–13% | Slightly elevated — possible patchy fog |
  | 3 | High | 13–20% | 2–4× baseline — worth setting an alarm |
  | 4 | Very High | 20–28% | 4–5× baseline — fog likely |
  | 5 | Extreme | 28%+ | Strongest signal the model produces |

  *Thresholds are calibrated to the actual fog base rate (~5.4% of hours in DC metro), not evenly spaced — so "3 out of 5" reflects genuine elevated risk, not an arbitrary midpoint.*

**Key design principles:**
- Honest framing: display is a probability, not a guarantee. The interface should communicate uncertainty, not false precision.
- Discovery-first: the map is the primary screen, not a search box or location picker
- Simplicity: one screen, one question ("where should I go tomorrow morning?")

**UI/UX detail is deferred** to the design phase — this section will expand when we move to frontend implementation.

---

## 8. Success Metrics & North Star

**North Star Metric**

*"Did someone drive somewhere they wouldn't have otherwise, because of this app — and was it worth it?"*

This is the only metric that truly validates the product. If the app changes a photographer's behavior and that behavior produces a result they value, the product works. If it doesn't change behavior, or changes behavior but the fog isn't there, it doesn't matter how technically impressive the model is.

For the personal MVP, this is measured informally: did your husband (or you) actually use it to make a go/no-go decision? Did you go? Was fog there?

**Leading Indicators**

| Metric | What it tells us | How to measure |
|---|---|---|
| Prediction accuracy | Is our fog probability calibrated? | Backtest against ASOS historical observations + forward validation |
| False positive rate | How often did we say "go" and fog wasn't there | Log predictions vs. actual observed conditions at DC metro ASOS stations [C1] |
| False negative rate | How often did fog happen when we said "low probability" | Same method |
| Lift over baseline | Are we better than just checking dew point + wind manually? | Compare model output to simple rule-based baseline (T-Td ≤ 2°C + wind < 5mph) [A2] |

**What "accurate enough" means**

We are not competing with NWS. We are competing with a photographer's current process: checking 2–4 apps, looking at raw humidity and dew point numbers, making a gut call [D6]. If Fogchaser provides meaningfully better signal than that patchwork — even 20–30% improvement in hit rate — it has value.

Accuracy is framed as *probabilistic calibration*, not binary correctness. If we say 70% fog probability and fog appears 65–75% of the time when we say that, we're well-calibrated. That's the goal.

---

## 9. Accuracy & Testing Plan

**Why standard accuracy metrics mislead for fog**

Fog is a rare event. A model that always predicts "no fog" would be correct most of the time — but useless. Standard accuracy (percentage correct) is meaningless for rare events. We use:

- **Precision**: When we predict fog, how often is fog actually there? (Reduces wasted trips)
- **Recall**: When fog actually happens, how often did we predict it? (Reduces missed opportunities)
- **AUC-PR**: Area under the precision-recall curve — the standard metric for imbalanced classification problems like fog prediction [B11]
- **Brier score**: Measures calibration of probability estimates (are our 70% predictions actually right 70% of the time?)

**Testing phases**

*Phase 1 — Historical backtesting (before any app is built)*
- Pull ASOS/METAR records for DC metro stations from IEM [C2] for 2019–2024
- Define fog label: visibility < 1/4 mile OR present weather code = FG [C1]
- Run fog probability model on same-period HRRR atmospheric inputs [A3]
- Measure precision, recall, AUC-PR, Brier score
- Compare against simple baseline: T-Td ≤ 2°C + wind < 5mph = fog likely [A2]
- Gate: we proceed to building the app only if we beat the baseline meaningfully

*Phase 2 — Forward validation (once model is running)*
- Each morning after a prediction night: check actual observed ASOS conditions [C1]
- Log what the model predicted vs. what actually happened
- Track precision/recall over time; update model if systematic errors emerge

*Phase 3 — User validation (once app is being used)*
- Informal log: went out / fog was there / fog wasn't there
- Qualitative: did the app change the decision? was it worth it?

**What we are honest about**

We will communicate that the probability is an estimate, not a guarantee. The app will surface the key conditions driving the score (dew point spread, wind, terrain) so users can apply their own judgment rather than blindly trusting a number.

Fog prediction beyond 6–12 hours has genuinely poor skill in the scientific literature [B1] [B2]. We operate primarily in the 6–18 hour window where skill is highest, and we are transparent about confidence degrading at longer horizons.

---

## 10. What We Are Not Building

**Not in scope — ever (for this product)**
- A safety or navigation tool for pilots, drivers, or transportation (different regulatory and liability space)
- Real-time fog detection / nowcasting (satellite imagery interpretation — a separate problem)
- A general weather app

**Not in scope — MVP; revisit in future phases**
- Sunrise/sunset quality scoring (Phase 2 — clearly the second most valuable feature, well-defined)
- Notifications and alerts
- Multi-city support (DC metro only until the model is validated)
- Native mobile app (web app first)
- User accounts or personalization
- Historical fog data browsing
- Other weather phenomena
- Monetization

**Why these boundaries matter**

Every feature not built in MVP is a deliberate choice to keep the core honest. The fog discovery map is hard enough to do well. Adding features before validating the core model would mean building on an unproven foundation.

---

## 11. Open Questions

These are unresolved at the time of writing. Each needs a decision before or during Phase 1.

1. **Model validation gate**: What specific AUC-PR or precision/recall threshold do we require before building the app? We should define this upfront so we don't rationalize a weak model.

2. ~~**Probability display format**~~ **RESOLVED**: Display a Fog Risk Score (1–5) with a plain-language label prominently, plus relative risk framing ("Nx more likely than a typical morning") as a one-liner. Raw calibrated probability shown as a secondary detail. Score thresholds are calibrated to the actual baseline fog rate (~5.4%), not evenly spaced — see Section 7 for the full table.

3. **Spatial coverage of DC metro**: What's the geographic bounding box? (e.g., 30-mile radius from Capitol, or something more specific to cover the key fog corridors including Dulles, Shenandoah, Chesapeake Bay influence?)

4. **Terrain weighting methodology**: Exactly how do we combine atmospheric probability with terrain weights? Multiplicative? Additive? Needs to be defined in Phase 1.

5. **Fog definition threshold**: Do we define "fog" as visibility < 1/4 mile (Dense Fog Advisory threshold [A1]), < 5/8 mile (FG present weather code), or < 1 mile (common research threshold)? Different thresholds produce different label distributions and model characteristics.

6. **Maryland Mesonet access**: Confirm API access and data terms for research/non-commercial use [C6].

7. **NBM vs. HRRR for served data**: Confirm NBM [A5] provides sufficient temporal resolution and variable depth for our fog probability inputs, or whether we need raw HRRR for certain variables [A3].

8. **Urban heat island correction**: How explicitly do we encode the UHI fog suppression effect [B9] in the terrain weights? (Impervious surface fraction as a continuous downweight, or a discrete urban/suburban/rural classification?)

9. **Phase 1 timeline**: When do we begin model validation? What resources (compute, data storage) does that require?

---

## 12. Bibliography

Sources are organized by category. Inline markers throughout the document reference these entries.

---

### [A] NOAA / NWS Official Resources

**[A1]** National Weather Service. *Dense Fog Advisory — Fog Safety*.
https://www.weather.gov/safety/fog-ww

**[A2]** National Weather Service, Houston/Galveston Office. *Fog Forecasting Guide* (ZHU Training Page).
https://www.weather.gov/media/zhu/ZHU_Training_Page/fog_stuff/fog_guide/fog.pdf
*(Includes fog type definitions, predictor thresholds, and forecasting methodology.)*

**[A3]** NOAA Global Systems Laboratory. *High-Resolution Rapid Refresh (HRRR) Model*.
https://rapidrefresh.noaa.gov/hrrr/
*(Includes variable inventory, spatial/temporal resolution specs, and access documentation.)*

**[A4]** NOAA Cooperative Institute for Research in Environmental Sciences. *Stratiform Cloud-Hydrometeor Assimilation for HRRR and RAP Model Short-Range Weather Prediction*.
https://repository.library.noaa.gov/view/noaa/31766

**[A5]** NOAA Meteorological Development Laboratory. *National Blend of Models (NBM)*.
https://vlab.noaa.gov/web/mdl/nbm
AWS Open Data Registry: https://registry.opendata.aws/noaa-nbm/

**[A6]** NOAA / NCEP. *HRRR GRIB2 Variable Table (HRRRv4 2D Surface Fields)*.
https://rapidrefresh.noaa.gov/hrrr/GRIB2Table_hrrrncep_2d.txt
*(Complete listing of HRRR output variables including SOILW, HPBL, CLWMR, VIS, etc.)*

**[A7]** NOAA Meteorological Development Laboratory. *National Digital Forecast Database (NDFD)*.
https://www.ncei.noaa.gov/products/weather-climate-models/national-digital-forecast-database

**[A8]** NOAA Global Systems Laboratory. *HRRR-Cast: AI-Powered Regional Model Upgrades (2025)*.
https://gsl.noaa.gov/news/new-upgrades-to-hrrr-cast-noaas-experimental-ai-powered-regional-model

**[A9]** National Weather Service, Baltimore/Washington Forecast Office (LWX).
https://www.weather.gov/lwx/

**[A10]** National Weather Service. *Radiation Fog*.
https://www.weather.gov/safety/fog-radiation

**[A11]** National Weather Service. *Advection Fog*.
https://www.weather.gov/safety/fog-advection

**[A12]** National Weather Service. *Mountain and Valley Fog*.
https://www.weather.gov/safety/fog-mountain-valley

---

### [B] Academic Research Papers

**[B1]** Ghirardelli, J.E. and Glahn, B. (2010). *Forecast of Low Visibility and Fog from NCEP: Current Status and Efforts*. International Fog and Dew Workshop (FOGDEW 2010).
https://meetingorganizer.copernicus.org/FOGDEW2010/FOGDEW2010-57-8.pdf
*(Key finding: NWP fog forecast performance "still poor in comparison to precipitation forecasts"; positive bias of up to 300% for shallow fog.)*

**[B2]** Gultepe, I. et al. (2023). *Fog Decision Support Systems: A Review*. MDPI Atmosphere, 14(8), 1314.
https://www.mdpi.com/2073-4433/14/8/1314
*(Reviews forecast skill horizons; confirms skill degrades substantially beyond 6 hours.)*

**[B3]** Sims, A.L. et al. (2017). *A LAMP–HRRR MELD for Improved Aviation Guidance*. Weather and Forecasting, 32(2).
https://journals.ametsoc.org/view/journals/wefo/32/2/waf-d-16-0127_1.xml
*(Shows post-processed HRRR blends outperform raw HRRR for ceiling and visibility.)*

**[B4]** Lakra, K. and Avishek, K. (2022). *A Review on Factors Influencing Fog Formation, Classification, Forecasting, Detection and Impacts*. Rendiconti Lincei. PMC Open Access.
https://pmc.ncbi.nlm.nih.gov/articles/PMC8918085/
*(Comprehensive review of 250+ papers; covers predictor thresholds, fog types, and multivariate nature of fog.)*

**[B5]** Schütz, N. et al. (2024). *Improving Classification-Based Nowcasting of Radiation Fog with Machine Learning*. Quarterly Journal of the Royal Meteorological Society.
https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4619
*(XGBoost models identify visibility trend, current visibility, RH trend, and T-Td spread as top predictors.)*

**[B6]** Beal, L. et al. (2024). *Evaluation of Near-Surface and Boundary-Layer Meteorological Conditions That Support Cold-Fog Formation*. Quarterly Journal of the Royal Meteorological Society.
https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4818
*(Identifies boundary layer humidity distribution as key differentiator between fog and non-fog cases.)*

**[B7]** Morichetti, M. et al. (2023). *Investigating Multiscale Meteorological Controls and Impact of Soil Moisture Heterogeneity on Radiation Fog in Complex Terrain*. Atmospheric Chemistry and Physics, 23, 14451–14476.
https://acp.copernicus.org/articles/23/14451/2023/
*(Shows soil moisture variability at sub-kilometer scale drives spatial heterogeneity of radiation fog; soil moisture shifts onset timing by 30 min – 5 hours.)*

**[B8]** Zhang, X. et al. (2025). *Improving Fog Simulation: The Role of Soil Moisture Constraint*. ScienceDirect / Atmospheric Research.
https://www.sciencedirect.com/science/article/abs/pii/S0169809525002248
*(Confirms soil moisture nudging "critically influences fog predictability" in NWP models.)*

**[B9]** Klemm, O. and Lin, N.H. (2020). *To What Extents Do Urbanization and Air Pollution Affect Fog?* Atmospheric Chemistry and Physics, 20, 5559–5584.
https://acp.copernicus.org/articles/20/5559/2020/
*(Documents "fog hole" effect over urban cores; urbanization inhibits low-level fog, delays formation, and advances dissipation.)*

**[B10]** Aggarwal, A. et al. (2024). *Short-Term Fog Forecasting at North India Airports Using ML*. ACM Conference.
https://dl.acm.org/doi/10.1145/3632410.3632449
*(ASOS METAR visibility used as fog label; demonstrates ML feasibility for regional airport fog.)*

**[B11]** Gutierrez-Antuñano, M.A. et al. (2025). *Geographic Transferability of Machine Learning Models for Airport Fog Forecasting*. arXiv:2510.21819.
https://arxiv.org/abs/2510.21819
*(XGBoost on ASOS + NWP features achieves AUC 0.923–0.947 across multiple airports and fog regimes. Visibility persistence identified as top SHAP feature.)*

**[B12]** Gutierrez-Antuñano et al. (2023). *Efficient Prediction of Fog-Related Low-Visibility Events with Machine Learning*. ScienceDirect / Atmospheric Research.
https://www.sciencedirect.com/science/article/pii/S0169809523003885
*(Demonstrates that physical feature engineering matters more than adding exotic data sources; NO2 identified as underappreciated predictor.)*

**[B13]** Gao, S. et al. (2024). *Enhanced Oceanic Fog Nowcasting via Recurrent Neural Networks*. International Journal of Digital Earth / Tandfonline.
https://www.tandfonline.com/doi/full/10.1080/20964471.2024.2412379
*(GOES-16 + RNN achieves POD 0.75 at 2-hour nowcast horizon; useful for 0–6h but not 12–24h forecasting.)*

**[B14]** Benjamin, S.G. et al. (2022). *The HRRR: An Hourly Updating Convection-Allowing Forecast Model. Part I: System Description*. Weather and Forecasting, 37(8).
https://journals.ametsoc.org/view/journals/wefo/37/8/WAF-D-21-0151.1.xml

**[B15]** Benjamin, S.G. et al. (2022). *The HRRR: An Hourly Updating Convection-Allowing Forecast Model. Part II: Forecast Performance*. Weather and Forecasting, 37(8).
https://journals.ametsoc.org/view/journals/wefo/37/8/WAF-D-21-0130.1.xml

**[B16]** Gutierrez, M. et al. (2025). *Artificial Intelligence-Based Methods and Algorithms in Fog and Atmospheric Low-Visibility Forecasting: A Review*. MDPI Atmosphere, 16(9), 1073.
https://www.mdpi.com/2073-4433/16/9/1073
*(Comprehensive 2025 review of the state of AI/ML in fog prediction; best-performing data stack synthesis.)*

**[B17]** Li, J. et al. (2024). *Effects of Surface Moisture Flux on the Formation of Cold Fog over Complex Terrain*. Quarterly Journal of the Royal Meteorological Society.
https://rmets.onlinelibrary.wiley.com/doi/full/10.1002/qj.4748

**[B18]** Kuchera, E.L. et al. (2025). *Heavy Fog Forecasting with Machine Learning*. Nature Scientific Reports.
https://www.nature.com/articles/s41598-025-28811-y

**[B19]** ECMWF. *Visibility Forecast — User Guide, Section 9.4*.
https://confluence.ecmwf.int/display/FUG/Section+9.4+Visibility
*(Documents NWP limitations for fog at sub-grid scales; radiation fog timing biases.)*

---

### [C] Data Sources & Access Tools

**[C1]** Federal Aviation Administration. *Automated Surface Observing Systems (ASOS)*.
https://www.faa.gov/air_traffic/weather/asos
*(Station locations, variable definitions, visibility reporting increments.)*

**[C2]** Iowa Environmental Mesonet (IEM). *ASOS Historical Download*.
https://mesonet.agron.iastate.edu/request/download.phtml
*(Free CSV download of all US ASOS stations back to ~1995; no registration required.)*

**[C3]** NOAA / NCEI. *Integrated Surface Database (ISD)*.
https://www.ncei.noaa.gov/products/land-based-station/integrated-surface-database
AWS Open Data: https://registry.opendata.aws/noaa-isd/

**[C4]** Blaylock, B.K. *Herbie: Python Package for HRRR and Other NWP Model Data*.
https://herbie.readthedocs.io/
GitHub: https://github.com/blaylockbk/Herbie
*(Handles GRIB2 byte-range requests, model selection, and geographic subsetting for HRRR, NBM, and other NOAA models.)*

**[C5]** AWS Open Data Registry. *NOAA National Blend of Models (NBM)*.
https://registry.opendata.aws/noaa-nbm/

**[C6]** University of Maryland. *Maryland Mesonet*.
https://mesonet.umd.edu/
Related research: Coniglio, M.C. et al. (2024). *Optimizing NWP Utility of Maryland Mesonet Observations*. Weather and Forecasting, 39(12).
https://journals.ametsoc.org/view/journals/wefo/39/12/WAF-D-24-0089.1.xml

**[C7]** Synoptic Data. *Weather API (includes RWIS, mesonet, and ASOS networks)*.
https://synopticdata.com/weatherapi/
*(Free research tier; aggregates 170,000+ stations across 320+ networks.)*

**[C8]** USGS. *3D Elevation Program (3DEP) — 1-Meter DEM*.
https://data.usgs.gov/datacatalog/data/USGS:77ae0551-c61e-4979-aedd-d797abdcde0e
Download portal: https://apps.nationalmap.gov/downloader

**[C9]** USGS / MRLC. *National Land Cover Database (NLCD)*.
https://www.mrlc.gov/data
https://www.usgs.gov/centers/eros/science/national-land-cover-database

**[C10]** NOAA. *GOES-16/17/18 Advanced Baseline Imager (ABI) on AWS*.
https://registry.opendata.aws/noaa-goes/
CIMSS Fog Product documentation: https://cimss.ssec.wisc.edu/csppgeo/includes/documents/GOESR_FLS_EUM.pdf

**[C11]** ECMWF. *ERA5 Reanalysis — Copernicus Climate Data Store*.
https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=overview
Documentation: https://confluence.ecmwf.int/display/CKB/ERA5:+data+documentation

**[C12]** NOAA / MDL. *LAMP (Localized Aviation MOS Program)*.
*(Statistical post-processing of HRRR for aviation ceiling/visibility; referenced in B3.)*
https://vlab.noaa.gov/web/mdl/lamp

---

### [D] Industry & Community Sources

**[D1]** Viewfindr. *Fog Forecasting for Photographers*.
https://viewfindr.net/photographing-fog/
Fog Height product: https://viewfindr.net/weather/fog-height/
*(European-focused; claims ~80% forecast accuracy; developed with meteorologists.)*

**[D2]** PhotoHound. *Predicting Fog with the PhotoHound App*.
https://www.photohound.co/articles/photohound-app-predicting-fog/

**[D3]** Clear Outside. *Weather Forecasting App for Astronomers and Photographers*.
https://clearoutside.com/

**[D4]** Fstoppers. *Why Weather Apps Are Not Accurate Enough for Landscape Photography*.
https://fstoppers.com/landscapes/why-weather-apps-are-not-accurate-enough-my-landscape-photography-591215
*(Argues fog events can be confined to 10×10km areas; apps fail to resolve at this scale.)*

**[D5]** Windy Community. *Fog and Forecasted Fog — Documentation Thread*.
https://community.windy.com/topic/8455/fog-and-forecasted-fog
*(Windy's own documentation: fog overlay "only indicates a relative possibility.")*

**[D6]** Talk Photography Forum. *Photography in the Mist — Apps/Tools for Fog/Mist Forecasting*.
https://www.talkphotography.co.uk/threads/photography-in-the-mist-any-useful-apps-tools-for-fog-mist-forecasting.703371/
*(Documents photographer multi-app workflow; "all apps and websites are poor now" for fog prediction.)*

**[D7]** Location Scout. *Forecasting Fog for Landscape Photography*.
https://www.locationscout.net/articles/27-forecasting-fog-for-landscape-photography

**[D8]** Wikipedia. *Foggy Bottom*.
https://en.wikipedia.org/wiki/Foggy_Bottom
*(Historical documentation of centuries of fog in DC's low-lying riverside neighborhood.)*

**[D9]** The Baltimore Banner. *Why Does It Seem Foggier Along the Chesapeake Bay?*
https://www.thebanner.com/opinion/column/chesapeake-bay-bridge-fog-maryland-DW3DIT3MQRFNRJUOPX2B4XCHZM/

**[D10]** Travel Photography Magazine. *Forecasting the Fog: Using Weather Apps to Plan Atmospheric Photo Shoots*.
https://travelphotographymagazine.com/forecasting-the-fog-using-weather-apps-to-plan-atmospheric-photo-shoots/gear/

**[D11]** aows.co. *How I Predict Fog (Photography Workflow Blog)*.
https://aows.co/blog/2021/10/28/how-i-predict-fog
