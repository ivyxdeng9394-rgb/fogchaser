# Fogchaser

A mobile-first fog prediction tool for the DC metro area, built for photographers who want to plan shoots around fog windows.

**Live app:** [fogchaser.vercel.app](https://fogchaser.vercel.app)

---

## What It Does

Fogchaser answers the question: *where* is fog most likely to form in the next 12 hours, and why?

Instead of a simple yes/no forecast, the app renders a live probability map of the entire DC metro region at 500m resolution — updated hourly using the NOAA HRRR weather model and real-time airport observations. Tap any location on the map to see what's driving the fog risk there: atmospheric conditions, terrain effects, and the underlying model confidence.

---

## How It Works

The pipeline runs in three stages:

**1. Machine Learning Model**
An XGBoost classifier trained on 6 years of hourly ASOS weather observations (2018–2023) paired with HRRR atmospheric reanalysis data. It predicts fog probability for 8 DC-area airport stations using features like dew point spread, boundary layer height, cloud base height, wind speed, and relative humidity.

- AUC-PR: **0.357** (6.6× better than a random baseline)
- Platt-calibrated probabilities, F2-optimized threshold at 0.17
- Recall 72%, Precision 36% at threshold

**2. Spatial Interpolation Layer**
The 8 airport point-predictions get interpolated across ~120,000 grid cells covering the region. This uses Inverse Distance Weighting (IDW) in log-odds space, with a static terrain offset grid layered on top.

The terrain offset encodes four fog-relevant signals derived from USGS elevation and land cover data:
- **Valley depth (TPI):** Cold air pools in valleys → higher fog probability
- **Urban heat island:** Dense impervious surfaces suppress fog → lower probability
- **Surface moisture:** Proximity to rivers, wetlands, reservoirs → higher probability
- **Aspect:** North-facing slopes stay cooler → slightly higher probability

**3. Web App**
A single-page JavaScript app (no framework) renders the GeoTIFF fog maps as a Leaflet overlay. A time slider steps through the next 12 forecast hours. Tapping any location opens a details panel with a 1–5 fog risk score, the atmospheric conditions driving it, and terrain context.

---

## Architecture

```
fogrefresh (shell alias)
    └── scripts/run_live_forecast.py
            ├── fetch_live_asos.py       ← 8 DC airport observations (IEM API)
            ├── fetch_live_hrrr.py       ← NOAA HRRR atmospheric data (Herbie/AWS)
            ├── run_inference_hour.py    ← XGBoost model + Platt calibration
            └── spatial_pipeline.py     ← IDW interpolation + terrain offset → GeoTIFF
                    └── upload_to_r2.py ← GeoTIFFs + manifest.json → Cloudflare R2

Vercel (app)  ←→  Cloudflare R2 (data)
fogchaser.vercel.app       pub-*.r2.dev/manifest.json + fog_prob_*.tif
```

Data updates (GeoTIFFs + manifest) go directly to Cloudflare R2 — no Vercel redeploy needed. App code changes deploy via `vercel --prod`.

---

## Tech Stack

| Layer | Tools |
|---|---|
| ML model | XGBoost, scikit-learn (Platt calibration), pandas, numpy |
| Weather data | Herbie (HRRR via AWS S3), IEM API (ASOS observations) |
| Geospatial | rasterio, pyproj, scipy (IDW interpolation) |
| Terrain data | USGS 3DEP DEM (1m elevation), USGS NLCD (land cover) |
| Frontend | Vanilla JS, Leaflet.js, GeoRaster/geoblaze, SunCalc |
| Hosting | Vercel (app), Cloudflare R2 (forecast data) |
| Testing | pytest |

---

## Model Performance

Evaluated on an October–December 2024 held-out test set of 4,289 hourly observations across 8 DC metro stations (5.4% fog rate):

| Model | AUC-PR | vs. Random |
|---|---|---|
| Rule-based baseline (T–Td ≤ 2°F + wind < 5 mph) | 0.071 | 1.3× |
| NOAA NBM binary forecast | 0.170 | 3.2× |
| XGBoost, ASOS features only | 0.174 | 3.2× |
| NBM soft (inverse visibility) | 0.296 | 5.5× |
| **XGBoost + HRRR, 6-year training (current)** | **0.357** | **6.6×** |

AUC-PR on peak fog season (Oct–Dec eval set) is 0.480 — the model is strongest when fog is most likely.

---

## Running Locally

```bash
# Install Python dependencies
pip install -r requirements.txt

# Generate mock forecast data (no R2 credentials needed)
python3 scripts/generate_mock_forecast.py

# Serve the app locally (must use a server, not file://)
cd app && python3 -m http.server 8080
# Visit http://localhost:8080
```

The app auto-detects `localhost` and loads from `app/data/manifest.json` instead of R2.

**For live data**, copy `.env.example` to `.env` and fill in Cloudflare R2 credentials, then run:

```bash
fogrefresh
```

---

## Project Structure

```
fogchaser/
├── app/                    # Frontend (HTML, CSS, JS)
├── scripts/                # Python pipeline scripts
├── models/                 # Trained XGBoost model + calibrators
├── data/                   # Raw and processed data
├── docs/                   # PRD, spatial layer guide, design notes
├── tests/                  # pytest test suite (spatial layer validation)
└── outputs/                # Calibration curves, experiment logs
```

Key docs:
- `docs/fogchaser-mvp-prd.md` — full product requirements: vision, data sources, modeling approach, success metrics
- `docs/spatial-layer-guide.md` — plain-English walkthrough of the terrain interpolation layer

---

## Known Limitations

- **Static terrain offset** — doesn't adapt between radiation fog (forms in place) and advection fog (rolls in from the Bay). Accepted MVP trade-off.
- **8 airport stations** — all in flat terrain. The model may underestimate fog in deep valleys not near an airport.
- **DC metro only** — no multi-city support yet.
- **500m spatial resolution** — matches terrain data; atmospheric inputs are 3km HRRR cells.

---

## Background

Built as a personal project to explore the intersection of weather modeling, geospatial analysis, and product design. The core question driving the build: *can a small ensemble of point observations, combined with terrain data, produce a meaningful fog probability map?* The answer turned out to be yes — with the right interpolation approach and enough training data.
