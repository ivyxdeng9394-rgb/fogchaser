# Fogchaser UI Redesign Plan
**Date:** 2026-03-07
**Status:** Awaiting approval before implementation

---

## My design read on where we are

The current UI is functional but it's doing something quietly wrong: it's presenting fog as a weather-monitoring tool when it should feel like a photography planning tool. Those are different things. A weather app shows you what's happening. A shoot-planning tool helps you make a decision: go or no-go. Every UI choice should serve the go/no-go decision for a photographer who has 30 seconds to check their phone at 9pm before deciding whether to set a 4am alarm.

Right now, the UI leads with a map. That's correct — spatial distribution is the whole differentiator here. But the map doesn't answer the primary question fast enough. The overnight summary badge is tiny text in the header. The click interaction requires a tap that has no feedback. The time controls show UTC. None of that is designed around the photographer's actual moment of use.

The NYT map you referenced is beautiful but it's the wrong reference for our data type. Their map is discrete neighborhood polygons — hard-edged because each polygon is a defined area. Our fog data is a continuous raster: probabilities blend smoothly across space because that's how atmosphere actually works. Trying to add hard neighborhood borders to our overlay would create false precision — implying "fog stops at the DC/Maryland border" when the model doesn't know that. The right goal is high contrast and readability, not NYT polygon aesthetics.

---

## What I agree with and why

### 1. Local time + relative hours (+1h, +2h)

**Recommended.** UTC is wrong for this audience — not just inconvenient, actually wrong. A photographer in DC at 9pm doesn't think in UTC. The decision question is "will it be foggy at 5am tomorrow?" not "at 09:00 UTC." The exposure strip cells should show "+1h", "+2h" so the user sees the forecast horizon, not clock arithmetic.

One nuance: show local time in the hour label ("Fri 5:00 AM · +8h from now"), not just "+8h" alone. "+8h" without an anchor time is disorienting — people can't easily add 8 to their current time in their head.

**Complexity:** Low.

---

### 2. Mobile bottom sheet instead of floating panel

**Strongly recommended, and I'd go further than you described.**

The floating panel isn't just annoying — it's architecturally wrong for mobile. Tapping the map to learn about a spot and then having a box appear *on top of the map* forces users to mentally hold two things at once: where they tapped and what the box says. The map becomes unusable while the box is open.

The right pattern for mobile is a **bottom sheet with two states**:
- **Peek state** (visible by default once data loads): A thin 48px handle at the bottom showing "Fog tonight: 3/5 — High · 2.3× above normal." Always visible, doesn't block the map.
- **Tap-to-expand**: Tapping anywhere on the peek bar expands to a half-screen panel with score, location name, probability details, and eventually contributing factors.
- **Tap the map to probe**: Tapping the map updates the peek bar content for that location and hour.

This means the map is always explorable. Information lives below the fold but is always one tap away.

On desktop, the current left-panel approach is fine. Make it responsive.

**One thing I'd push back on:** You said "something that expands." I'd caution against a full-screen modal expand — that removes the map entirely, which breaks the spatial context. Half-screen bottom sheet keeps both visible.

**Complexity:** Medium.

---

### 3. Location name via reverse geocoding

**Recommended with reservations.**

Showing "Arlington, VA" instead of coordinates is clearly better. But I want to flag a real-world issue: Nominatim (OpenStreetMap's reverse geocoder) can return confusing results. At zoom level 10 over the Potomac corridor, it might return "unnamed road" or a very generic county name rather than a useful neighborhood. The closer you zoom, the more useful the result.

My recommendation: **show the nearest weather station as the primary anchor** ("Near IAD — Dulles Corridor"), with the Nominatim city/suburb as secondary. The 8 stations are exactly the locations the model is most reliable — naming them gives users a useful anchor ("IAD area = more fog-prone than DCA"). Nominatim is a bonus layer, not the primary anchor.

Also: rate-limit aggressively. Cache results by rounded lat/lon (0.01 degree precision). One bad batch of taps shouldn't trigger 20 API calls.

**Complexity:** Low-Medium.

---

### 4. Visual differentiation on the map

**Here's where I'd push back on the NYT comparison.**

The NYT polygon borders work because their data *is* polygons. Our fog data is a continuous raster — the values blend across space. Adding fake hard borders between fog zones would be misleading. It would imply the model has neighborhood-level precision that it doesn't have (500m resolution with terrain weighting, not parcel-level).

What we *can* do that genuinely improves readability:

1. **Switch to CartoDB Dark Matter base tiles** — dark background, white street labels. This makes the blue fog overlay dramatically more readable and lets you see neighborhood names at zoom 13+. This is the single highest-ROI change on the list.

2. **Boost the overlay opacity curve** — the current ramp has too shallow a gradient between Low (barely visible) and Moderate. Bump Low opacity from 0.25 to 0.35, Moderate from 0.42 to 0.55. Make the visual difference between score levels unmissable.

3. **Increase GeoRaster resolution** from 256 to 512. Reduces the "blocky tile" appearance when zoomed in.

4. **Don't add contour borders.** I know it looks compelling in the NYT reference, but it would be technically deceptive for our continuous raster data. The fog gradient is the truth — discrete borders would be a lie dressed up nicely.

**Complexity:** Low (tile swap + opacity tweak).

---

### 5. Brand color: dark gray gradient, font: Inter

**Partially agree.**

Inter is the right call for UI text. It's designed for screen readability, renders well at small sizes on mobile, has excellent numerics. I'd keep IBM Plex Mono for the data values (probability numbers, times) — monospaced numbers don't cause layout shift as values change.

On the gradient: I'd keep it subtle. The near-black background is actually working well because it makes the map the visual star and the fog overlay colors pop. Going lighter risks making the chrome compete with the map. My suggestion: `#111316` background with a very gentle gradient to `#0d1014` — warm dark gray, not "TV off black," but not noticeably lighter than current.

Where I'd add the gradient: the **header only**, with a slightly lighter surface that grades downward into the map. Creates a sense of layering — the header "floats" above the map.

**Complexity:** Low.

---

### 6. ASOS note

**Agree with moving it.** "ASOS data approximated" is meteorology jargon that means nothing to a photographer. The current placement — as the last thing in the click panel — reads like a legal disclaimer.

Better: a small ⚠ indicator on affected exposure-strip cells (hours 2–12). Users who care can tap it. The explanation should be plain English: "After the first hour, we estimate current conditions using the weather model instead of live sensor readings. Accuracy is slightly lower." That's it.

**Already fixed** in the current code — the note now only shows on relevant hours and the text is rewritten.

---

## Phase 2 — My priorities, which differ from Ivy's ordering

### 7. Contributing factors — I'd prioritize this higher

You listed this as Phase 2 because it requires pipeline changes. I agree on the sequencing, but I think it's the most important feature in the product — not a nice-to-have.

Here's why: every competitor (Windy, Clear Outside, even the Weather Channel) shows fog probability. The thing nobody does is explain *why* in plain English with photography-specific context. "Dew point and air temperature are nearly equal, light winds, and you're in a river valley — conditions are set for radiation fog at dawn" is information a photographer can actually use. It also builds trust: if I tell you why I'm saying 3/5 and you look outside and see those conditions forming, you'll trust the next prediction.

**For the mock data right now:** I can add fake contributing-factors data to the mock manifest so we can design and test the UX pattern before the pipeline is built. That way when we do build the pipeline change, we know exactly what format to emit.

**Recommended pipeline addition to manifest per hour:**
```json
"conditions": {
  "t_td_spread_f": 1.8,
  "wind_speed_mph": 3.2,
  "hpbl_m": 142,
  "hgt_cldbase_m": 380,
  "rh_pct": 94
}
```
The frontend translates these to English using simple rules (T-Td < 2°F → "air near saturation," wind < 5mph → "calm — fog can settle," etc.)

### 8. Per-station breakdown — useful, low priority

Showing "DCA: 2/5 · IAD: 4/5" gives photographers a reason to drive west toward Dulles instead of staying in the urban core. Genuinely useful. But it's second tier — the contributing factors explanation builds trust first, station-level breakdown adds spatial decision support second.

---

## What I'd add that wasn't in Ivy's notes

### 9. Stronger overnight summary — the primary decision surface

The photographer's question is binary: **go or no-go for tomorrow morning.** Right now that answer is buried in a small badge in the header.

I'd add a **single-question answer** prominently displayed when the user opens the app: a full-width card below the notice strip that says:

> **Tomorrow morning (5–7 AM)**
> **Moderate fog · 2/5 · 1.8× above normal**
> Best window: 05:00–06:30 · Dulles corridor most likely

This disappears once the user starts interacting with the map (or can be dismissed). It front-loads the go/no-go answer. If the answer is "Low — nothing to see," users can go back to sleep without opening the map at all.

This requires no pipeline changes — all the data is already in the manifest.

### 10. Color legend on map

Currently there's no legend explaining what the blue shades mean. A small, minimal legend (3 rows: faint = Low, medium = Moderate, saturated = High/Very High) anchored to the top-right of the map would help new users orient.

---

## Summary table

| # | Change | Phase | My priority | Complexity |
|---|--------|-------|-------------|------------|
| 1 | Local time + "+Nh" | 1 | High | Low |
| 2 | Bottom sheet UX | 1 | High | Medium |
| 3 | Location name | 1 | Medium | Low-Med |
| 4 | Dark tile + opacity boost | 1 | High | Low |
| 5 | Inter font + brand colors | 1 | Low | Low |
| 6 | ASOS note cleanup | 1 | Done | Done |
| 7 | Contributing factors | 2 | **Highest** | Med (pipeline) |
| 8 | Per-station breakdown | 2 | Medium | Low (pipeline) |
| 9 | Overnight summary card | 1 | **High** | Low |
| 10 | Color legend | 1 | Medium | Low |

---

## What I'd defer or cut

**Vector contour borders on the fog overlay:** Looks good in the NYT reference. Wrong for our continuous raster data. Would imply false precision. Cut.

**Search box:** PRD is explicit — discovery-first, not search. The map IS the search. Adding a box changes the mental model toward "weather lookup" instead of "where should I go?" Defer indefinitely.

**24-hour forecast:** Model skill degrades past 12 hours. Showing more hours would create false confidence. The 12-hour window is the right call — not a limitation to overcome but an honest boundary.
