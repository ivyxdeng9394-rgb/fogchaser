# Planning Panel — Design Doc

**Date:** 2026-03-08
**Status:** Approved
**Author:** Ivy + Claude

---

## Problem

After a user taps a fog spot and sees the score, the next question is: "Is it worth going, and what does that trip look like?" Right now the app gives the fog signal but no path to act on it. The user has to switch to Google Maps, look up sunrise separately, and mentally stitch it together. That friction is the gap this feature closes.

## Goal

Turn the tap sheet into a lightweight planning tool — fog signal + lighting context + one-tap navigation — so a photographer can make a fully-informed go/no-go decision without leaving the app.

This directly serves the North Star metric: did someone go somewhere because of this app?

---

## What We're Building

A "Plan this spot" CTA added to the existing tap sheet, with:

1. **Lighting times** for the tapped location and forecast date (on-device, no API)
2. **Persistent departure point** stored in localStorage, editable, GPS quick-fill option
3. **Navigate button** deep-linking to Google Maps (Android) or Apple Maps (iOS)

---

## Visual Hierarchy

"Plan this spot" is the primary call to action. The fog score is supporting context. This reflects the product goal: the score tells you *whether* to go, the plan tells you *how*.

```
Location name

[ Plan this spot → ]     ← primary CTA, large, high contrast

1/5 — Low · Stay home    ← smaller, secondary
[ Why this score › ]     ← small expandable
```

When "Plan this spot" is expanded:

```
From: [Your Home]                    [Edit]
[ Navigate →                              ]   ← full-width, large tap target

Nautical twilight    5:12a
Civil twilight       5:41a
Sunrise              6:08a
Golden hour ends     6:52a
Golden hour starts   5:59p
Sunset               6:44p
```

---

## Accordion Behavior

"Plan this spot" and "Why this score" are both expandable. Only one can be open at a time (accordion). Opening one closes the other. Keeps the sheet from growing too tall on mobile.

"Plan this spot" is listed first — it's the action, "Why this score" is the detail.

---

## Departure Point

- Stored in `localStorage` — persists across sessions, no server or account needed
- Set once, reused every session
- Editable via [Edit] link in the planning section
- First-time prompt: type an address OR tap "Use my current location" (GPS)
- Address input opens as a small modal overlay (not inline in the sheet) — avoids keyboard-inside-sheet awkwardness on mobile
- GPS option uses browser Geolocation API — prompts permission, auto-fills coordinates as a readable address (reverse geocoded via Nominatim, already in our CSP allowlist)

---

## Lighting Times

- Calculated on-device using **SunCalc.js** (free, no API key, ~7KB)
- Inputs: lat/lon of tapped point + calendar date of the selected forecast hour
- Times shown in Eastern time (America/New_York), same as the rest of the app
- Times update when the user slides to a different forecast hour (date may change)
- Times shown:
  - Nautical twilight (dawn)
  - Civil twilight (dawn)
  - Sunrise
  - Golden hour end (morning)
  - Golden hour start (evening)
  - Sunset
  - Civil twilight (dusk)

---

## Navigate Button

- Detects platform: iOS → Apple Maps deep link, Android/other → Google Maps deep link
- URL format:
  - Google Maps: `https://www.google.com/maps/dir/?api=1&origin={lat,lon}&destination={lat,lon}&travelmode=driving`
  - Apple Maps: `maps://?saddr={lat,lon}&daddr={lat,lon}&dirflg=d`
- Opens in new tab / native app — does not replace the fogchaser session
- If no departure point is set, tapping Navigate prompts the user to set one first

---

## What We Are Not Building (in this phase)

- In-app travel time calculation (requires routing API — future iteration)
- "Other fog spots nearby along this route" (future — Ivy noted this is valuable but needs in-app routing context)
- Notifications or "leave by" alerts
- Saving favorite spots

---

## Libraries

- **SunCalc.js** — sun position and lighting times. MIT license, no API key.
  CDN: `https://unpkg.com/suncalc@1.9.0/suncalc.js`
  CSP: already allows `unpkg.com` in `script-src`

---

## Open Questions (resolved)

- Deep link vs. in-app routing → **deep link** (routing API is cost/complexity not justified at this scale)
- Persistent departure vs. per-session → **persistent** (localStorage, no account needed)
- Departure point UX → **modal overlay** for address input, GPS quick-fill
- Lighting times scope → **times only, no quality scoring** (scoring is future)
