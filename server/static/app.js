const POLL_MS = 2000;

const $ = (id) => document.getElementById(id);
const app = document.querySelector(".app");

let lastStatus = null;
let lastSinceMs = null;
let lastTodayUptime = 0;
let lastTodayDowntime = 0;
let lastTodayOutages = [];
let lastFetchOk = false;

function fmtDuration(totalSec) {
  const s = Math.max(0, Math.floor(totalSec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(sec)}`;
}

function fmtTimeLocal(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return iso;
  }
}

function fmtFullLocal(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function renderOutages(outages) {
  const list = $("outage-list");
  if (!outages || outages.length === 0) {
    list.innerHTML = '<li class="outages__empty">No outages today 🎉</li>';
    return;
  }
  const items = outages
    .slice()
    .reverse()
    .map((o) => {
      const cls = o.ongoing ? " class=\"outage--ongoing\"" : "";
      const label = o.ongoing ? "ongoing" : fmtDuration(o.duration_seconds);
      return `<li${cls}>
        <span class="outage__time">${fmtTimeLocal(o.start)}</span>
        <span class="outage__duration">${label}</span>
      </li>`;
    })
    .join("");
  list.innerHTML = items;
}

function applyStatus(data) {
  const status = data.status;
  app.dataset.status = status;
  $("status").textContent = status === "on" ? "ON" : "OFF";
  $("since-line").textContent = "since " + fmtFullLocal(data.since);
  $("last-heartbeat").textContent =
    "last ping " + fmtFullLocal(data.last_heartbeat_at);

  lastStatus = status;
  lastSinceMs = data.since ? new Date(data.since).getTime() : Date.now();

  const today = data.today || {};
  lastTodayUptime = today.uptime_seconds || 0;
  lastTodayDowntime = today.downtime_seconds || 0;
  lastTodayOutages = today.outages || [];

  $("stat-uptime-pct").textContent =
    (today.uptime_percent ?? 0).toFixed(1) + "%";
  $("stat-uptime-time").textContent = fmtDuration(lastTodayUptime) + " up";
  $("stat-downtime").textContent = fmtDuration(lastTodayDowntime);
  const oc = today.outage_count || 0;
  $("stat-outage-count").textContent =
    oc + (oc === 1 ? " outage" : " outages");

  renderOutages(lastTodayOutages);
}

function tickLocal() {
  if (lastStatus === null || lastSinceMs === null) return;
  const elapsed = (Date.now() - lastSinceMs) / 1000;
  $("duration").textContent = fmtDuration(elapsed);
}

async function poll() {
  try {
    const res = await fetch("/api/status", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    applyStatus(data);
    lastFetchOk = true;
    const conn = $("conn");
    conn.textContent = "live";
    conn.dataset.state = "ok";
  } catch (err) {
    lastFetchOk = false;
    const conn = $("conn");
    conn.textContent = "offline";
    conn.dataset.state = "err";
  }
}

poll();
setInterval(poll, POLL_MS);
setInterval(tickLocal, 1000);
