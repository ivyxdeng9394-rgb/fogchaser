# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

The project has a working fog prediction pipeline:
- XGBoost + HRRR model: AUC-PR 0.357, 6.6x better than random (6yr full model, 2018–2023)
- Platt-calibrated probabilities + F2 threshold at 0.17 (recall=72%, precision=36%)
- Calibrated probability range: [0.008, 0.252]
- Spatial interpolation layer: IDW in log-odds space + static terrain offset grid → 500m fog probability maps of DC metro
- All code in `scripts/`, tests in `tests/spatial/`

## Project Context

**fogchaser** is a photography-focused tool for understanding and predicting fog conditions. The goal is practical: help a photographer (not a meteorologist) know when and where fog is likely to form, so they can plan shoots. The Claude settings whitelist these domains for research:
- `fogforecast.com` — fog forecast data
- `www.talkphotography.co.uk` — photography community
- `www.photrio.com` — photography community

## How to Work on This Project

**Be factual and validate claims.** This is science-adjacent work. Do not state things as fact unless they are well-established or sourced. Flag uncertainty explicitly — e.g., "this is debated in the literature" or "this assumes X, which may not hold in your local conditions."

**Explain everything in plain English.** The user has no meteorology background. When explaining fog formation, atmospheric conditions, or statistical methods, use analogies and plain language. Avoid jargon without defining it first.

**Highlight risks and uncertainty.** Fog prediction is inherently uncertain. Always be clear about:
- What the model/analysis can and cannot tell us
- Where the data might be unreliable or incomplete
- What assumptions are baked in and when they might break

**When doing statistical modeling, go slow and explain thoroughly:**
- Before choosing an approach, explain what options exist and why one might be better than another for this use case
- Walk through the modeling step by step — don't skip ahead
- Compare approaches extensively: show the trade-offs, not just the winner
- Explain *why* we're doing each step, not just *what* we're doing
- Be steady and predictable — don't rush to a conclusion

## Key Documents

- **Product Requirements Document (PRD):** `docs/fogchaser-mvp-prd.md`
  The PRD covers product vision, target users, competitive landscape, MVP scope, data sources, modeling approach, success metrics, testing plan, and a full bibliography of sources. Read this before starting any work on this project.

- **Spatial Layer Guide:** `docs/spatial-layer-guide.md`
  Plain-English guide to the spatial interpolation layer: what each script does, how to run it, validation results, and implementation gotchas.

## Spatial Layer Gotchas

- **TPI sign:** Raw TPI is positive for ridges, negative for valleys. The terrain offset formula negates TPI so valleys (fog-favoring via cold air pooling) get a positive offset. Do not remove the negation.
- **IDW power is 1.2** (not the textbook default of 1.5 or 2.0). Higher power creates bullseye artifacts around individual stations.
- **Always feed calibrated probabilities** (0.008–0.252 range for the 6yr full model) into the spatial pipeline — not binary 0/1 fog labels. Binary inputs saturate IDW in log-odds space and produce all-blue maps.
- **The terrain offset is static** (does not change by hour or season). It will over-correct on advection fog events. This is an accepted MVP limitation.

## Setup

```
Run tests:                          python3 -m pytest tests/spatial/ -v
Run Phase 1 terrain setup (once):   see docs/spatial-layer-guide.md
Run validation:                     python3 scripts/validate_spatial.py
Refresh forecast data:              fogrefresh
Deploy code changes to Vercel:      vercel --prod   (run from project root)
```

## Deployment Architecture

There are two separate systems. Keep them straight:

**Cloudflare R2** — stores data (updated by `fogrefresh`)
- GeoTIFF fog maps: one per forecast hour, ~1MB each
- `manifest.json`: the index file the app fetches on load
- Public base URL: `https://pub-e433cc0481d6494280712cc9b1e4100e.r2.dev`
- `manifest.json` URL: `https://pub-e433cc0481d6494280712cc9b1e4100e.r2.dev/manifest.json`

**Vercel** — serves the app (HTML/CSS/JS/favicon)
- URL: `https://fogchaser.vercel.app`
- NOT connected to the GitHub repo — must deploy manually with `vercel --prod`
- Only needs redeployment when app code changes (HTML, CSS, JS, vercel.json)
- Data refreshes do NOT require a Vercel redeploy

**GitHub** — source of truth for code only
- `main` branch
- `app/data/manifest.json` is NOT committed to git (manifest lives on R2)
- GitHub Actions is currently blocked on this account — automation is not running

## fogrefresh — What It Does

`fogrefresh` is a shell alias defined in `~/.bash_profile`. It runs `scripts/refresh_forecast.sh`, which does the following in order:

1. Loads R2 credentials from `.env`
2. Runs `scripts/run_live_forecast.py`:
   - Finds the most recent HRRR model run
   - Fetches live ASOS observations from IEM for 8 DC metro stations
   - For each of the next 12 forecast hours (fxx=1–12):
     - Downloads HRRR variables for that hour
     - Runs the XGBoost model → calibrated fog probabilities per station
     - Runs the spatial pipeline (IDW + terrain offset) → GeoTIFF fog map
     - Uploads GeoTIFF to R2
   - Writes `manifest.json` with URLs, scores, labels, and conditions per hour
   - Uploads `manifest.json` to R2 (with `no-cache` header)
3. Done — no git commit, no Vercel deploy needed

**To refresh forecast data:** run `fogrefresh` in terminal from any directory.
**Requires:** `.env` file in project root with R2 credentials. Copy `.env.example` and fill in values from the Cloudflare dashboard. Never commit `.env`.

## Credentials

- **R2 credentials** — stored in `.env` (local) and Cloudflare dashboard. GitHub Secrets cannot be read back once set — go to Cloudflare to retrieve or recreate.
- **Vercel** — logged in via `vercel` CLI. Run `vercel whoami` to confirm.
- **`.env` template** — see `.env.example` in project root.
