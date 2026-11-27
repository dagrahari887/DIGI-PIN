/**
 * app.js
 * ------
 * Wires the B2B admin console to the v2 API:
 *   POST /api/v1/address/resolve
 * Renders every pipeline stage (quality, validation, location/DIGIPIN,
 * vertical, risk, verification, instructions) as its own card, and lets
 * the operator:
 *   - resolve an ambiguous address by picking a candidate
 *   - toggle the floor rail (recomputes instructions client-side, mirrors
 *     core/vertical_fusion.py exactly, no re-fetch)
 *   - mark a verification component "confirmed" (re-calls /resolve with
 *     confirmed_fields so the state genuinely comes from the backend's
 *     verification.py rules, never faked client-side)
 */

const API_BASE = "http://localhost:8000";
const HIGH_FLOOR_THRESHOLD = 4;
const FLOOR_OPTIONS = ["G", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];

const DEMOS = {
  complete: "Flat 302, 3rd Floor, Near Durga Temple, Sector 62, Noida, 201301",
  landmark: "Near Durga Temple, Sector 62, Noida",
  missingfloor: "Flat 302, Sector 62, Noida, 201301",
  missingflat: "3rd Floor, Near Durga Temple, Sector 62, Noida",
  ambiguous: "Sector 62",
  invalid: "asdkfj laksjdf laksjdlfk",
  campus: "A-12, IIT Delhi Campus, Hauz Khas, New Delhi, 110016",
  commercial: "5th Floor, Cyber Hub, DLF Phase 2, Gurugram, 122002",
};

// ---------------------------------------------------------------------------
// Map setup
// ---------------------------------------------------------------------------

const map = L.map("map", { zoomControl: true }).setView([22.9734, 78.6569], 5);
const satelliteLayer = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { attribution: "Tiles &copy; Esri", maxZoom: 21 }
);
const streetLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  attribution: "&copy; OpenStreetMap contributors",
  maxZoom: 19,
});
satelliteLayer.addTo(map);
L.control.layers({ Satellite: satelliteLayer, Street: streetLayer }).addTo(map);

let marker = null;
let gridPolygon = null;

function renderOnMap(lat, lon, box) {
  if (marker) map.removeLayer(marker);
  if (gridPolygon) map.removeLayer(gridPolygon);
  marker = L.marker([lat, lon]).addTo(map);
  const bounds = [
    [box.min_lat, box.min_lon],
    [box.min_lat, box.max_lon],
    [box.max_lat, box.max_lon],
    [box.max_lat, box.min_lon],
  ];
  gridPolygon = L.polygon(bounds, { color: "#1F7A5C", weight: 3, fillColor: "#1F7A5C", fillOpacity: 0.25 }).addTo(map);
  map.setView([lat, lon], 20);
}

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const el = {
  input: document.getElementById("address-input"),
  demoSelect: document.getElementById("demo-select"),
  resolveBtn: document.getElementById("resolve-btn"),
  errorMsg: document.getElementById("error-msg"),
  loadingBar: document.getElementById("loading-bar"),
  results: document.getElementById("results"),
  flowRail: document.getElementById("flow-rail"),

  qualityBadge: document.getElementById("quality-badge"),
  qualityFill: document.getElementById("quality-fill"),
  qualityReasons: document.getElementById("quality-reasons"),

  validationBadge: document.getElementById("validation-badge"),
  validationIssues: document.getElementById("validation-issues"),
  candidatesList: document.getElementById("candidates-list"),

  locationCard: document.getElementById("location-card"),
  digipinDisplay: document.getElementById("digipin-display"),
  locationFields: document.getElementById("location-fields"),

  verticalCard: document.getElementById("vertical-card"),
  floorRail: document.getElementById("floor-rail"),
  verticalFields: document.getElementById("vertical-fields"),

  riskBadge: document.getElementById("risk-badge"),
  riskReasons: document.getElementById("risk-reasons"),

  verificationBadge: document.getElementById("verification-badge"),
  verificationFields: document.getElementById("verification-fields"),

  deliveryInstructions: document.getElementById("delivery-instructions"),
  liftWarning: document.getElementById("lift-warning"),
  rawJson: document.getElementById("raw-json"),
};

function showError(message) {
  el.errorMsg.textContent = message;
  el.errorMsg.classList.remove("hidden");
}
function clearError() {
  el.errorMsg.classList.add("hidden");
  el.errorMsg.textContent = "";
}
function setLoading(isLoading) {
  el.loadingBar.style.opacity = isLoading ? "1" : "0";
  el.resolveBtn.disabled = isLoading;
  el.resolveBtn.textContent = isLoading ? "Resolving…" : "Resolve address";
}
function fieldRow(label, value) {
  return `<div class="field-row"><span class="field-label">${label}</span><span class="field-value">${value ?? "—"}</span></div>`;
}
function badgeClass(prefix, key) {
  return `badge badge-${String(key).toLowerCase()}`;
}
function markFlow(step, state) {
  const node = el.flowRail.querySelector(`[data-step="${step}"]`);
  if (!node) return;
  node.classList.remove("done", "skip");
  if (state) node.classList.add(state);
}
function resetFlow() {
  el.flowRail.querySelectorAll(".flow-step").forEach((n) => n.classList.remove("done", "skip"));
}

// ---------------------------------------------------------------------------
// Vertical instruction builder — mirrors core/vertical_fusion.py exactly so
// toggling the floor rail is instant and never re-hits the API.
// ---------------------------------------------------------------------------

function describeFloor(floor) {
  if (floor === null || floor === undefined) return "ground level (unconfirmed)";
  if (floor === "G" || floor === "0") return "the ground floor";
  const n = parseInt(floor, 10);
  let suffix = "th";
  if (n % 10 === 1 && n !== 11) suffix = "st";
  else if (n % 10 === 2 && n !== 12) suffix = "nd";
  else if (n % 10 === 3 && n !== 13) suffix = "rd";
  return `the ${floor}${suffix} floor`;
}
function buildInstructions({ floor, unit, landmark, accessNotes }) {
  const parts = ["Navigate to the highlighted DIGIPIN cell."];
  if (landmark) parts.push(`The building is near ${landmark}.`);
  const floorPhrase = describeFloor(floor);
  if (unit) parts.push(`Go to unit ${unit} on ${floorPhrase}.`);
  else parts.push(`Proceed to ${floorPhrase}.`);
  const floorNum = floor === "G" ? 0 : parseInt(floor, 10);
  const isHigh = !Number.isNaN(floorNum) && floorNum >= HIGH_FLOOR_THRESHOLD;
  if (isHigh) parts.push("This is a high floor -- confirm lift availability before dispatch.");
  if (accessNotes) parts.push(accessNotes.trim().replace(/\.$/, "") + ".");
  return { text: parts.join(" "), isHigh };
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let lastAddress = "";
let lastResolveBody = null; // successful /resolve response
let selectedFloor = null;
let confirmedFields = new Set();

// ---------------------------------------------------------------------------
// Renderers
// ---------------------------------------------------------------------------

function renderQuality(quality) {
  el.qualityBadge.textContent = `${quality.score} · ${quality.label}`;
  el.qualityBadge.className = badgeClass("quality", quality.label);
  el.qualityFill.style.width = `${quality.score}%`;
  el.qualityFill.style.background =
    quality.label === "complete" ? "#1F7A5C" : quality.label === "incomplete" ? "#B8860B" : "#B23A48";
  el.qualityReasons.innerHTML = quality.reasons.map((r) => `<li>${r}</li>`).join("");
  markFlow("quality", "done");
}

function renderValidation(validation, onSelectCandidate) {
  el.validationBadge.textContent = validation.decision;
  el.validationBadge.className = badgeClass("validation", validation.decision);
  el.validationIssues.innerHTML = (validation.issues || []).map((i) => `<li>${i}</li>`).join("");
  el.candidatesList.innerHTML = "";

  if (validation.candidates && validation.candidates.length) {
    validation.candidates.forEach((c, idx) => {
      const row = document.createElement("div");
      row.className = "candidate-row";
      row.innerHTML = `
        <div>
          <div class="text-[12px]">${c.display_name}</div>
          <div class="text-[10.5px] text-muted font-mono">importance ${c.importance.toFixed(2)} · ${c.latitude.toFixed(4)}, ${c.longitude.toFixed(4)}</div>
        </div>
        <button data-idx="${idx}">Use this</button>
      `;
      row.querySelector("button").addEventListener("click", () => onSelectCandidate(idx));
      el.candidatesList.appendChild(row);
    });
  }
  markFlow("validation", validation.decision === "proceed" ? "done" : "skip");
}

function renderLocation(dp) {
  el.locationCard.style.display = "block";
  el.digipinDisplay.textContent = dp.location.digipin;
  el.locationFields.innerHTML = [
    fieldRow("Coordinates", `${dp.location.latitude}, ${dp.location.longitude}`),
    fieldRow("Cell (bounding box)", `${dp.location.bounding_box.min_lat.toFixed(6)}…${dp.location.bounding_box.max_lat.toFixed(6)}`),
    fieldRow("Delivery Point ID", dp.delivery_point_id),
  ].join("");
  markFlow("location", "done");
  markFlow("digipin", "done");
  markFlow("delivery", "done");
}

function renderVertical(dp) {
  el.verticalCard.style.display = "block";
  const initialFloor = dp.vertical.floor_level || "G";
  selectedFloor = initialFloor;
  el.floorRail.innerHTML = "";
  FLOOR_OPTIONS.forEach((floor) => {
    const btn = document.createElement("button");
    btn.className = "floor-btn" + (floor === initialFloor ? " active" : "");
    btn.textContent = floor === "G" ? "Ground" : `Floor ${floor}`;
    btn.addEventListener("click", () => {
      selectedFloor = floor;
      document.querySelectorAll(".floor-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      refreshInstructions();
    });
    el.floorRail.appendChild(btn);
  });
  el.verticalFields.innerHTML = [
    fieldRow("House / unit", dp.vertical.unit_no || dp.vertical.house_no || "—"),
    fieldRow("Building hint", dp.vertical.building_hint || "—"),
    fieldRow("Lift confirmation needed", dp.vertical.requires_lift_confirmation ? "Yes" : "No"),
  ].join("");
  markFlow("vertical", "done");
}

function renderRisk(risk) {
  el.riskBadge.textContent = `${risk.level} (${risk.points} pts)`;
  el.riskBadge.className = badgeClass("risk", risk.level);
  el.riskReasons.innerHTML = risk.reasons.map((r) => `<li>${r}</li>`).join("");
  markFlow("risk", "done");
}

function renderVerification(verification, dp) {
  el.verificationBadge.textContent = verification.overall;
  el.verificationBadge.className = badgeClass("verification", verification.overall);
  el.verificationFields.innerHTML = "";
  Object.entries(verification.components).forEach(([name, comp]) => {
    const row = document.createElement("div");
    row.className = "verify-row";
    const isVerified = comp.state === "VERIFIED";
    row.innerHTML = `
      <span class="text-[12px] capitalize">${name}</span>
      <span class="flex items-center gap-2">
        <span class="badge badge-${comp.state.toLowerCase()}">${comp.state}</span>
        <button class="verify-btn" ${isVerified || name === "entrance" ? "disabled" : ""} data-field="${name}">Confirm</button>
      </span>
    `;
    if (!isVerified && name !== "entrance") {
      row.querySelector("button").addEventListener("click", () => confirmField(name));
    }
    el.verificationFields.appendChild(row);
  });
  markFlow("verification", "done");
}

function refreshInstructions() {
  if (!lastResolveBody) return;
  const dp = lastResolveBody.delivery_point;
  const { text, isHigh } = buildInstructions({
    floor: selectedFloor,
    unit: dp.vertical.unit_no || dp.vertical.house_no,
    landmark: dp.landmark,
    accessNotes: dp.access_notes,
  });
  el.deliveryInstructions.textContent = text;
  el.liftWarning.classList.toggle("hidden", !isHigh);
  markFlow("instructions", "done");
}

function renderFullResult(body) {
  lastResolveBody = body;
  el.results.style.display = "block";
  el.rawJson.textContent = JSON.stringify(body, null, 2);

  renderQuality(body.quality);
  renderValidation(body.validation, () => {});

  const dp = body.delivery_point;
  if (dp) {
    renderLocation(dp);
    renderVertical(dp);
    renderRisk(dp.risk);
    renderVerification(dp.verification, dp);
    refreshInstructions();
    renderOnMap(dp.location.latitude, dp.location.longitude, dp.location.bounding_box);
  } else {
    el.locationCard.style.display = "none";
    el.verticalCard.style.display = "none";
  }
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

async function callResolve(extra = {}) {
  const address = lastAddress;
  const payload = { address, confirmed_fields: Array.from(confirmedFields), ...extra };
  const response = await fetch(`${API_BASE}/api/v1/address/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  return { ok: response.ok, status: response.status, data };
}

async function confirmField(name) {
  confirmedFields.add(name);
  setLoading(true);
  try {
    const { ok, data } = await callResolve();
    if (ok) renderFullResult(data);
    else showError("Could not refresh verification state.");
  } finally {
    setLoading(false);
  }
}

async function selectCandidate(idx) {
  setLoading(true);
  try {
    const { ok, data } = await callResolve({ select_candidate_index: idx });
    if (ok) {
      clearError();
      renderFullResult(data);
    } else {
      showError("Could not resolve the selected candidate.");
    }
  } finally {
    setLoading(false);
  }
}

async function resolveAddress() {
  const address = el.input.value.trim();
  clearError();
  if (!address) {
    showError("Enter a delivery address first.");
    return;
  }

  lastAddress = address;
  confirmedFields = new Set();
  resetFlow();
  el.results.style.display = "none";
  setLoading(true);

  try {
    const { ok, status, data } = await callResolve();

    if (!ok) {
      const detail = data.detail;
      if (detail && detail.validation) {
        // Structured pipeline stop (reject / needs_confirmation) --
        // still render quality + validation so the operator sees why.
        el.results.style.display = "block";
        el.rawJson.textContent = JSON.stringify(data, null, 2);
        renderQuality(detail.quality);
        renderValidation(detail.validation, (idx) => selectCandidate(idx));
        el.locationCard.style.display = "none";
        el.verticalCard.style.display = "none";
        if (detail.validation.decision === "reject") {
          showError(detail.message || "Address could not be resolved.");
        }
      } else {
        showError((detail && detail.message) || `Request failed (${status}).`);
      }
      return;
    }

    renderFullResult(data);
  } catch (err) {
    showError(`Could not reach the API at ${API_BASE}. Make sure the FastAPI server is running (uvicorn main:app --reload --port 8000).`);
  } finally {
    setLoading(false);
  }
}

el.resolveBtn.addEventListener("click", resolveAddress);
el.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) resolveAddress();
});
el.demoSelect.addEventListener("change", (e) => {
  const key = e.target.value;
  if (key && DEMOS[key]) {
    el.input.value = DEMOS[key];
    resolveAddress();
  }
});
