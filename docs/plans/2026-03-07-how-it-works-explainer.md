# How It Works Explainer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a full-screen "How it works" modal that slides up from the tonight-bar, explaining fogchaser's prediction approach in calm, plain English.

**Architecture:** Entry point is a quiet link below the tonight-bar score. Tapping it opens a full-screen slide-up modal (same dark palette as app). All markup in index.html, styles in style.css, open/close logic in app.js. No new files, no new dependencies.

**Tech Stack:** Vanilla HTML/CSS/JS. DM Sans font (already loaded). Reuses existing CSS variables and sheet animation patterns from the info sheet.

---

### Task 1: Add entry point link to tonight-bar

**Files:**
- Modify: `app/index.html` — add link inside `#tonight-bar`

**Step 1: Read the current tonight-bar markup**

```bash
grep -n "tonight" app/index.html
```

**Step 2: Add the entry point link**

Inside `#tonight-bar`, after the existing `<span id="tonight-text">`, add:

```html
<button id="how-link" aria-label="How does this work">How does this work →</button>
```

**Step 3: Verify in browser**

Run local server: `cd app && python3 -m http.server 8080`
Open http://localhost:8080 — you should see "How does this work →" below the tonight score. It will be unstyled for now.

**Step 4: Commit**

```bash
git add app/index.html
git commit -m "feat: add how-it-works entry point to tonight-bar"
```

---

### Task 2: Add modal HTML to index.html

**Files:**
- Modify: `app/index.html` — add modal before closing `</body>`

**Step 1: Add the modal markup**

Before the closing `</body>` tag, add:

```html
<!-- How it works modal -->
<div id="how-modal" aria-modal="true" role="dialog" aria-label="How it works">
  <div id="how-backdrop"></div>
  <div id="how-sheet">
    <div id="how-header">
      <svg width="18" height="18" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <circle cx="16" cy="16" r="11.5" stroke="#dedad2" stroke-width="1.5" fill="none"/>
        <path d="M6 14.5 Q9.5 13 13 14.5 Q16.5 16 20 14.5 Q23.5 13 26 14.5" stroke="#dedad2" stroke-width="1.3" stroke-linecap="round" fill="none" opacity="0.45"/>
        <path d="M5.5 18.5 Q9 17 12.5 18.5 Q16 20 19.5 18.5 Q23 17 26.5 18.5" stroke="#dedad2" stroke-width="1.7" stroke-linecap="round" fill="none" opacity="0.9"/>
      </svg>
      <span id="how-title">How it works</span>
      <button id="how-close" aria-label="Close">✕</button>
    </div>

    <div id="how-body">
      <div class="how-section">
        <div class="how-accent"></div>
        <p>Fogchaser reads live weather data and predicts where fog is likely to form in the next 12 hours — so you can plan your shoot before you're standing in it.</p>
      </div>
      <div class="how-section">
        <div class="how-accent"></div>
        <p>We pull from eight weather stations across DC metro plus a NOAA weather model that forecasts temperature, humidity, and wind at high resolution — updated every hour.</p>
      </div>
      <div class="how-section">
        <div class="how-accent"></div>
        <p>A machine learning model trained on six years of real hourly weather records learned the patterns that reliably precede fog. It outperforms standard weather forecasts on fog specifically.</p>
      </div>
      <div class="how-section">
        <div class="how-accent"></div>
        <p>Fog doesn't fall evenly. Cold air drains into valleys overnight. We layer terrain data onto the forecast so the map shows where fog is actually likely to pool — not just the regional average.</p>
      </div>
      <div class="how-section">
        <div class="how-accent"></div>
        <p>Fog is genuinely hard to predict. This model is a strong signal, not a guarantee. Use it to make a more informed call, not the only call.</p>
      </div>
    </div>

    <div id="how-footer">Built by a photographer, for photographers.</div>
  </div>
</div>
```

**Step 2: Verify markup is valid**

Open http://localhost:8080 — page should load without errors. Modal not visible yet (no styles).

**Step 3: Commit**

```bash
git add app/index.html
git commit -m "feat: add how-it-works modal markup"
```

---

### Task 3: Style the entry point link

**Files:**
- Modify: `app/style.css`

**Step 1: Find the tonight-bar styles**

```bash
grep -n "tonight" app/style.css
```

**Step 2: Add link styles after the tonight-bar block**

```css
#how-link {
  display: block;
  background: none;
  border: none;
  padding: 0;
  margin: 6px auto 0;
  color: var(--text-muted);
  font: 400 11px/1.4 var(--font);
  letter-spacing: 0.02em;
  cursor: pointer;
  opacity: 0.75;
  transition: opacity 0.15s ease;
}
#how-link:hover { opacity: 1; }
```

**Step 3: Verify in browser**

The "How does this work →" text should appear below the tonight score in muted color.

**Step 4: Commit**

```bash
git add app/style.css
git commit -m "feat: style how-it-works entry point link"
```

---

### Task 4: Style the modal

**Files:**
- Modify: `app/style.css` — add modal styles at end of file

**Step 1: Add all modal styles**

```css
/* ── How it works modal ──────────────────────────────────────────────────── */

#how-modal {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 2000;
}
#how-modal.open { display: block; }

#how-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  opacity: 0;
  transition: opacity 0.28s ease;
}
#how-modal.open #how-backdrop { opacity: 1; }

#how-sheet {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  top: 0;
  background: var(--bg);
  display: flex;
  flex-direction: column;
  transform: translateY(100%);
  transition: transform 0.32s cubic-bezier(0.32, 0.72, 0, 1);
  overflow: hidden;
}
#how-modal.open #how-sheet { transform: translateY(0); }

#how-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
#how-title {
  flex: 1;
  font: 500 15px/1 var(--font);
  color: var(--text);
  letter-spacing: 0.01em;
}
#how-close {
  background: none;
  border: none;
  color: var(--text-muted);
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  transition: color 0.15s ease;
}
#how-close:hover { color: var(--text); }

#how-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 20px 20px;
  -webkit-overflow-scrolling: touch;
}

.how-section {
  display: flex;
  gap: 14px;
  padding: 18px 0;
  border-bottom: 1px solid var(--border);
}
.how-section:last-child { border-bottom: none; }

.how-accent {
  flex-shrink: 0;
  width: 2px;
  border-radius: 2px;
  background: var(--accent);
  opacity: 0.6;
  align-self: stretch;
}

.how-section p {
  margin: 0;
  font: 400 14px/1.65 var(--font);
  color: var(--text);
  opacity: 0.88;
}

#how-footer {
  padding: 16px 20px calc(16px + env(safe-area-inset-bottom));
  text-align: center;
  font: 400 12px/1.4 var(--font);
  color: var(--text-muted);
  opacity: 0.6;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
```

**Step 2: Verify in browser**

The modal is still hidden. No visual change expected yet — styles are ready for when JS adds the `.open` class.

**Step 3: Commit**

```bash
git add app/style.css
git commit -m "feat: style how-it-works modal"
```

---

### Task 5: Wire up open/close logic in app.js

**Files:**
- Modify: `app/app.js`

**Step 1: Add open/close functions and event listeners**

At the bottom of `app.js`, before `init()`, add:

```javascript
// ── How it works modal ────────────────────────────────────────────────────────
function openHowModal() {
  document.getElementById("how-modal").classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeHowModal() {
  document.getElementById("how-modal").classList.remove("open");
  document.body.style.overflow = "";
}

document.getElementById("how-link").addEventListener("click", openHowModal);
document.getElementById("how-close").addEventListener("click", closeHowModal);
document.getElementById("how-backdrop").addEventListener("click", closeHowModal);
```

**Step 2: Add swipe-down to dismiss**

Append to the how-modal section:

```javascript
(function () {
  const sheet = document.getElementById("how-sheet");
  let startY = null;

  sheet.addEventListener("touchstart", e => {
    startY = e.touches[0].clientY;
  }, { passive: true });

  sheet.addEventListener("touchend", e => {
    if (startY === null) return;
    const delta = e.changedTouches[0].clientY - startY;
    if (delta > 60) closeHowModal();
    startY = null;
  }, { passive: true });
})();
```

**Step 3: Verify in browser (full flow)**

- Tap "How does this work →" — modal slides up smoothly
- Tap ✕ — modal slides down
- Tap backdrop — modal slides down
- Swipe down on modal — modal slides down
- All five sections visible with accent lines
- Footer text at bottom
- No console errors

**Step 4: Commit**

```bash
git add app/app.js
git commit -m "feat: wire open/close logic for how-it-works modal"
```

---

### Task 6: Final check + deploy

**Step 1: Test on mobile (or mobile emulation in DevTools)**

- Open DevTools → Toggle device toolbar → iPhone 14 Pro
- Hard refresh
- Verify modal fills screen correctly
- Verify safe-area padding at bottom (notch devices)
- Verify text is readable, sections are well-spaced

**Step 2: Push and deploy**

```bash
git push origin main
vercel --prod
```

**Step 3: Smoke test on live URL**

Open https://fogchaser.vercel.app on phone. Tap "How does this work →". Verify modal opens and closes correctly.
