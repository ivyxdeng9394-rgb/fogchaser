const LOCAL = window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1";
const MANIFEST_URL  = LOCAL ? "data/manifest.json" : "https://pub-e433cc0481d6494280712cc9b1e4100e.r2.dev/manifest.json";
const TERRAIN_URL   = "https://pub-e433cc0481d6494280712cc9b1e4100e.r2.dev/terrain_offset.tif";
const DC_CENTER = [38.95, -77.05];
const DC_ZOOM   = 10;

// DC metro ASOS stations — nearest-station fallback for location labeling
const STATIONS = {
  KDCA: { name: "Reagan National (DC)",   lat: 38.852, lon: -77.037 },
  KBWI: { name: "BWI Airport (MD)",       lat: 39.175, lon: -76.668 },
  KIAD: { name: "Dulles Airport (VA)",    lat: 38.944, lon: -77.456 },
  KCGS: { name: "College Park (MD)",      lat: 38.981, lon: -76.922 },
  KGAI: { name: "Montgomery Co. (MD)",    lat: 39.168, lon: -77.166 },
  KHEF: { name: "Manassas (VA)",          lat: 38.721, lon: -77.515 },
  KFDK: { name: "Frederick (MD)",         lat: 39.417, lon: -77.374 },
  KNYG: { name: "Quantico (VA)",          lat: 38.502, lon: -77.305 },
};

// Fog overlay: lighter touch — labels tile layer renders on top so names stay readable
function fogColor(prob) {
  if (prob == null || prob < 0) return null;
  if (prob < 0.03)  return null;
  if (prob < 0.08)  return "rgba(140,205,235,0.28)";
  if (prob < 0.12)  return "rgba(90,165,218,0.42)";
  if (prob < 0.17)  return "rgba(55,130,208,0.54)";
  if (prob < 0.21)  return "rgba(30,100,192,0.65)";
  if (prob < 0.24)  return "rgba(12,72,178,0.74)";
  return                    "rgba(0,38,152,0.82)";
}

function fogScore(prob) {
  if (!prob || prob < 0.08) return 1;
  if (prob < 0.13) return 2;
  if (prob < 0.17) return 3;
  if (prob < 0.22) return 4;
  return 5;
}

function fogLabel(prob) {
  return ["", "Low", "Moderate", "High", "Very High", "Extreme"][fogScore(prob)];
}


function probLabel(prob) {
  if (!prob || prob < 0.03) return "1/5 — Low";
  return `${fogScore(prob)}/5 — ${fogLabel(prob)}`;
}

const ET = "America/New_York";

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

function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
}

function buildNavURL(destLat, destLon, dep = getDeparture()) {
  if (!dep) return null;
  if (isIOS()) {
    return `maps://?saddr=${dep.lat},${dep.lon}&daddr=${destLat},${destLon}&dirflg=d`;
  }
  return `https://www.google.com/maps/dir/?api=1&origin=${dep.lat},${dep.lon}&destination=${destLat},${destLon}&travelmode=driving`;
}

function formatHour(valid_utc) {
  const d    = new Date(valid_utc);
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", hour12: true, timeZone: ET });
  const diffH = Math.round((d - Date.now()) / 3600000);
  const rel  = diffH === 0 ? "now" : diffH > 0 ? `+${diffH}h` : `${diffH}h`;
  return { time, rel, diffH };
}

function cellHourLabel(valid_utc) {
  const d = new Date(valid_utc);
  const parts = new Intl.DateTimeFormat("en-US", { hour: "numeric", hour12: true, timeZone: ET }).formatToParts(d);
  const hour  = parts.find(p => p.type === "hour").value;
  const ampm  = parts.find(p => p.type === "dayPeriod").value[0].toLowerCase();
  return `${hour}${ampm}`;
}

function dateLabel(valid_utc) {
  return new Date(valid_utc).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: ET });
}

function timeAgo(isoStr) {
  const diff = (Date.now() - new Date(isoStr).getTime()) / 60000;
  if (diff < 60) return `${Math.round(diff)}m ago`;
  return `${Math.round(diff / 60)}h ago`;
}

function nearestStation(lat, lon) {
  let best = null, bestDist = Infinity;
  for (const [id, s] of Object.entries(STATIONS)) {
    const d = Math.hypot(lat - s.lat, lon - s.lon);
    if (d < bestDist) { bestDist = d; best = { id, ...s }; }
  }
  return best;
}

// Reverse geocode via Nominatim — returns neighborhood/city name or null
const geocodeCache = {};
async function reverseGeocode(lat, lon) {
  const key = `${lat.toFixed(2)},${lon.toFixed(2)}`;
  if (geocodeCache[key] !== undefined) return geocodeCache[key];
  try {
    const url = `https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lon}&format=json&zoom=14&accept-language=en`;
    const r    = await fetch(url);
    const data = await r.json();
    const a    = data.address || {};
    const place = a.suburb || a.neighbourhood || a.city_district ||
                  a.town || a.village || a.city || a.county;
    const state = a.state_code || (a.state || "").replace(/^.+ /, "");
    const result = place ? `${place}, ${state}` : null;
    geocodeCache[key] = result;
    return result;
  } catch {
    geocodeCache[key] = null;
    return null;
  }
}

// Plain-English bullets from atmospheric conditions
function conditionBullets(conditions) {
  if (!conditions) return [];
  const { t_td_spread_f, wind_speed_mph, hpbl_m, hgt_cldbase_m, rh_pct } = conditions;
  const bullets = [];

  if (t_td_spread_f <= 2)
    bullets.push("Air temperature and dew point are nearly equal — the air is close to saturation");
  else if (t_td_spread_f <= 5)
    bullets.push("Some moisture in the air, but not yet fully saturated");
  else
    bullets.push("Dry air — large gap between temperature and dew point");

  if (wind_speed_mph < 5)
    bullets.push("Calm winds — fog can form and linger once it develops");
  else if (wind_speed_mph < 12)
    bullets.push("Light winds — fog may form but could drift or thin out");
  else
    bullets.push("Too windy for dense fog to stay put");

  if (hpbl_m < 200)
    bullets.push("Very shallow, stable atmosphere — cold air is trapped near the ground");
  else if (hpbl_m < 500)
    bullets.push("Shallow atmosphere — favors cold air pooling in low-lying areas");

  if (hgt_cldbase_m < 400)
    bullets.push("Cloud base is very low — overcast and close to the surface");

  if (rh_pct > 92)
    bullets.push("Humidity is near maximum — air is holding as much moisture as it can");

  return bullets;
}

function terrainBullet(offset) {
  if (offset == null) return null;
  if (offset > 0.25)  return "Low-lying valley or sheltered hollow — cold air pools here, raising local fog likelihood";
  if (offset > 0.10)  return "Low-lying terrain — slightly more fog-prone than surrounding higher ground";
  if (offset >= -0.05) return "Average terrain — no strong terrain effect on fog at this location";
  return "Elevated or open area — fog less likely to settle here than in nearby valleys";
}

// ── State ─────────────────────────────────────────────────────────────────────
let map, currentLayer, manifest;
let currentClickLatLng = null; // lat/lon of last map tap — used by navigate button
const georasterCache = {};

// ── Init map ──────────────────────────────────────────────────────────────────
map = L.map("map", {
  center: DC_CENTER,
  zoom: DC_ZOOM,
  minZoom: 9,
});

// Base: dark, no labels — fog overlay goes over this
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png", {
  attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors © <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: "abcd",
  maxZoom: 20,
}).addTo(map);

// Labels pane — sits above the fog overlay so names are always readable
const labelsPane = map.createPane("labels");
labelsPane.style.zIndex = 650;
labelsPane.style.pointerEvents = "none";
L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png", {
  pane: "labels",
  subdomains: "abcd",
  maxZoom: 20,
}).addTo(map);

// Coverage boundary — dashed rectangle showing prediction area extent
L.rectangle(
  [[38.5, -77.7], [39.4, -76.8]],
  { color: "#a89e92", weight: 1.5, dashArray: "5 6", fill: false, opacity: 0.45, interactive: false }
).addTo(map);

// Legend
const LegendControl = L.Control.extend({
  onAdd() {
    const div = L.DomUtil.create("div", "map-legend");
    div.innerHTML = `
      <div class="legend-title">Fog risk</div>
      <div class="legend-row"><span class="swatch" style="background:rgba(140,205,235,0.45)"></span>Low</div>
      <div class="legend-row"><span class="swatch" style="background:rgba(90,165,218,0.58)"></span>Moderate</div>
      <div class="legend-row"><span class="swatch" style="background:rgba(55,130,208,0.72)"></span>High</div>
      <div class="legend-row"><span class="swatch" style="background:rgba(0,38,152,0.88)"></span>Very High+</div>
    `;
    L.DomEvent.disableClickPropagation(div);
    return div;
  }
});
new LegendControl({ position: "topright" }).addTo(map);

// ── Sheet — position above time bar ──────────────────────────────────────────
const sheet = document.getElementById("info-sheet");

function positionSheet() {
  const tbH = document.getElementById("time-bar").offsetHeight;
  sheet.style.bottom = tbH + "px";
}
positionSheet();
window.addEventListener("resize", positionSheet);

function openSheet() {
  sheet.classList.add("open");
  sheet.classList.remove("peeking");
}

function closeSheet() {
  sheet.classList.remove("open", "peeking");
}

function panMapForSheet(latlng) {
  const mapH   = map.getContainer().offsetHeight;
  const sheetH = window.innerHeight * 0.4; // matches max-height: 40vh
  const safeH  = mapH - sheetH;
  const targetY = safeH * 0.38; // place pin 38% from top of visible area
  const pinY    = map.latLngToContainerPoint(latlng).y;
  const deltaY  = pinY - targetY;
  if (Math.abs(deltaY) > 20) {
    map.panBy([0, deltaY], { animate: true, duration: 0.3 });
  }
}

function resetExplorer() {
  closeSheet();
  if (clickMarker) { map.removeLayer(clickMarker); clickMarker = null; }
  currentClickLatLng = null;
  document.getElementById("sheet-location").textContent = "Tap the map to explore";
  document.getElementById("sheet-score-label").textContent = "";
  document.getElementById("prob-value").textContent = "—";
  document.getElementById("prob-label").textContent = "—";
  // Reset why section
  closeWhySection();
  document.getElementById("approx-note").classList.remove("visible-ready");
  document.getElementById("why-toggle").style.display = "none";
  // Reset plan section
  document.getElementById("plan-toggle").style.display = "none";
  closePlanSection();
  document.getElementById("lighting-times").innerHTML = "";
}

document.getElementById("sheet-close").addEventListener("click", resetExplorer);
document.getElementById("header-title").addEventListener("click", resetExplorer);

// ── Accordion: Plan this spot + Why this score ─────────────────────────────
// Only one section open at a time.

function openPlanSection() {
  document.getElementById("plan-section").classList.add("visible");
  document.getElementById("plan-section").removeAttribute("aria-hidden");
  document.getElementById("plan-toggle").classList.add("expanded");
  // Close why section
  closeWhySection();
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

// Drag gesture on bottom sheet (mobile swipe up/down)
let dragStartY = null, dragStartOpen = false;
sheet.addEventListener("touchstart", e => {
  dragStartY    = e.touches[0].clientY;
  dragStartOpen = sheet.classList.contains("open");
}, { passive: true });
sheet.addEventListener("touchend", e => {
  if (dragStartY === null) return;
  const delta = dragStartY - e.changedTouches[0].clientY;
  if (Math.abs(delta) < 12) { dragStartY = null; return; } // too small — treat as tap
  if (delta > 0) openSheet(); else resetExplorer();
  dragStartY = null;
}, { passive: true });

// ── Load manifest ─────────────────────────────────────────────────────────────
async function init() {
  try {
    const r = await fetch(`${MANIFEST_URL}?t=` + Date.now());
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    manifest = await r.json();
  } catch (e) {
    const el = document.getElementById("loading");
    el.textContent = "Forecast unavailable — try again later.";
    el.style.color = "#c47070";
    return;
  }

  if (!manifest.hours?.length) {
    document.getElementById("loading").textContent = "No forecast data.";
    return;
  }

  document.getElementById("updated-label").textContent =
    timeAgo(manifest.generated_utc);

  // Only show hours that haven't passed yet
  const now = Date.now();
  manifest.hours = manifest.hours.filter(h => new Date(h.valid_utc).getTime() > now);

  if (!manifest.hours.length) {
    document.getElementById("loading").textContent = "Forecast is stale — run fogrefresh to update.";
    document.getElementById("loading").style.color = "#c47070";
    return;
  }

  // Summary bar: driven by peak hour (not average) so high-fog windows aren't buried
  const forBadge  = manifest.hours;
  const peakHour   = forBadge.reduce((b, h) => h.avg_prob > b.avg_prob ? h : b, forBadge[0]);
  const peakHrComp = cellHourLabel(peakHour.valid_utc);
  const peakDate   = dateLabel(peakHour.valid_utc);
  const ovnScore  = fogScore(peakHour.avg_prob);
  const ovnLabel  = fogLabel(peakHour.avg_prob);
  const scoreEl   = document.getElementById("tonight-score");
  const textEl    = document.getElementById("tonight-text");

  scoreEl.textContent = `${ovnScore}/5 — ${ovnLabel}`;
  scoreEl.className   = ovnScore >= 3 ? "go" : ovnScore === 2 ? "warn" : "skip";

  const firstDate = dateLabel(forBadge[0].valid_utc);
  const lastDate  = dateLabel(forBadge[forBadge.length - 1].valid_utc);
  const firstComp = cellHourLabel(forBadge[0].valid_utc);
  const lastComp  = cellHourLabel(forBadge[forBadge.length - 1].valid_utc);
  const window12  = firstDate === lastDate
    ? `${firstDate}, ${firstComp} – ${lastComp} ET`
    : `${firstDate}, ${firstComp} – ${lastDate}, ${lastComp} ET`;

  if (ovnScore >= 3) {
    textEl.textContent = `Peak around ${peakDate}, ${peakHrComp} ET · Worth setting an alarm`;
  } else if (ovnScore === 2) {
    textEl.textContent = `${window12} · Low signal, patchy fog possible`;
  } else {
    textEl.textContent = `${window12} · No fog expected`;
  }

  const slider = document.getElementById("hour-slider");
  slider.max   = manifest.hours.length - 1;
  slider.value = 0;

  function updateSliderFill() {
    const pct = slider.max > 0 ? (slider.value / slider.max) * 100 : 0;
    slider.style.setProperty("--slider-fill", `${pct}%`);
  }
  updateSliderFill();

  buildExposureStrip();
  positionSheet(); // re-measure now that exposure strip cells are rendered
  await showHour(0);

  document.getElementById("loading").style.display = "none";

  // Preload terrain GeoRaster in background so first click is fast
  loadGeoRaster(TERRAIN_URL).catch(() => {});

  slider.addEventListener("input", () => {
    const idx = parseInt(slider.value);
    updateSliderFill();
    showHour(idx);
    updateActiveCell(idx);
    // Refresh lighting times if plan section is open and a location is selected
    if (currentClickLatLng && document.getElementById("plan-section").classList.contains("visible")) {
      renderLightingTimes(currentClickLatLng.lat, currentClickLatLng.lng, manifest.hours[idx].valid_utc);
    }
    // Preload neighbours so next step cross-fades without a network wait
    [idx - 1, idx + 1].forEach(i => {
      if (i >= 0 && i < manifest.hours.length && manifest.hours[i].url)
        loadGeoRaster(manifest.hours[i].url).catch(() => {});
    });
  });

  map.on("click", onMapClick);
}

// ── Exposure strip ────────────────────────────────────────────────────────────
function buildExposureStrip() {
  const el = document.getElementById("exposure-strip");
  el.innerHTML = "";

  manifest.hours.forEach((h, i) => {
    const cell = document.createElement("div");
    cell.className = "exposure-cell";

    const p = h.avg_prob || 0;
    if (p >= 0.17) {
      const t = Math.min(1, (p - 0.17) / (0.252 - 0.17));
      cell.style.background = `rgba(40,105,198,${0.52 + t * 0.32})`;
      cell.classList.add("fog-hi");
    } else if (p >= 0.08) {
      const t = (p - 0.08) / (0.17 - 0.08);
      cell.style.background = `rgba(65,140,215,${0.14 + t * 0.36})`;
    } else if (p >= 0.03) {
      cell.style.background = "rgba(85,150,210,0.09)";
    }

    cell.innerHTML = `<span class="cell-hour">${cellHourLabel(h.valid_utc)}</span>`;
    cell.addEventListener("click", () => {
      document.getElementById("hour-slider").value = i;
      showHour(i);
      updateActiveCell(i);
    });
    el.appendChild(cell);
  });

  updateActiveCell(0);
}

function updateActiveCell(idx) {
  document.querySelectorAll(".exposure-cell").forEach((c, i) =>
    c.classList.toggle("active", i === idx)
  );
}

// ── Show forecast hour ────────────────────────────────────────────────────────
async function showHour(idx) {
  const h = manifest.hours[idx];
  const { time, rel } = formatHour(h.valid_utc);

  document.getElementById("hour-label").textContent =
    `${time}  (${rel})  ·  ${h.label || "—"}`;

  updateActiveCell(idx);

  if (!h.url) {
    if (currentLayer) { map.removeLayer(currentLayer); currentLayer = null; }
    return;
  }

  const gr = await loadGeoRaster(h.url);
  const newLayer = georasterToOverlay(gr);
  newLayer.addTo(map);

  // Cross-fade: new layer in, old layer out simultaneously
  const newEl = newLayer._image;
  const oldLayer = currentLayer;
  const oldEl = oldLayer?._image;

  if (newEl) {
    newEl.style.opacity = "0";
    newEl.style.transition = "opacity 0.28s ease";
    requestAnimationFrame(() => { newEl.style.opacity = "1"; });
  }
  if (oldEl) {
    oldEl.style.transition = "opacity 0.28s ease";
    oldEl.style.opacity = "0";
    setTimeout(() => { if (oldLayer) map.removeLayer(oldLayer); }, 280);
  } else if (oldLayer) {
    map.removeLayer(oldLayer);
  }

  currentLayer = newLayer;
}

// Render a georaster to a single L.imageOverlay — eliminates tile seams entirely
function georasterToOverlay(gr) {
  const w = gr.width, h = gr.height;
  const canvas = document.createElement("canvas");
  canvas.width = w; canvas.height = h;
  const ctx = canvas.getContext("2d");
  const img = ctx.createImageData(w, h);
  const band = gr.values[0];

  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const v = band[y][x];
      const color = fogColor(v);
      const i = (y * w + x) * 4;
      if (!color) { img.data[i + 3] = 0; continue; }
      // Parse "rgba(r,g,b,a)" string
      const m = color.match(/[\d.]+/g);
      img.data[i]     = +m[0];
      img.data[i + 1] = +m[1];
      img.data[i + 2] = +m[2];
      img.data[i + 3] = Math.round(+m[3] * 255);
    }
  }
  ctx.putImageData(img, 0, 0);
  const url = canvas.toDataURL();
  const bounds = [[gr.ymin, gr.xmin], [gr.ymax, gr.xmax]];
  return L.imageOverlay(url, bounds, { opacity: 1.0, interactive: false });
}

async function loadGeoRaster(url) {
  if (georasterCache[url]) return georasterCache[url];
  const resp   = await fetch(url);
  const buffer = await resp.arrayBuffer();
  const gr     = await parseGeoraster(buffer);
  georasterCache[url] = gr;
  return gr;
}

// ── Map click ─────────────────────────────────────────────────────────────────
let clickMarker = null;

async function onMapClick(e) {
  currentClickLatLng = e.latlng;
  const idx = parseInt(document.getElementById("hour-slider").value);
  const h   = manifest.hours[idx];
  if (!h.url) return;

  // Pin on map
  if (clickMarker) map.removeLayer(clickMarker);
  clickMarker = L.circleMarker([e.latlng.lat, e.latlng.lng], {
    radius: 7,
    color: "#4da8cf",
    fillColor: "#4da8cf",
    fillOpacity: 0.18,
    weight: 2,
  }).addTo(map);

  // Show sheet immediately in loading state
  document.getElementById("sheet-location").textContent = "Reading location…";
  document.getElementById("sheet-score-label").textContent = "";
  document.getElementById("prob-value").textContent = "—";
  document.getElementById("prob-label").textContent = "Reading…";
  document.getElementById("why-factors").classList.remove("visible");
  document.getElementById("approx-note").classList.remove("visible");
  openSheet();
  panMapForSheet(e.latlng);

  // Geocode + identify in parallel (terrain preloaded at startup, so this is fast)
  const [locationName, gr, terrainGr] = await Promise.all([
    reverseGeocode(e.latlng.lat, e.latlng.lng),
    loadGeoRaster(h.url),
    loadGeoRaster(TERRAIN_URL),
  ]);

  // Location: prefer geocoded name, fall back to nearest station
  if (locationName) {
    document.getElementById("sheet-location").textContent = locationName;
  } else {
    const st = nearestStation(e.latlng.lat, e.latlng.lng);
    document.getElementById("sheet-location").textContent =
      st ? `Near ${st.name}` : "DC Metro Area";
  }

  let prob = null;
  try {
    const results = await geoblaze.identify(gr, [e.latlng.lng, e.latlng.lat]);
    if (results?.[0] != null && results[0] > -9990) prob = results[0];
  } catch (_) {}

  let terrainOffset = null;
  try {
    const tr = await geoblaze.identify(terrainGr, [e.latlng.lng, e.latlng.lat]);
    if (tr?.[0] != null && tr[0] > -1.0 && tr[0] < 1.0) terrainOffset = tr[0];
  } catch (_) {}

  if (prob == null) {
    document.getElementById("prob-label").textContent = "No data at this location.";
    return;
  }

  document.getElementById("sheet-score-label").textContent = `${fogScore(prob)}/5`;
  document.getElementById("prob-value").textContent =
    `${fogScore(prob)}/5 — ${fogLabel(prob)}`;
  const goLabel = ["", "Stay home", "Probably not worth it", "Marginal — your call", "Worth the alarm", "Worth the alarm"][fogScore(prob)];
  document.getElementById("prob-label").textContent = goLabel;

  // Contributing factors — atmospheric (regional) + terrain (location-specific)
  const bullets = conditionBullets(h.conditions);
  const tb = terrainBullet(terrainOffset);
  if (tb) bullets.push(tb);
  const factorsEl  = document.getElementById("why-factors");
  const toggleEl   = document.getElementById("why-toggle");
  const approxEl   = document.getElementById("approx-note");
  factorsEl.classList.remove("visible");
  toggleEl.classList.remove("expanded");

  if (bullets.length) {
    factorsEl.innerHTML = bullets.map(b => `<div class="why-bullet">${b}</div>`).join("");
    if (h.approx_asos) {
      approxEl.textContent = "After the first hour, we use weather model estimates instead of live sensor readings. Accuracy is slightly lower for these hours.";
      approxEl.classList.add("visible-ready");
    }
    toggleEl.style.display = "block";
  }

  // Show plan toggle and populate planning section
  document.getElementById("plan-toggle").style.display = "block";
  renderDeparture();
  renderLightingTimes(e.latlng.lat, e.latlng.lng, h.valid_utc);
}

// ── How it works modal ────────────────────────────────────────────────────────
function openHowModal() {
  const scrollY = window.scrollY;
  document.body.style.position = "fixed";
  document.body.style.top = `-${scrollY}px`;
  document.body.style.width = "100%";
  document.getElementById("how-modal").classList.add("open");
}

function closeHowModal() {
  const scrollY = Math.abs(parseInt(document.body.style.top || "0", 10));
  document.body.style.position = "";
  document.body.style.top = "";
  document.body.style.width = "";
  document.getElementById("how-modal").classList.remove("open");
  window.scrollTo(0, scrollY);
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("how-link").addEventListener("click", openHowModal);
  document.getElementById("how-close").addEventListener("click", closeHowModal);
  document.getElementById("how-backdrop").addEventListener("click", closeHowModal);

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

  document.getElementById("navigate-btn").addEventListener("click", () => {
    if (!currentClickLatLng) return;
    const dep = getDeparture();
    if (!dep) {
      openDepartureModal();
      return;
    }
    const url = buildNavURL(currentClickLatLng.lat, currentClickLatLng.lng, dep);
    if (url) window.open(url, "_blank", "noopener");
  });

  (function () {
    const sheet = document.getElementById("how-sheet");
    let startY = null;

    sheet.addEventListener("touchstart", e => {
      startY = e.touches[0].clientY;
    }, { passive: true });

    sheet.addEventListener("touchcancel", () => { startY = null; }, { passive: true });

    sheet.addEventListener("touchend", e => {
      if (startY === null) return;
      const delta = e.changedTouches[0].clientY - startY;
      if (delta > 60) closeHowModal();
      startY = null;
    }, { passive: true });
  })();
});

init();
