# Hour Scrubber — Design Doc

**Date:** 2026-03-08
**Status:** Approved
**Author:** Ivy + Claude

---

## Problem

The current time bar is ~110px tall and awkward to use on mobile. It stacks three separate elements: a text label, a row of 44px colored rectangles, and a range input with a small 18px thumb. The only reliable drag target is the tiny dot — the rectangles are tappable but don't support scrubbing. The slider dot is hard to hit on mobile.

## Goal

Replace the entire time bar interaction with a single scrubber that is compact, easy to grab on mobile, and supports both tapping-to-jump and dragging-to-scrub smoothly.

---

## What We're Building

A single scrubber component replacing the exposure strip + range slider:

```
6:00 AM — Wednesday
━━━━━━━━━━━━━━━●━━━━━━━━━━━━━━━━━━
```

**Total height: ~55px** (down from ~110px)

### Elements

**Hour label** (`#hour-label`) — already exists, stays. Left-aligned, shows current forecast hour in Eastern time. Becomes the sole text indicator since the rectangles are removed.

**Track** — Full-width, 6px tall, rounded ends. Left of thumb: accent color (`var(--accent)`). Right of thumb: dim (`rgba(255,255,255,0.15)`). 12 subtle tick marks at equal intervals (one per hour) so the hour grid is visible without rectangles.

**Thumb** — Pill shape, 44×24px, white with soft drop shadow. Large enough to grab reliably on mobile. No label on the thumb itself — the hour label above handles that.

### Interactions

- **Drag thumb** — scrubs smoothly through hours; map updates in real time
- **Tap anywhere on track** — jumps to the nearest hour position (no need to land on the thumb)
- **Desktop** — click and drag, or click to jump; same behavior

### What's Removed

- The 44px colored exposure-strip rectangles (`#exposure-strip`, `.exposure-cell`)
- The existing 18px dot-style range slider thumb styling

### What Stays

- `#hour-label` text (already in HTML, just becomes more prominent)
- `#hour-slider` range input (restyled — same element, no HTML change needed)
- All JS logic for `showHour()`, `updateSliderFill()`, slider `input` event — unchanged
- Tap-on-track behavior: native range input already supports click-to-jump on desktop; on mobile, a `touchstart`/`touchmove` handler on the track element maps touch X position to the nearest hour index

---

## Implementation Notes

- Remove `#exposure-strip` from HTML and all related CSS/JS (`buildExposureStrip`, `updateActiveCell`, `.exposure-cell`, `.cell-hour`)
- Restyle `#hour-slider`: increase track height to 6px, replace 18px circle thumb with 44×24px pill via `-webkit-slider-thumb` / `-moz-range-thumb`
- Add tick marks via a CSS `background` repeating-linear-gradient on the track (12 equally spaced marks, 1px wide, subtle)
- Add touch event listener on `#hour-slider` for reliable mobile tap-to-jump (native range input tap behavior is inconsistent across mobile browsers)
- `#time-bar` padding can be reduced now that the strip is gone

---

## Out of Scope

- Fog probability indicators per hour (removed by design decision)
- Animated thumb transitions between hours
- Keyboard left/right arrow support (already works via native range input)
