# Planning Panel Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a "Plan this spot" accordion to the tap sheet with lighting times (SunCalc), persistent departure point (localStorage), and one-tap navigation (Google Maps / Apple Maps deep link).

**Architecture:** All changes are client-side in `app/` (index.html, app.js, style.css). SunCalc.js added via CDN. Departure point stored in localStorage — no account, no backend. Accordion pattern: only one of "Plan this spot" / "Why this score" open at a time. CSP already allows unpkg.com and nominatim.openstreetmap.org — no vercel.json changes needed.

**Tech Stack:** Vanilla JS, SunCalc.js 1.9.0 (CDN), Nominatim (existing), Leaflet (existing), CSS transitions

**Design reference:** `docs/plans/2026-03-08-planning-panel-design.md`

**After every task — NON-NEGOTIABLE:**
1. Run the verification step(s) listed in the task.
2. Use `superpowers:verification-before-completion` — confirm the output before claiming it works.
3. If broken: rework until the verification passes. Do NOT commit broken code and move on.
4. Only then commit and proceed to the next task.

---

### Task 1: Add SunCalc.js

**Files:**
- Modify: `app/index.html`

**Step 1: Compute SRI hash**

```bash
curl -s https://unpkg.com/suncalc@1.9.0/suncalc.js | openssl dgst -sha384 -binary | openssl base64 -A
```

Save the output — you'll use it as the `integrity` value.

**Step 2: Add script tag to index.html**

Add after the geoblaze `<script>` tag (line 75), before `<script src="app.js">`:

```html
<script src="https://unpkg.com/suncalc@1.9.0/suncalc.js"
        integrity="sha384-PASTE_HASH_HERE"
        crossorigin="anonymous"></script>
```

Replace `PASTE_HASH_HERE` with the hash from Step 1.

**Step 3: Verify SunCalc loads**

```bash
cd app && python3 -m http.server 8080
```

Open http://localhost:8080. DevTools Console:

```js
SunCalc.getTimes(new Date(), 38.89, -77.03)
```

Expected: object with `sunrise`, `sunset`, `goldenHour`, `nauticalDawn`, etc. No 404 or CSP errors.

**Step 4: Commit**

```bash
git add app/index.html
git commit -m "feat: add SunCalc.js for on-device lighting times"
```

---

### Task 2: Restructure sheet HTML + add departure modal

**Files:**
- Modify: `app/index.html`

**Step 1: Replace #sheet-body**

The existing `#sheet-body` div (lines 53–60 in index.html) currently contains:
```
#prob-value, #prob-label, #why-toggle, #why-factors, #approx-note
```

Replace the ENTIRE `#sheet-body` div with this:

```html
<div id="sheet-body">
  <!-- PRIMARY CTA -->
  <button id="plan-toggle" style="display:none">Plan this spot</button>
  <div id="plan-section" aria-hidden="true">
    <div id="plan-departure">
      <span id="departure-from">From</span>
      <span id="departure-label">Not set</span>
      <button id="departure-edit" aria-label="Edit departure point">Edit</button>
    </div>
    <button id="navigate-btn" disabled>Navigate →</button>
    <div id="lighting-times" aria-live="polite"></div>
  </div>

  <!-- SECONDARY: Score -->
  <div id="score-row">
    <span id="prob-value">—</span>
    <span id="prob-label">—</span>
  </div>

  <!-- WHY THIS SCORE accordion -->
  <button id="why-toggle" style="display:none">Why this score</button>
  <div id="why-factors"></div>
  <div id="approx-note"></div>
</div>
```

**Step 2: Add departure modal HTML**

Add just before `</body>` (after the closing `</div>` of `how-modal`):

```html
<!-- Departure point modal -->
<div id="departure-modal" aria-modal="true" role="dialog" aria-label="Set departure point">
  <div id="departure-backdrop" aria-hidden="true"></div>
  <div id="departure-dialog">
    <div id="departure-header">
      <span id="departure-title">Departure point</span>
      <button id="departure-close" aria-label="Close">✕</button>
    </div>
    <div id="departure-body">
      <p id="departure-hint">Where are you shooting from? Enter a neighborhood, address, or landmark.</p>
      <input type="text" id="departure-input" placeholder="e.g. Silver Spring, MD" autocomplete="off" />
      <div id="departure-error" aria-live="polite"></div>
      <button id="departure-gps-btn">Use my current location</button>
      <button id="departure-save-btn">Save</button>
    </div>
  </div>
</div>
```

**Step 3: Verify HTML structure**

Reload app. Sheet should still open on map tap. No JS errors (existing IDs `why-toggle`, `why-factors`, `approx-note` are unchanged). The sheet may look slightly different since `#prob-value` no longer has large font CSS — that's expected and will be fixed in Task 3.

**Step 4: Commit**

```bash
git add app/index.html
git commit -m "feat: restructure sheet body and add departure modal HTML"
```

---

### Task 3: Style the planning panel

**Files:**
- Modify: `app/style.css`

**Step 1: Replace #prob-value and #prob-label blocks**

Find and replace the existing `#prob-value` block (currently 30px font):

OLD:
```css
#prob-value {
  font-size: 30px;
  font-weight: 600;
  color: var(--accent);
  line-height: 1;
  margin-bottom: 6px;
  letter-spacing: -0.02em;
}

#prob-label {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
  margin-bottom: 14px;
}
```

NEW (score is now secondary):
```css
#score-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 12px 0 4px;
  border-top: 1px solid var(--border);
}

#prob-value {
  font-size: 15px;
  font-weight: 600;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
}

#prob-label {
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.4;
}
```

**Step 2: Add Plan toggle button CSS**

Add after the `#prob-label` block:

```css
/* Plan this spot — primary CTA */
#plan-toggle {
  width: 100%;
  padding: 13px 16px;
  margin: 14px 0 0;
  background: var(--surface2);
  border: 1px solid var(--border2);
  border-radius: 8px;
  color: var(--text);
  font: 500 15px/1 'DM Sans', system-ui, sans-serif;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
  -webkit-tap-highlight-color: transparent;
  position: relative;
}

#plan-toggle::after {
  content: '›';
  position: absolute;
  right: 16px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--accent);
  font-size: 18px;
  line-height: 1;
  transition: transform 0.18s ease;
}

#plan-toggle.expanded {
  border-color: var(--accent);
}

#plan-toggle.expanded::after {
  transform: translateY(-50%) rotate(90deg);
}

#plan-toggle:hover {
  border-color: var(--border2);
  background: #1a1916;
}
```

**Step 3: Add plan section interior CSS**

```css
/* Plan section — slides open under the toggle */
#plan-section {
  display: none;
  flex-direction: column;
  padding: 12px 0 4px;
}

#plan-section.visible { display: flex; }

/* Departure row */
#plan-departure {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 0 10px;
  font-size: 13px;
}

#departure-from {
  color: var(--text-dim);
  flex-shrink: 0;
}

#departure-label {
  flex: 1;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

#departure-edit {
  background: none;
  border: none;
  color: var(--accent);
  font: 400 13px 'DM Sans', system-ui, sans-serif;
  cursor: pointer;
  padding: 4px 0 4px 6px;
  flex-shrink: 0;
  -webkit-tap-highlight-color: transparent;
}

/* Navigate button — primary action, full-width */
#navigate-btn {
  width: 100%;
  padding: 14px 16px;
  background: var(--accent);
  border: none;
  border-radius: 8px;
  color: #0a1a22;
  font: 600 15px/1 'DM Sans', system-ui, sans-serif;
  cursor: pointer;
  transition: opacity 0.15s ease, transform 0.1s ease;
  -webkit-tap-highlight-color: transparent;
  margin-bottom: 14px;
}

#navigate-btn:hover { opacity: 0.88; }
#navigate-btn:active { transform: scale(0.98); }

#navigate-btn:disabled {
  opacity: 0.32;
  cursor: default;
}

/* Lighting times */
#lighting-times {
  display: flex;
  flex-direction: column;
}

.lighting-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 7px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.lighting-row:last-child { border-bottom: none; }

.lighting-label { color: var(--text-muted); }

.lighting-time {
  color: var(--text);
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
```

**Step 4: Verify visually**

Reload app. Tap map. Sheet opens. Score row is now compact (15px, not 30px). "Plan this spot" button still hidden (JS not wired yet). No layout breakage.

**Step 5: Commit**

```bash
git add app/style.css
git commit -m "feat: add planning panel CSS"
```

---

### Task 4: Style the departure modal

**Files:**
- Modify: `app/style.css`

**Step 1: Add departure modal CSS at end of file**

```css
/* ── Departure modal ─────────────────────────────────────────────────────── */

#departure-modal {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 2002;
}

#departure-modal.open { display: block; }

#departure-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  opacity: 0;
  transition: opacity 0.22s ease;
}

#departure-modal.open #departure-backdrop { opacity: 1; }

#departure-dialog {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  background: var(--surface);
  border-radius: 14px 14px 0 0;
  border: 1px solid var(--border2);
  border-bottom: none;
  transform: translateY(100%);
  transition: transform 0.26s cubic-bezier(0.32, 0.72, 0, 1);
  padding: 0 20px calc(28px + env(safe-area-inset-bottom));
  max-height: 60vh;
  overflow-y: auto;
}

#departure-modal.open #departure-dialog { transform: translateY(0); }

#departure-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 0 14px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 18px;
}

#departure-title {
  font: 500 15px/1 'DM Sans', system-ui, sans-serif;
  color: var(--text);
}

#departure-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  -webkit-tap-highlight-color: transparent;
}

#departure-hint {
  font-size: 13px;
  color: var(--text-muted);
  margin-bottom: 12px;
  line-height: 1.5;
}

#departure-input {
  width: 100%;
  padding: 12px 14px;
  background: var(--surface2);
  border: 1px solid var(--border2);
  border-radius: 8px;
  color: var(--text);
  font: 400 14px 'DM Sans', system-ui, sans-serif;
  outline: none;
  margin-bottom: 8px;
  -webkit-appearance: none;
  transition: border-color 0.15s ease;
}

#departure-input:focus { border-color: var(--accent); }
#departure-input::placeholder { color: var(--text-dim); }

#departure-error {
  font-size: 12px;
  color: var(--red);
  min-height: 18px;
  margin-bottom: 6px;
  line-height: 1.4;
}

#departure-gps-btn {
  width: 100%;
  padding: 11px 14px;
  background: none;
  border: 1px solid var(--border2);
  border-radius: 8px;
  color: var(--text-muted);
  font: 400 13px 'DM Sans', system-ui, sans-serif;
  cursor: pointer;
  margin-bottom: 10px;
  -webkit-tap-highlight-color: transparent;
  transition: border-color 0.15s ease, color 0.15s ease;
}

#departure-gps-btn:hover { border-color: var(--accent); color: var(--text); }

#departure-save-btn {
  width: 100%;
  padding: 13px 14px;
  background: var(--accent);
  border: none;
  border-radius: 8px;
  color: #0a1a22;
  font: 600 14px/1 'DM Sans', system-ui, sans-serif;
  cursor: pointer;
  -webkit-tap-highlight-color: transparent;
  transition: opacity 0.15s ease;
}

#departure-save-btn:hover { opacity: 0.88; }
```

**Step 2: Verify modal animation**

In browser console:

```js
document.getElementById('departure-modal').classList.add('open')
```

Modal slides up from bottom. Backdrop darkens. Input and buttons styled correctly. Then:

```js
document.getElementById('departure-modal').classList.remove('open')
```

Modal slides back down. ✓

**Step 3: Commit**

```bash
git add app/style.css
git commit -m "feat: add departure modal CSS"
```

---

### Task 5: Accordion logic

**Files:**
- Modify: `app/app.js`

**Step 1: Replace the existing why-toggle listener**

Find this block in app.js (around line 249):

```js
document.getElementById("why-toggle").addEventListener("click", () => {
  const factorsEl = document.getElementById("why-factors");
  ...
});
```

Replace it entirely with:

```js
// ── Accordion: Plan this spot + Why this score ─────────────────────────────
// Only one section open at a time.

function openPlanSection() {
  document.getElementById("plan-section").classList.add("visible");
  document.getElementById("plan-section").removeAttribute("aria-hidden");
  document.getElementById("plan-toggle").classList.add("expanded");
  // Close why section
  document.getElementById("why-factors").classList.remove("visible");
  document.getElementById("approx-note").classList.remove("visible");
  document.getElementById("why-toggle").classList.remove("expanded");
}

function closePlanSection() {
  document.getElementById("plan-section").classList.remove("visible");
  document.getElementById("plan-section").setAttribute("aria-hidden", "true");
  document.getElementById("plan-toggle").classList.remove("expanded");
}

function openWhySection() {
  const factorsEl = document.getElementById("why-factors");
  const approxEl  = document.getElementById("approx-note");
  factorsEl.classList.add("visible");
  document.getElementById("why-toggle").classList.add("expanded");
  if (approxEl.classList.contains("visible-ready")) {
    approxEl.classList.add("visible");
  }
  // Close plan section
  closePlanSection();
}

function closeWhySection() {
  document.getElementById("why-factors").classList.remove("visible");
  document.getElementById("approx-note").classList.remove("visible");
  document.getElementById("why-toggle").classList.remove("expanded");
}

document.getElementById("plan-toggle").addEventListener("click", () => {
  if (document.getElementById("plan-section").classList.contains("visible")) {
    closePlanSection();
  } else {
    openPlanSection();
  }
});

document.getElementById("why-toggle").addEventListener("click", () => {
  if (document.getElementById("why-factors").classList.contains("visible")) {
    closeWhySection();
  } else {
    openWhySection();
  }
});
```

**Step 2: Update resetExplorer to clear plan state**

Find `resetExplorer()` and replace the entire function:

```js
function resetExplorer() {
  closeSheet();
  if (clickMarker) { map.removeLayer(clickMarker); clickMarker = null; }
  currentClickLatLng = null;
  document.getElementById("sheet-location").textContent = "Tap the map to explore";
  document.getElementById("sheet-score-label").textContent = "";
  document.getElementById("prob-value").textContent = "—";
  document.getElementById("prob-label").textContent = "—";
  // Reset why section
  document.getElementById("why-factors").classList.remove("visible");
  document.getElementById("approx-note").classList.remove("visible", "visible-ready");
  const whyToggleEl = document.getElementById("why-toggle");
  whyToggleEl.style.display = "none";
  whyToggleEl.classList.remove("expanded");
  // Reset plan section
  document.getElementById("plan-toggle").style.display = "none";
  closePlanSection();
  document.getElementById("lighting-times").innerHTML = "";
}
```

Note: `currentClickLatLng` is declared in Task 8 — add `let currentClickLatLng = null;` to the state block (near `let map, currentLayer, manifest;`) now to avoid a reference error.

**Step 3: Verify accordion**

Reload. Tap map. In console:

```js
document.getElementById('plan-toggle').style.display = 'block';
document.getElementById('why-toggle').style.display = 'block';
```

Click "Plan this spot" → plan section opens (empty for now). Click "Why this score" → why opens, plan closes. Click same button again → closes. ✓

**Step 4: Commit**

```bash
git add app/app.js
git commit -m "feat: add accordion logic for plan/why sections"
```

---

### Task 6: Lighting times (SunCalc)

**Files:**
- Modify: `app/app.js`

**Step 1: Add `formatET` helper**

Add after the `const ET = "America/New_York";` line:

```js
// Format a JS Date as "5:12a" in Eastern time
function formatET(date) {
  if (!date || isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: ET,
  }).replace(/\s?(AM|PM)/i, m => m.trim()[0].toLowerCase());
}
```

**Step 2: Add `computeLightingTimes` and `renderLightingTimes`**

Add after `formatET`:

```js
// Returns photographer lighting rows for a lat/lon + JS Date
function computeLightingTimes(lat, lon, date) {
  const t = SunCalc.getTimes(date, lat, lon);
  return [
    { label: "Nautical dawn",    time: formatET(t.nauticalDawn) },
    { label: "Civil dawn",       time: formatET(t.dawn) },
    { label: "Sunrise",          time: formatET(t.sunrise) },
    { label: "Golden hour ends", time: formatET(t.goldenHourEnd) },
    { label: "Golden hour",      time: formatET(t.goldenHour) },
    { label: "Sunset",           time: formatET(t.sunset) },
    { label: "Civil dusk",       time: formatET(t.dusk) },
  ];
}

// Render lighting rows into #lighting-times for the given lat/lon + forecast UTC string
function renderLightingTimes(lat, lon, valid_utc) {
  const rows = computeLightingTimes(lat, lon, new Date(valid_utc));
  document.getElementById("lighting-times").innerHTML = rows.map(r => `
    <div class="lighting-row">
      <span class="lighting-label">${r.label}</span>
      <span class="lighting-time">${r.time}</span>
    </div>
  `).join("");
}
```

**Step 3: Verify in console**

Reload. In console:

```js
renderLightingTimes(38.89, -77.03, new Date().toISOString());
document.getElementById('plan-section').classList.add('visible');
```

Expected: 7 lighting rows render in `#plan-section`. Times show as "5:12a" format. ✓

**Step 4: Commit**

```bash
git add app/app.js
git commit -m "feat: add lighting times computation with SunCalc"
```

---

### Task 7: Departure point (localStorage + modal + GPS)

**Files:**
- Modify: `app/app.js`

**Step 1: Add localStorage helpers + renderDeparture**

Add after the `ET` / `formatET` constant block, before the state variables:

```js
// ── Departure point ────────────────────────────────────────────────────────
const DEPARTURE_KEY = "fogchaser_departure";

function getDeparture() {
  try {
    const raw = localStorage.getItem(DEPARTURE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function saveDeparture(label, lat, lon) {
  localStorage.setItem(DEPARTURE_KEY, JSON.stringify({ label, lat, lon }));
}

function renderDeparture() {
  const dep = getDeparture();
  const labelEl = document.getElementById("departure-label");
  const navBtn  = document.getElementById("navigate-btn");
  if (dep) {
    labelEl.textContent = dep.label;
    navBtn.disabled = false;
  } else {
    labelEl.textContent = "Not set";
    navBtn.disabled = true;
  }
}
```

**Step 2: Add departure modal logic inside DOMContentLoaded**

Add inside the `document.addEventListener("DOMContentLoaded", () => { ... })` block, after the how-modal handlers:

```js
  // ── Departure modal ──────────────────────────────────────────────────────
  function openDepartureModal() {
    const dep = getDeparture();
    const input = document.getElementById("departure-input");
    input.value = dep ? dep.label : "";
    document.getElementById("departure-error").textContent = "";
    document.getElementById("departure-modal").classList.add("open");
    setTimeout(() => input.focus(), 320);
  }

  function closeDepartureModal() {
    document.getElementById("departure-modal").classList.remove("open");
  }

  document.getElementById("departure-edit").addEventListener("click", openDepartureModal);
  document.getElementById("departure-close").addEventListener("click", closeDepartureModal);
  document.getElementById("departure-backdrop").addEventListener("click", closeDepartureModal);

  document.getElementById("departure-save-btn").addEventListener("click", async () => {
    const input = document.getElementById("departure-input");
    const query = input.value.trim();
    if (!query) {
      document.getElementById("departure-error").textContent = "Please enter an address.";
      return;
    }
    const saveBtn = document.getElementById("departure-save-btn");
    saveBtn.textContent = "Searching…";
    saveBtn.disabled = true;
    document.getElementById("departure-error").textContent = "";
    try {
      const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(query)}&format=json&limit=1&accept-language=en`;
      const r = await fetch(url);
      const results = await r.json();
      if (!results.length) {
        document.getElementById("departure-error").textContent = "Address not found. Try being more specific.";
        return;
      }
      const { lat, lon } = results[0];
      saveDeparture(query, parseFloat(lat), parseFloat(lon));
      renderDeparture();
      closeDepartureModal();
    } catch {
      document.getElementById("departure-error").textContent = "Search failed. Check your connection.";
    } finally {
      saveBtn.textContent = "Save";
      saveBtn.disabled = false;
    }
  });

  document.getElementById("departure-gps-btn").addEventListener("click", () => {
    const btn = document.getElementById("departure-gps-btn");
    btn.textContent = "Getting location…";
    btn.disabled = true;
    document.getElementById("departure-error").textContent = "";
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        const { latitude: lat, longitude: lon } = pos.coords;
        const name = await reverseGeocode(lat, lon);
        const label = name || `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
        saveDeparture(label, lat, lon);
        renderDeparture();
        closeDepartureModal();
        btn.textContent = "Use my current location";
        btn.disabled = false;
      },
      (err) => {
        document.getElementById("departure-error").textContent =
          err.code === 1 ? "Location access denied. Type an address instead." : "Couldn't get location. Try again.";
        btn.textContent = "Use my current location";
        btn.disabled = false;
      },
      { timeout: 10000 }
    );
  });
```

**Step 3: Verify departure flow**

Reload. In console:

```js
document.getElementById('departure-modal').classList.add('open')
```

Type "Silver Spring, MD", click Save. Modal closes. Then:

```js
getDeparture()
// Expected: { label: "Silver Spring, MD", lat: 38.99..., lon: -77.02... }
```

Reload page. `getDeparture()` still returns the saved value (persists via localStorage). ✓

**Step 4: Commit**

```bash
git add app/app.js
git commit -m "feat: add departure point with localStorage, geocoding, and GPS"
```

---

### Task 8: Navigate button

**Files:**
- Modify: `app/app.js`

**Step 1: Add state variable for current click location**

Find the state block (around line 151):
```js
let map, currentLayer, manifest;
```

Change to:
```js
let map, currentLayer, manifest;
let currentClickLatLng = null; // lat/lon of last map tap — used by navigate button
```

(If you already added this in Task 5 step 2, skip this.)

**Step 2: Add iOS detection + buildNavURL**

Add after `renderDeparture`:

```js
function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function buildNavURL(destLat, destLon) {
  const dep = getDeparture();
  if (!dep) return null;
  if (isIOS()) {
    return `maps://?saddr=${dep.lat},${dep.lon}&daddr=${destLat},${destLon}&dirflg=d`;
  }
  return `https://www.google.com/maps/dir/?api=1&origin=${dep.lat},${dep.lon}&destination=${destLat},${destLon}&travelmode=driving`;
}
```

**Step 3: Wire navigate button in DOMContentLoaded**

Inside the `DOMContentLoaded` block, add:

```js
  document.getElementById("navigate-btn").addEventListener("click", () => {
    if (!currentClickLatLng) return;
    const dep = getDeparture();
    if (!dep) {
      openDepartureModal();
      return;
    }
    const url = buildNavURL(currentClickLatLng.lat, currentClickLatLng.lng);
    if (url) window.open(url, "_blank", "noopener");
  });
```

Note: `openDepartureModal` is declared earlier in the same `DOMContentLoaded` block — this works because both are in the same scope.

**Step 4: Set currentClickLatLng in onMapClick**

In `onMapClick`, add this as the first line of the function body (after `const idx = ...`):

```js
  currentClickLatLng = e.latlng;
```

**Step 5: Verify navigate logic**

Reload. Tap map. In console:

```js
currentClickLatLng  // { lat: 38.xxx, lng: -77.xxx }
buildNavURL(currentClickLatLng.lat, currentClickLatLng.lng)
// If departure set: "https://www.google.com/maps/dir/?api=1&origin=..."
// If not set: null
```

✓

**Step 6: Commit**

```bash
git add app/app.js
git commit -m "feat: add navigate button with iOS/Android deep links"
```

---

### Task 9: Wire planning panel into onMapClick and slider

**Files:**
- Modify: `app/app.js`

**Step 1: Update onMapClick to show the plan toggle and populate the plan section**

In `onMapClick`, find the section that sets `sheet-score-label`, `prob-value`, `prob-label` (around line 547):

```js
  document.getElementById("sheet-score-label").textContent = `${fogScore(prob)}/5`;
  document.getElementById("prob-value").textContent = `${fogScore(prob)}/5 — ${fogLabel(prob)}`;
  const goLabel = [...][fogScore(prob)];
  document.getElementById("prob-label").textContent = goLabel;
```

Add immediately AFTER that block:

```js
  // Show plan toggle and populate
  const planToggleEl = document.getElementById("plan-toggle");
  planToggleEl.style.display = "block";
  renderDeparture();
  renderLightingTimes(e.latlng.lat, e.latlng.lng, h.valid_utc);
```

**Step 2: Update slider handler to refresh lighting times**

In `init()`, inside `slider.addEventListener("input", ...)`, add after `showHour(idx)`:

```js
    // Refresh lighting times if plan section is open and a location is selected
    if (currentClickLatLng && document.getElementById("plan-section").classList.contains("visible")) {
      renderLightingTimes(currentClickLatLng.lat, currentClickLatLng.lng, manifest.hours[idx].valid_utc);
    }
```

**Step 3: Full integration test**

Manual test (use mock data: `python3 scripts/generate_mock_forecast.py` if needed):

1. Reload app with DevTools > Network > Disable Cache checked
2. Tap the map → sheet opens
3. "Plan this spot" button appears → tap it
4. Plan section expands:
   - "From  Not set  Edit" (or stored departure if set)
   - Navigate button (disabled if no departure, enabled if set)
   - 7 lighting time rows
5. Tap [Edit] → departure modal slides up
6. Type "Bethesda, MD" → Save → departure updates, Navigate enables
7. Tap Navigate → new tab opens with Google Maps route (iOS: Apple Maps)
8. Close plan, tap "Why this score" → opens, plan stays closed
9. Slide the hour slider → lighting times update (if plan is open)
10. Tap the X or header title → sheet closes, all state resets
11. Tap map again → clean state, plan toggle hidden until data loads

**Step 4: Commit**

```bash
git add app/app.js
git commit -m "feat: wire planning panel into map click and slider"
```

---

### Task 10: Code simplification

**REQUIRED SUB-SKILL:** Use `simplify` skill before starting this task.

Review all code added in Tasks 1–9 for redundancy, clarity, and maintainability. Focus on:

- `app/app.js` — new functions: `formatET`, `computeLightingTimes`, `renderLightingTimes`, `getDeparture`, `saveDeparture`, `renderDeparture`, `isIOS`, `buildNavURL`, `openPlanSection`, `closePlanSection`, `openWhySection`, `closeWhySection`, and the updated `resetExplorer` / `onMapClick`
- `app/style.css` — new planning panel and departure modal CSS blocks
- `app/index.html` — new HTML for sheet body and departure modal

Things to look for:
- Duplicate `getElementById` calls that could be cached into a variable
- The accordion open/close functions have repetitive DOM lookups — could be tightened
- Any CSS rules that duplicate existing variables or can reuse existing classes

After simplification, reload app and re-run the integration checklist from Task 9 Step 3 to confirm nothing broke.

**Commit:**

```bash
git add app/app.js app/style.css app/index.html
git commit -m "refactor: simplify planning panel code"
```

---

### Task 11: Security check

Review the new code for security issues before shipping. Check each item:

**1. XSS via innerHTML**

`renderLightingTimes` uses `innerHTML` to render lighting rows. The content comes from `computeLightingTimes`, which calls `formatET`, which calls `toLocaleTimeString` — browser API output, not user input. The `.label` strings are hardcoded literals. **Not a risk**, but confirm no user-supplied or manifest-supplied strings flow into these templates.

`onMapClick` sets `factorsEl.innerHTML` for why-bullets — already in existing code, not changed.

**2. localStorage data**

`getDeparture()` reads JSON from localStorage and uses `dep.label` as `textContent` (not innerHTML) — safe. Coordinates `dep.lat` / `dep.lon` are passed into a URL string — confirm they are `parseFloat`-ed before storage (they are, in `saveDeparture`). Verify URL construction:

```js
buildNavURL(currentClickLatLng.lat, currentClickLatLng.lng)
```

Both `currentClickLatLng` values come from Leaflet's `e.latlng` — always numeric. `dep.lat` / `dep.lon` are stored as `parseFloat(...)` — always numeric. Template literal with numeric values cannot inject URL fragments. ✓

**3. Nominatim forward geocode**

The search query is passed through `encodeURIComponent` before being put in the URL. ✓

The response reads `results[0].lat` and `results[0].lon` — passed through `parseFloat` before use. ✓

**4. Geolocation**

No data from `navigator.geolocation` is injected into the DOM as HTML — it flows into `reverseGeocode` (existing function) and then into `textContent`. ✓

**5. `window.open` with user-triggered URL**

`navigate-btn` click only fires from a direct user gesture. `buildNavURL` constructs the URL from `parseFloat` coordinates only — no string concatenation of user input. `noopener` is set. ✓

**If any issue is found:** fix it, re-run the integration checklist, commit with `fix: security — [description]`.

**If no issues found:** note that review was completed, no changes needed. No commit required.

---

### Task 12: Local testing (Ivy reviews before deploy)

**Step 1: Generate fresh mock data**

```bash
python3 scripts/generate_mock_forecast.py
```

**Step 2: Start local server**

```bash
cd app && python3 -m http.server 8080
```

Open http://localhost:8080 with DevTools open, Network > Disable Cache checked.

**Step 3: Test checklist — hand this to Ivy**

Walk through each flow and confirm ✓ or note what's broken:

- [ ] App loads, no console errors
- [ ] Tap map → sheet slides up with location name
- [ ] "Plan this spot" button is visible and prominent
- [ ] Tap "Plan this spot" → section expands with "From  Not set  Edit", disabled Navigate button, 7 lighting rows
- [ ] Lighting times look correct (AM times in the morning, PM times in the evening) for the selected forecast hour
- [ ] Tap [Edit] → departure modal slides up from bottom
- [ ] Type an address (e.g. "Silver Spring, MD") → Save → departure label updates, Navigate button enables
- [ ] Tap [Edit] again → modal shows previously saved address
- [ ] Tap Navigate → new tab opens with Google Maps (or Apple Maps on iPhone) showing a route
- [ ] If no departure set and Navigate tapped → departure modal opens
- [ ] Close plan section → tap "Why this score" → opens, plan section stays closed
- [ ] Slide the hour slider while plan is open → lighting times update
- [ ] Tap ✕ → sheet closes, all state resets
- [ ] Reload → saved departure persists (localStorage)
- [ ] On narrow mobile viewport: sheet doesn't overflow, lighting rows are readable, departure modal fits screen

**Step 4: Fix any issues Ivy finds before proceeding to deploy.**

---

### Task 13: Deploy

**Step 1: Deploy to Vercel**

```bash
vercel --prod
```

**Step 2: Smoke test on live URL**

Open https://fogchaser.vercel.app on mobile and desktop. Quick check:
- Map tap → planning panel works
- Set departure → Navigate opens maps app
- No console errors, no CSP violations

**Step 3: Done** ✓
