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
```
