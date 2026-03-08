# Design: "How It Works" Explainer

**Date:** 2026-03-07
**Status:** Approved

## Goal

Build trust with curious casual users (photographers, not meteorologists) by explaining how fogchaser predicts fog — calm, confident, and brief. Entry is opt-in, never forced.

## Entry Point

A quiet line below the tonight-bar score/text:

```
How does this work →
```

- Color: `#a89e92` (text-muted, same as secondary labels)
- Tapping opens the explainer modal

## The Modal

- **Type:** Full-screen slide-up card (iOS modal pattern)
- **Background:** `#0f0e0c` — matches app palette
- **Animation:** slides up from bottom on open, slides down on close
- **Dismiss:** swipe down OR tap ✕ button top-right
- **Backdrop:** map stays visible but dimmed behind (`rgba(0,0,0,0.5)`)
- **Font:** DM Sans (already loaded)
- **No scroll needed** — content fits one screen on most phones

## Header

- Small fogchaser logo mark (reuse SVG from main header)
- "How it works" title in DM Sans medium
- ✕ close button top-right

## Content — Five Sections

Each section has a thin left accent line (`var(--accent)`) as the only decoration. No bold headers — just flowing text. Generous line spacing.

1. **The pitch**
   "Fogchaser reads live weather data and predicts where fog is likely to form in the next 12 hours — so you can plan your shoot before you're standing in it."

2. **The data**
   "We pull from eight weather stations across DC metro plus a NOAA weather model that forecasts temperature, humidity, and wind at high resolution — updated every hour."

3. **The model**
   "A machine learning model trained on six years of real hourly weather records learned the patterns that reliably precede fog. It outperforms standard weather forecasts on fog specifically."

4. **Why spots differ**
   "Fog doesn't fall evenly. Cold air drains into valleys overnight. We layer terrain data onto the forecast so the map shows where fog is actually likely to pool — not just the regional average."

5. **Honest limits**
   "Fog is genuinely hard to predict. This model is a strong signal, not a guarantee. Use it to make a more informed call, not the only call."

## Footer

A quiet closing line centered at bottom:

```
Built by a photographer, for photographers.
```

Color: `#a89e92`

## Implementation Notes

- All markup lives in `index.html` as a hidden `<div id="how-modal">`
- Styles in `style.css`
- Open/close logic in `app.js` (reuse sheet open/close patterns already in codebase)
- Entry point link inserted as a new line in `#tonight-bar`
- No new files, no new dependencies
