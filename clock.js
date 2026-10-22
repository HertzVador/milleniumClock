"use strict";

const TAU = Math.PI * 2;
const BACKGROUND = "#0e1016";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const SEASONS = ["#7fb4ff", "#a6dcff", "#9be86a", "#4fd65a", "#2fc96e", "#ffe63a", "#ffc21a", "#ff9f1a", "#ff7f1f", "#f25a26", "#d8352a", "#6f95ff"];
const canvas = document.getElementById("clock");
const context = canvas.getContext("2d");
const timeDisplay = document.getElementById("time");
const dateDisplay = document.getElementById("date");
const fpsDisplay = document.getElementById("fps");
const sunStatus = document.getElementById("sun-status");
const latitudeInput = document.getElementById("latitude");
const longitudeInput = document.getElementById("longitude");
const sun = { night: null, noon: null, day: null, attempted: 0 };
let size = 0;
let pixelRatio = 1;
let coordinates = null;
let sunRequest = 0;

function modulo(value, period) {
  return ((value % period) + period) % period;
}

function mix(first, second, amount) {
  const channels = [1, 3, 5].map(offset => {
    const start = parseInt(first.slice(offset, offset + 2), 16);
    const end = parseInt(second.slice(offset, offset + 2), 16);
    return Math.round(start + (end - start) * amount).toString(16).padStart(2, "0");
  });
  return `#${channels.join("")}`;
}

function glow(age, period, trail, fadeIn) {
  age = modulo(age, period);
  if (age > period - fadeIn) return 1 - (period - age) / fadeIn;
  return Math.max(0, 1 - age / trail) ** 2;
}

function ringStates(now) {
  const seconds = now.getSeconds() + now.getMilliseconds() / 1000;
  const minutes = now.getMinutes() + seconds / 60;
  const hours = now.getHours() + minutes / 60;
  const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
  const days = now.getDate() - 1 + hours / 24;
  const months = now.getMonth() + days / daysInMonth;
  const padded = value => String(value).padStart(2, "0");
  return [
    { count: 10, position: 1 + months / 12, label: value => String(now.getFullYear() - 1 + value), subdiv: 12, color: "#9b8cff" },
    { count: 12, position: months, label: value => MONTHS[value], subdiv: 4, color: "#4aa8ff", colors: SEASONS },
    { count: daysInMonth, position: days, label: value => String(value + 1), subdiv: 4, color: "#2fd6c6" },
    { count: 24, position: hours, label: padded, subdiv: 4, color: "#82e04f" },
    { count: 60, position: minutes, label: padded, subdiv: 1, every: 5, color: "#ffd23f" },
    { count: 60, position: seconds, label: padded, subdiv: 1, every: 5, color: "#ff9142" },
    { count: 10, position: seconds % 10, label: String, subdiv: 10, color: "#ff5277", fixed: true }
  ];
}

function arc(radius, start, end, color, width, counterclockwise = false) {
  context.beginPath();
  context.arc(0, 0, radius, start, end, counterclockwise);
  context.strokeStyle = color;
  context.lineWidth = width;
  context.stroke();
}

function band(inner, outer, fill) {
  context.beginPath();
  context.arc(0, 0, outer, 0, TAU);
  context.arc(0, 0, inner, 0, TAU, true);
  context.fillStyle = fill;
  context.fill();
}

function seasonalBand(inner, outer, colors) {
  const gradient = context.createConicGradient(-Math.PI / 2, 0, 0);
  const wrap = mix(colors[colors.length - 1], colors[0], 0.5);
  gradient.addColorStop(0, wrap);
  for (let index = 0; index < colors.length; index++) {
    gradient.addColorStop((index + 0.5) / colors.length, colors[colors.length - 1 - index]);
  }
  gradient.addColorStop(1, wrap);
  context.globalAlpha = 110 / 255;
  band(inner, outer, gradient);
  context.globalAlpha = 1;
}

function drawNight(inner, outer, count) {
  if (!sun.night) return;
  const [sunset, sunrise] = sun.night;
  const start = -Math.PI / 2 - sunset / count * TAU;
  const end = start - modulo(sunrise - sunset, count) / count * TAU;
  context.beginPath();
  context.arc(0, 0, outer, start, end, true);
  context.arc(0, 0, inner, end, start);
  context.closePath();
  context.fillStyle = "rgba(0, 0, 10, 0.67)";
  context.fill();
}

function drawSun(radius, width) {
  context.save();
  context.rotate(-sun.noon / 24 * TAU);
  context.translate(0, -(radius - width * 0.2));
  const dot = width * 0.1;
  context.strokeStyle = "#ffd23f";
  context.lineWidth = Math.max(1, dot * 0.3);
  for (let ray = 0; ray < 8; ray++) {
    context.rotate(TAU / 8);
    context.beginPath();
    context.moveTo(dot * 1.4, 0);
    context.lineTo(dot * 1.9, 0);
    context.stroke();
  }
  context.beginPath();
  context.arc(0, 0, dot, 0, TAU);
  context.fillStyle = "#ffd23f";
  context.fill();
  context.strokeStyle = BACKGROUND;
  context.stroke();
  context.restore();
}

function drawRing(inner, outer, state, isHour) {
  const width = outer - inner;
  const gap = width * 0.04;
  const top = outer - gap * 2;
  context.save();
  if (!state.fixed) context.rotate(state.position / state.count * TAU);
  if (state.colors) seasonalBand(inner + gap, outer - gap, state.colors);
  else band(inner + gap, outer - gap, `${state.color}26`);
  if (isHour) drawNight(inner + gap, outer - gap, state.count);
  context.font = `${Math.max(5, width * 0.30)}px "Segoe UI", sans-serif`;
  context.textAlign = "center";
  context.textBaseline = "middle";
  context.lineCap = "round";
  const total = state.count * state.subdiv;
  for (let tick = 0; tick < total; tick++) {
    const index = Math.floor(tick / state.subdiv);
    const minor = tick % state.subdiv !== 0;
    const color = state.colors ? state.colors[index] : state.color;
    const brightness = glow(state.position * state.subdiv - tick, total, 8, 1);
    context.save();
    context.rotate((state.fixed ? 1 : -1) * tick / total * TAU);
    context.strokeStyle = state.fixed ? mix(mix(color, "#000000", 0.55), "#ffffff", brightness * 0.8) : minor ? mix(color, "#000000", 0.38) : color;
    context.lineWidth = Math.max(0.6, width * (minor ? 0.02 : 0.035));
    context.beginPath();
    context.moveTo(0, -top);
    context.lineTo(0, -top + width * (minor ? 0.14 : 0.28));
    context.stroke();
    if (!minor && index % (state.every || 1) === 0) {
      context.fillStyle = state.fixed
        ? mix(mix(color, "#000000", 0.55), "#ffffff", glow(state.position - index, state.count, 1.5, 0.25) * 0.8)
        : mix(color, "#ffffff", index === Math.floor(state.position) ? 0.5 : state.colors ? 0.25 : 0);
      context.fillText(state.label(index), 0, -(inner + width * 0.40));
    }
    context.restore();
  }
  if (isHour && sun.noon !== null) drawSun(outer, width);
  context.restore();
}

function drawCenter(radius, seconds) {
  const hole = radius * 0.12;
  const pitch = (radius - hole) / 60;
  band(hole, radius, "#12151d");
  band(0, hole, "#000000");
  context.lineCap = "butt";
  for (let index = 0; index < 60; index++) {
    const local = modulo(seconds - index, 60);
    const active = local < 1;
    const turn = active ? TAU * (0.5 - 0.5 * Math.cos(Math.PI * local)) : 0;
    const accent = active ? mix("#1f5a32", "#7dff9e", Math.min(1, local / 0.08, (1 - local) / 0.08)) : "#1f5a32";
    const body = active ? mix("#13161c", "#1f5a32", 0.5 * Math.sin(Math.PI * local)) : "#13161c";
    const middle = -Math.PI / 2 + turn;
    const halfSegment = 5 / 180 * Math.PI;
    const ringRadius = hole + (index + 0.5) * pitch;
    arc(ringRadius, middle + halfSegment, middle + TAU - halfSegment, body, pitch * 0.75);
    arc(ringRadius, middle - halfSegment, middle + halfSegment, accent, pitch * 0.75);
  }
}

function resize() {
  const bounds = canvas.parentElement.getBoundingClientRect();
  size = Math.max(1, Math.floor(Math.min(bounds.width, bounds.height)));
  pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.round(size * pixelRatio);
  canvas.height = Math.round(size * pixelRatio);
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;
}

function render(now) {
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  context.fillStyle = BACKGROUND;
  context.fillRect(0, 0, size, size);
  context.translate(size / 2, size / 2);
  const radius = size / 2 * 0.96;
  const hub = radius * 0.30;
  const width = (radius - hub) / 7;
  ringStates(now).forEach((state, index) => drawRing(radius - (index + 1) * width, radius - index * width, state, index === 3));
  context.strokeStyle = "#ff3355";
  context.lineWidth = Math.max(1.2, radius * 0.004);
  context.beginPath();
  context.moveTo(0, -(hub + width));
  context.lineTo(0, -radius);
  context.stroke();
  const point = radius * 0.025;
  context.beginPath();
  context.moveTo(-point, -radius - point * 1.2);
  context.lineTo(point, -radius - point * 1.2);
  context.lineTo(0, -radius + point * 0.4);
  context.closePath();
  context.fillStyle = "#ff3355";
  context.fill();
  drawCenter(hub * 0.96, now.getSeconds() + now.getMilliseconds() / 1000);
  const pad = (value, digits = 2) => String(value).padStart(digits, "0");
  timeDisplay.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}.${pad(now.getMilliseconds(), 3)}`;
  timeDisplay.dateTime = now.toISOString();
  dateDisplay.textContent = `${["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][now.getDay()]} ${pad(now.getDate())} ${MONTHS[now.getMonth()]} ${now.getFullYear()}`;
}

function localDay(now) {
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

function validCoordinates(value) {
  return value && Number.isFinite(value.lat) && Number.isFinite(value.lon) && Math.abs(value.lat) <= 90 && Math.abs(value.lon) <= 180;
}

async function fetchJSON(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

async function refreshSun() {
  const request = ++sunRequest;
  const day = localDay(new Date());
  sun.attempted = Date.now();
  sunStatus.textContent = "Fetching sun data...";
  try {
    let location = coordinates;
    if (!location) {
      const data = await fetchJSON("https://ipapi.co/json/");
      location = { lat: Number(data.latitude), lon: Number(data.longitude) };
      if (!validCoordinates(location)) throw new Error("Location unavailable");
    }
    const query = new URLSearchParams({ lat: location.lat, lng: location.lon, date: day, formatted: "0" });
    const data = await fetchJSON(`https://api.sunrise-sunset.org/json?${query}`);
    if (request !== sunRequest) return;
    if (data.status !== "OK") throw new Error("Sun data unavailable");
    const hour = value => {
      const time = new Date(value);
      if (!Number.isFinite(time.getTime())) throw new Error("Invalid sun data");
      return time.getUTCFullYear() === 1970 ? null : time.getHours() + time.getMinutes() / 60 + time.getSeconds() / 3600;
    };
    const sunrise = hour(data.results.sunrise);
    const sunset = hour(data.results.sunset);
    sun.night = sunrise !== null && sunset !== null ? [sunset, sunrise] : null;
    sun.noon = hour(data.results.solar_noon);
    sun.day = day;
    latitudeInput.value = location.lat;
    longitudeInput.value = location.lon;
    sunStatus.textContent = `Sun data updated (${coordinates ? "manual" : "IP"} location, device time zone).`;
  } catch (error) {
    if (request !== sunRequest) return;
    sunStatus.textContent = "Sun data unavailable. Retrying in 10 minutes; clock remains active.";
  }
}

function setLocation(location) {
  coordinates = location;
  sun.night = null;
  sun.noon = null;
  sun.day = null;
  try {
    if (location) localStorage.setItem("disc-clock-location", JSON.stringify(location));
    else localStorage.removeItem("disc-clock-location");
  } catch (error) {}
  refreshSun();
}

try {
  const saved = JSON.parse(localStorage.getItem("disc-clock-location"));
  if (validCoordinates(saved)) coordinates = saved;
} catch (error) {}
const parameters = new URLSearchParams(window.location.search);
if (parameters.has("lat") && parameters.has("lon") && parameters.get("lat").trim() && parameters.get("lon").trim()) {
  const supplied = { lat: Number(parameters.get("lat")), lon: Number(parameters.get("lon")) };
  if (validCoordinates(supplied)) coordinates = supplied;
}
if (coordinates) {
  latitudeInput.value = coordinates.lat;
  longitudeInput.value = coordinates.lon;
}

document.getElementById("location-form").addEventListener("submit", event => {
  event.preventDefault();
  const location = { lat: latitudeInput.valueAsNumber, lon: longitudeInput.valueAsNumber };
  if (validCoordinates(location)) setLocation(location);
});
document.getElementById("automatic-location").addEventListener("click", () => setLocation(null));

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await document.documentElement.requestFullscreen();
  } catch (error) {
    document.getElementById("fullscreen").title = "Fullscreen unavailable in this browser";
  }
}
document.getElementById("fullscreen").addEventListener("click", toggleFullscreen);
document.addEventListener("keydown", event => {
  if (event.key === "F11") {
    event.preventDefault();
    toggleFullscreen();
  }
});
document.addEventListener("fullscreenchange", () => {
  document.getElementById("fullscreen").setAttribute("aria-pressed", String(Boolean(document.fullscreenElement)));
});
new ResizeObserver(resize).observe(canvas.parentElement);
window.addEventListener("resize", resize);
resize();
refreshSun();
setInterval(() => {
  if (sun.day !== localDay(new Date()) && Date.now() - sun.attempted >= 600000) refreshSun();
}, 10000);

let lastFrame = -Infinity;
let sampleStart = performance.now();
let frames = 0;
function animate(timestamp) {
  requestAnimationFrame(animate);
  if (document.hidden || timestamp - lastFrame < 1000 / 60 - 0.5) return;
  lastFrame = timestamp;
  render(new Date());
  frames++;
  if (timestamp - sampleStart >= 1000) {
    fpsDisplay.textContent = `${(frames * 1000 / (timestamp - sampleStart)).toFixed(1)} FPS`;
    sampleStart = timestamp;
    frames = 0;
  }
}
requestAnimationFrame(animate);