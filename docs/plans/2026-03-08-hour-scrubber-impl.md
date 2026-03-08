# Hour Scrubber Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Replace the 44px colored exposure strip + tiny-dot slider with a single compact fat scrubber (~55px total height) that is easy to drag and tap on mobile.

**Architecture:** Three changes in sequence — strip out the old exposure strip (HTML/CSS/JS), restyle the existing `#hour-slider` range input as a fat pill-thumb scrubber, then add a touch handler that maps taps anywhere on the track to the correct hour. The underlying `showHour()` / `updateSliderFill()` / slider `input` event logic is untouched.

**Tech Stack:** HTML, CSS (pseudo-elements for range input thumb/track), vanilla JS (touchstart/touchmove events)

**Design doc:** `docs/plans/2026-03-08-hour-scrubber-design.md`

---

> **Non-negotiable verification rule:** After every task, open the app at `http://localhost:8080` (run `python3 -m http.server 8080` from `app/`) with DevTools open and cache disabled. Confirm the specific behavior for that task before committing. If it's broken, fix it before moving on. Use `superpowers:verification-before-completion` before every commit.

---

### Task 1: Remove the exposure strip

**Files:**
- Modify: `app/index.html`
- Modify: `app/style.css` (lines 189–228)
- Modify: `app/app.js` (functions `buildExposureStrip`, `updateActiveCell`, and their call sites)

**Context:** The exposure strip is a row of 12 colored rectangles (`#exposure-strip` / `.exposure-cell`) that currently sits between the hour label and the range slider. It's being removed entirely. The range slider (`#hour-slider`) and hour label (`#hour-label`) stay. `cellHourLabel()` is used elsewhere in app.js — do NOT remove it.

**Step 1: Remove the HTML element**

In `app/index.html`, inside `#time-bar`, delete this line:
```html
<div id="exposure-strip"></div>
```

The `#time-bar` should then contain only:
```html
<div id="time-bar">
  <label id="hour-label">—</label>
  <input type="range" id="hour-slider" min="0" max="0" value="0" />
</div>
```

**Step 2: Remove the CSS**

In `app/style.css`, delete these blocks entirely (lines ~189–228):
```css
#exposure-strip {
  display: flex;
  gap: 2px;
  margin-bottom: 6px;
}

.exposure-cell {
  flex: 1;
  height: 44px;
  min-width: 0;
  border-radius: 3px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: transform 0.1s ease, border-color 0.12s ease;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  padding-bottom: 6px;
  background: var(--surface2);
  -webkit-tap-highlight-color: transparent;
  touch-action: manipulation;
}

.exposure-cell:hover { border-color: var(--border2); }

.exposure-cell.active {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent);
}

.cell-hour {
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  color: rgba(222, 218, 210, 0.30);
  line-height: 1;
  user-select: none;
}

.exposure-cell.active .cell-hour,
.exposure-cell.fog-hi .cell-hour { color: rgba(222, 218, 210, 0.75); }
```

**Step 3: Remove the JS functions and call sites**

In `app/app.js`:

a) Delete the entire `buildExposureStrip()` function (lines ~494–524):
```js
function buildExposureStrip() { ... }
```

b) Delete the entire `updateActiveCell()` function (lines ~526–530):
```js
function updateActiveCell(idx) { ... }
```

c) Remove the call to `buildExposureStrip()` (currently line ~465). The line directly after the slider setup reads:
```js
buildExposureStrip();
positionSheet(); // re-measure now that exposure strip cells are rendered
```
Remove `buildExposureStrip();` but keep `positionSheet();`.

d) Remove all remaining calls to `updateActiveCell(idx)`:
- In the slider `input` handler (~line 478): remove `updateActiveCell(idx);`
- In `showHour()` (~line 540): remove `updateActiveCell(idx);`

**Step 4: Verify**

Start the local server:
```bash
cd "/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/work/vibe coding/fogchaser/app"
python3 -m http.server 8080
```

Open `http://localhost:8080` with DevTools open and cache disabled.

Expected:
- No colored rectangle strip visible — just a label + thin slider
- Dragging the slider still changes the map and updates the hour label
- No JS errors in console
- `positionSheet()` still runs (sheet appears above the time bar when you tap the map)

**Step 5: Commit**
```bash
git add app/index.html app/style.css app/app.js
git commit -m "refactor: remove exposure strip, leave scrubber as sole time control"
```

---

### Task 2: Restyle slider as fat pill scrubber

**Files:**
- Modify: `app/style.css`

**Context:** The range input (`#hour-slider`) currently has a 3px track and an 18px circle thumb. We're making it a proper fat scrubber: 6px track, 44×24px pill-shaped thumb, full opacity, tick marks, larger touch target. No HTML or JS changes in this task.

**Step 1: Replace the `#hour-slider` and related CSS**

In `app/style.css`, replace the entire `#hour-slider` block and its thumb/track pseudo-element blocks (lines ~230–275) with:

```css
/* ── Hour scrubber ────────────────────────────────────────────────────────── */

#time-bar {
  padding: 10px 16px 14px;
  background: var(--surface);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

#hour-label {
  display: block;
  font-size: 13px;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
  margin-bottom: 10px;
}

#scrubber-wrap {
  position: relative;
  padding: 10px 0;   /* expands touch target above/below the track */
}

#hour-slider {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 6px;
  background: linear-gradient(
    to right,
    var(--accent) var(--slider-fill, 0%),
    rgba(255,255,255,0.18) var(--slider-fill, 0%)
  );
  border-radius: 3px;
  cursor: pointer;
  display: block;
  outline: none;
  border: none;
  position: relative;
  z-index: 1;
}

/* Tick marks — 12 subtle dots evenly spaced along the track */
#hour-ticks {
  display: flex;
  justify-content: space-between;
  padding: 0 22px;   /* align with thumb center at min/max */
  margin-top: 4px;
}

#hour-ticks span {
  display: block;
  width: 1px;
  height: 4px;
  background: rgba(255,255,255,0.18);
  border-radius: 1px;
}

/* Webkit thumb — pill shaped */
#hour-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 44px;
  height: 24px;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 1px 5px rgba(0,0,0,0.5);
  cursor: grab;
  transition: transform 0.1s ease;
}

#hour-slider:active::-webkit-slider-thumb {
  cursor: grabbing;
  transform: scale(1.06);
}

/* Firefox thumb */
#hour-slider::-moz-range-thumb {
  width: 44px;
  height: 24px;
  border-radius: 12px;
  background: #fff;
  border: none;
  box-shadow: 0 1px 5px rgba(0,0,0,0.5);
  cursor: grab;
}

#hour-slider::-moz-range-track {
  height: 6px;
  background: rgba(255,255,255,0.18);
  border-radius: 3px;
}
```

Also remove the existing `#time-bar` and `#hour-label` blocks that appear earlier in the file (lines ~174–187) — they are now consolidated into the block above.

And remove the desktop media query override for `#hour-slider opacity` (lines ~562–567):
```css
@media (min-width: 680px) {
  #hour-slider {
    opacity: 0.35;
    margin-top: 6px;
  }
}
```

**Step 2: Update HTML to add the scrubber wrapper and tick strip**

In `app/index.html`, replace the `#time-bar` content with:

```html
<div id="time-bar">
  <label id="hour-label">—</label>
  <div id="scrubber-wrap">
    <input type="range" id="hour-slider" min="0" max="0" value="0" />
  </div>
  <div id="hour-ticks"></div>
</div>
```

**Step 3: Build tick marks in JS**

In `app/app.js`, inside the `loadManifest` function after `slider.max = manifest.hours.length - 1;` (line ~456), add:

```js
// Build tick marks (one per hour)
const ticksEl = document.getElementById("hour-ticks");
ticksEl.innerHTML = "";
manifest.hours.forEach(() => {
  const s = document.createElement("span");
  ticksEl.appendChild(s);
});
```

**Step 4: Verify**

Reload `http://localhost:8080` (cache disabled).

Expected:
- Pill-shaped white thumb (~44×24px), easy to grab
- 6px tall track, accent color fills left of thumb
- 12 subtle tick marks below the track
- Hour label is slightly larger and readable
- Dragging still works, hour label updates, map cross-fades
- Total time bar height visibly shorter than before (~55px vs old ~110px)
- No JS errors

**Step 5: Commit**
```bash
git add app/index.html app/style.css app/app.js
git commit -m "feat: restyle hour slider as fat pill scrubber with tick marks"
```

---

### Task 3: Touch tap-to-jump + final verify

**Files:**
- Modify: `app/app.js`

**Context:** On mobile, tapping the track (not the thumb) on a native range input does not reliably jump to that position on iOS Safari. We fix this with a `touchstart` listener that maps the touch X position to the nearest hour index and updates the slider. This also makes the scrubber feel more responsive since `touchstart` fires immediately (no 300ms delay).

**Step 1: Add the touch handler**

In `app/app.js`, inside the `DOMContentLoaded` event listener (or right after the slider `input` listener in `loadManifest` is fine — just after the `slider.addEventListener("input", ...)` block), add:

```js
// Mobile tap-to-jump: map touch X position to hour index
slider.addEventListener("touchstart", (e) => {
  const touch = e.touches[0];
  const rect = slider.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (touch.clientX - rect.left) / rect.width));
  const idx = Math.round(ratio * slider.max);
  slider.value = idx;
  updateSliderFill();
  showHour(idx);
  if (currentClickLatLng && document.getElementById("plan-section").classList.contains("visible")) {
    renderLightingTimes(currentClickLatLng.lat, currentClickLatLng.lng, manifest.hours[idx].valid_utc);
  }
}, { passive: true });
```

Note: `{ passive: true }` tells the browser we won't call `preventDefault()`, which allows the page to scroll freely and removes the touch-delay warning. The `touchmove` event on the range input already handles drag — this handler only improves tap accuracy.

**Step 2: Verify on mobile (or mobile emulation in DevTools)**

In Chrome DevTools, enable mobile emulation (toggle device toolbar). Set device to iPhone or similar.

1. Load `http://localhost:8080`
2. Tap the left edge of the scrubber track — map should jump to hour 0
3. Tap the right edge — map should jump to last hour
4. Tap the middle — map should jump to hour 6
5. Drag smoothly left to right — map cross-fades through hours
6. Tap a spot on the map, open "Plan this spot" → drag the scrubber → lighting times update

Expected: all five steps work, no console errors, no scroll hijacking.

**Step 3: Final design check**

On desktop (full browser width):
- Scrubber sits in the bottom bar, looks clean, not too tall
- Pill thumb is visible and drags smoothly

On mobile emulation:
- Bottom bar is clearly shorter than before
- Pill thumb is easy to grab and drag

**Step 4: Commit**
```bash
git add app/app.js
git commit -m "feat: add touch tap-to-jump handler for mobile scrubber"
```

---

### Task 4: Deploy to Vercel

**Step 1: Run final local check**

Confirm the app loads at `http://localhost:8080`, the scrubber works on both desktop and mobile emulation, and there are no console errors.

**Step 2: Deploy**

```bash
cd "/Users/dengzhenhua/Desktop/Desktop - MacBook Pro/work/vibe coding/fogchaser"
vercel --prod
```

Expected output includes a production URL (`https://fogchaser.vercel.app`).

**Step 3: Smoke test on real device**

Open `https://fogchaser.vercel.app` on a phone. Drag the scrubber. Confirm it's easy to grab and scrolls through hours smoothly.
