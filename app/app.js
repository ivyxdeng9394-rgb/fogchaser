const DATA_DIR  = "data";
const DC_CENTER = [38.95, -77.05];
const DC_ZOOM   = 10;

// Constrain map to DC metro coverage area
const DC_BOUNDS = L.latLngBounds(
  L.latLng(38.35, -77.85),  // SW
  L.latLng(39.55, -76.55)   // NE
);

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

const BASELINE = 0.054;

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

function relativeRisk(prob) {
  if (!prob) return "1.0";
  return (prob / BASELINE).toFixed(1);
}

function probLabel(prob) {
  if (!prob || prob < 0.03) return "1/5 — Low";
  return `${fogScore(prob)}/5 — ${fogLabel(prob)}`;
}

const ET = "America/New_York";

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

// ── State ─────────────────────────────────────────────────────────────────────
let map, currentLayer, manifest;
const georasterCache = {};

// ── Init map ──────────────────────────────────────────────────────────────────
map = L.map("map", {
  center: DC_CENTER,
  zoom: DC_ZOOM,
  maxBounds: DC_BOUNDS,
  maxBoundsViscosity: 0.85,
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
  document.getElementById("sheet-location").textContent = "Tap the map to explore";
  document.getElementById("sheet-score-label").textContent = "";
  document.getElementById("prob-value").textContent = "—";
  document.getElementById("prob-label").textContent = "—";
  document.getElementById("why-factors").classList.remove("visible");
  document.getElementById("approx-note").classList.remove("visible", "visible-ready");
  const toggleEl = document.getElementById("why-toggle");
  toggleEl.style.display = "none";
  toggleEl.classList.remove("expanded");
}

document.getElementById("sheet-close").addEventListener("click", resetExplorer);
document.getElementById("header-title").addEventListener("click", resetExplorer);

document.getElementById("why-toggle").addEventListener("click", () => {
  const factorsEl = document.getElementById("why-factors");
  const approxEl  = document.getElementById("approx-note");
  const toggleEl  = document.getElementById("why-toggle");
  const expanding = !factorsEl.classList.contains("visible");
  factorsEl.classList.toggle("visible", expanding);
  if (approxEl.classList.contains("visible-ready")) {
    approxEl.classList.toggle("visible", expanding);
  }
  toggleEl.classList.toggle("expanded", expanding);
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
    const r = await fetch(`${DATA_DIR}/manifest.json?t=` + Date.now());
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

  // Tonight bar: overnight average (23–07 UTC)
  const overnight = manifest.hours.filter(h => {
    const hr = parseInt(h.valid_utc.slice(11, 13));
    return hr >= 23 || hr <= 7;
  });
  const forBadge  = overnight.length > 0 ? overnight : manifest.hours;
  const avgOvn    = forBadge.reduce((s, h) => s + h.avg_prob, 0) / forBadge.length;
  const ovnScore  = fogScore(avgOvn);
  const ovnLabel  = fogLabel(avgOvn);
  const riskStr   = relativeRisk(avgOvn);

  // Find peak hour for best-window hint
  const peakHour  = forBadge.reduce((b, h) => h.avg_prob > b.avg_prob ? h : b, forBadge[0]);
  const { time: peakTime } = formatHour(peakHour.valid_utc);

  const scoreEl   = document.getElementById("tonight-score");
  const textEl    = document.getElementById("tonight-text");

  scoreEl.textContent = `${ovnScore}/5 — ${ovnLabel}`;
  scoreEl.className   = ovnScore >= 3 ? "go" : ovnScore === 2 ? "warn" : "skip";

  const firstTime = formatHour(forBadge[0].valid_utc).time;
  const lastTime  = formatHour(forBadge[forBadge.length - 1].valid_utc).time;
  const window12  = `${firstTime} -- ${lastTime} ET`;

  if (ovnScore >= 3) {
    textEl.textContent = `Peak around ${peakTime} ET · ${riskStr}× above normal · Worth setting an alarm`;
  } else if (ovnScore === 2) {
    textEl.textContent = `${window12} · Low signal, patchy fog possible`;
  } else {
    textEl.textContent = `${window12} · No fog expected`;
  }

  const slider = document.getElementById("hour-slider");
  slider.max   = manifest.hours.length - 1;
  slider.value = 0;

  buildExposureStrip();
  positionSheet(); // re-measure now that exposure strip cells are rendered
  await showHour(0);

  document.getElementById("loading").style.display = "none";

  slider.addEventListener("input", () => {
    const idx = parseInt(slider.value);
    showHour(idx);
    updateActiveCell(idx);
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
  if (currentLayer) map.removeLayer(currentLayer);

  currentLayer = new GeoRasterLayer({
    georaster: gr,
    opacity: 1.0,
    pixelValuesToColorFn: (values) => {
      const v = values[0];
      if (v == null || v < -9990) return null;
      return fogColor(v);
    },
    resolution: 512,
  });
  currentLayer.addTo(map);
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

  // Geocode + identify in parallel
  const [locationName, gr] = await Promise.all([
    reverseGeocode(e.latlng.lat, e.latlng.lng),
    loadGeoRaster(h.url),
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

  if (prob == null) {
    document.getElementById("prob-label").textContent = "No data at this location.";
    return;
  }

  document.getElementById("sheet-score-label").textContent = `${fogScore(prob)}/5`;
  document.getElementById("prob-value").textContent =
    `${fogScore(prob)}/5 — ${fogLabel(prob)}`;
  document.getElementById("prob-label").textContent =
    `${Math.round(prob * 100)}% probability  ·  ${relativeRisk(prob)}× above normal`;

  // Contributing factors — populate but hide behind toggle
  const bullets = conditionBullets(h.conditions);
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
}

init();
