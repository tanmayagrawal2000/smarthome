const POLL_MS = 2000;

const $ = (id) => document.getElementById(id);
const app = document.querySelector(".app");

let lastStatus = null;
let lastSinceMs = null;

const FMT_TIME = new Intl.DateTimeFormat([], {
  hour: "numeric",
  minute: "2-digit",
  second: "2-digit",
  hour12: true,
});

const FMT_TIME_SHORT = new Intl.DateTimeFormat([], {
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

const FMT_FULL = new Intl.DateTimeFormat([], {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

function isSameLocalDay(a, b) {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

function fmtDuration(totalSec) {
  const s = Math.max(0, Math.floor(totalSec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return `${pad(h)}:${pad(m)}:${pad(sec)}`;
}

function fmtTime(iso) {
  if (!iso) return "—";
  try {
    return FMT_TIME.format(new Date(iso));
  } catch {
    return iso;
  }
}

function fmtTimeShort(iso) {
  if (!iso) return "—";
  try {
    return FMT_TIME_SHORT.format(new Date(iso));
  } catch {
    return iso;
  }
}

function fmtFull(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return isSameLocalDay(d, new Date())
      ? FMT_TIME_SHORT.format(d)
      : FMT_FULL.format(d);
  } catch {
    return iso;
  }
}

const FMT_DATE = new Intl.DateTimeFormat([], {
  month: "short",
  day: "numeric",
});

function fmtDateShort(iso) {
  if (!iso) return "—";
  try {
    return FMT_DATE.format(new Date(iso));
  } catch {
    return iso;
  }
}

function renderTimeline(barEl, axisEl, data) {
  const segments = (data && data.segments) || [];

  if (segments.length === 0) {
    barEl.innerHTML = "";
    axisEl.innerHTML = "";
    return;
  }

  const windowStart = new Date(data.window_start).getTime();
  const windowEnd = new Date(data.window_end).getTime();
  const totalSec = Math.max(1, (windowEnd - windowStart) / 1000);
  const multiDay = (windowEnd - windowStart) > 36 * 60 * 60 * 1000;

  const tipTime = multiDay
    ? (iso) => `${fmtDateShort(iso)} ${fmtTimeShort(iso)}`
    : fmtTimeShort;

  const html = segments
    .map((s) => {
      const cls =
        "timeline__seg " +
        (s.status === "on" ? "timeline__seg--on" : "timeline__seg--off");
      const pct = (s.duration_seconds / totalSec) * 100;
      const w = pct.toFixed(3) + "%";
      const tip = `${s.status.toUpperCase()} ${tipTime(s.start)}–${tipTime(
        s.end
      )} (${fmtDuration(s.duration_seconds)})`;
      return `<div class="${cls}" style="width:${w}" title="${tip}"></div>`;
    })
    .join("");
  barEl.innerHTML = html;

  const fmtAxis = multiDay ? fmtDateShort : fmtTimeShort;
  axisEl.innerHTML =
    `<span>${fmtAxis(data.window_start)}</span>` +
    `<span>${fmtAxis(data.window_end)}</span>`;
}

function renderOutages(outages) {
  const list = $("outage-list");
  if (!outages || outages.length === 0) {
    list.innerHTML = '<li class="outages__empty">No outages today</li>';
    return;
  }
  const items = outages
    .slice()
    .reverse()
    .map((o) => {
      const cls = o.ongoing ? " class=\"outage--ongoing\"" : "";
      const range = o.ongoing
        ? `${fmtTimeShort(o.start)} – now`
        : `${fmtTimeShort(o.start)} – ${fmtTimeShort(o.end)}`;
      const dur = o.ongoing ? "ongoing" : fmtDuration(o.duration_seconds);
      return `<li${cls}>
        <span class="outage__time">${range}</span>
        <span class="outage__duration">${dur}</span>
      </li>`;
    })
    .join("");
  list.innerHTML = items;
}

function applyStatus(data) {
  const status = data.status;
  app.dataset.status = status;
  $("status").textContent = status === "on" ? "ON" : "OFF";
  $("since-line").textContent = "since " + fmtFull(data.since);
  $("last-heartbeat").textContent = "last ping " + fmtFull(data.last_heartbeat_at);

  lastStatus = status;
  lastSinceMs = data.since ? new Date(data.since).getTime() : Date.now();

  const today = data.today || {};
  $("stat-downtime").textContent = fmtDuration(today.downtime_seconds || 0);
  $("stat-outage-count").textContent = String(today.outage_count || 0);

  renderTimeline($("timeline-bar"), $("timeline-axis"), today);
  renderOutages(today.outages || []);
}

function tickLocal() {
  if (lastStatus === null || lastSinceMs === null) return;
  const elapsed = (Date.now() - lastSinceMs) / 1000;
  $("duration").textContent = fmtDuration(elapsed);
}

async function poll() {
  try {
    const res = await fetch("/api/grid/status", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    applyStatus(data);
    const conn = $("conn");
    conn.textContent = "live";
    conn.dataset.state = "ok";
  } catch (err) {
    const conn = $("conn");
    conn.textContent = "offline";
    conn.dataset.state = "err";
  }
}

// ===== History section =====

let historyRange = "day";
const historyDateInput = $("history-date");

function pad2(n) {
  return String(n).padStart(2, "0");
}

function todayLocalDateStr() {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
}

function todayLocalMonthStr() {
  const d = new Date();
  return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
}

function setHistoryInputForRange(range, preserveDate = false) {
  if (range === "month") {
    if (!preserveDate || !historyDateInput.value) {
      historyDateInput.type = "month";
      historyDateInput.value = todayLocalMonthStr();
    } else {
      const v = historyDateInput.value.slice(0, 7);
      historyDateInput.type = "month";
      historyDateInput.value = v;
    }
  } else {
    if (historyDateInput.type === "month" || !preserveDate || !historyDateInput.value) {
      historyDateInput.type = "date";
      historyDateInput.value = todayLocalDateStr();
    } else {
      historyDateInput.type = "date";
    }
  }
}

function computeRangeBounds() {
  const v = historyDateInput.value;
  if (!v) return null;
  let start, end;
  if (historyRange === "day") {
    const [y, m, d] = v.split("-").map(Number);
    start = new Date(y, m - 1, d, 0, 0, 0);
    end = new Date(y, m - 1, d + 1, 0, 0, 0);
  } else if (historyRange === "week") {
    const [y, m, d] = v.split("-").map(Number);
    const picked = new Date(y, m - 1, d);
    const dow = picked.getDay(); // 0=Sun ... 6=Sat
    const mondayOffset = (dow + 6) % 7; // 0=Mon ... 6=Sun
    start = new Date(picked.getFullYear(), picked.getMonth(), picked.getDate() - mondayOffset);
    end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + 7);
  } else {
    const [y, m] = v.split("-").map(Number);
    start = new Date(y, m - 1, 1, 0, 0, 0);
    end = new Date(y, m, 1, 0, 0, 0);
  }
  return { start, end };
}

const FMT_RANGE_LONG = new Intl.DateTimeFormat([], {
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
});
const FMT_RANGE_MONTH = new Intl.DateTimeFormat([], {
  month: "long",
  year: "numeric",
});

function formatRangeLabel(start, end) {
  if (historyRange === "day") {
    return FMT_RANGE_LONG.format(start);
  }
  if (historyRange === "week") {
    const lastDay = new Date(end.getTime() - 1);
    return `${fmtDateShort(start.toISOString())} – ${fmtDateShort(
      lastDay.toISOString()
    )}, ${start.getFullYear()}`;
  }
  return FMT_RANGE_MONTH.format(start);
}

async function fetchHistory() {
  const bounds = computeRangeBounds();
  if (!bounds) return;
  const { start, end } = bounds;
  $("history-range-label").textContent = formatRangeLabel(start, end);
  try {
    const url = `/api/grid/stats?start=${encodeURIComponent(
      start.toISOString()
    )}&end=${encodeURIComponent(end.toISOString())}`;
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error("HTTP " + r.status);
    const data = await r.json();
    renderHistory(data);
  } catch (err) {
    $("history-uptime-pct").textContent = "—";
    $("history-uptime-time").textContent = "—";
    $("history-downtime").textContent = "—";
    $("history-outages").textContent = "—";
    $("history-longest").textContent = "—";
    $("history-avg").textContent = "avg —";
  }
}

function renderHistory(data) {
  renderTimeline(
    $("history-timeline-bar"),
    $("history-timeline-axis"),
    data
  );
  $("history-uptime-pct").textContent =
    (data.uptime_percent ?? 0).toFixed(2) + "%";
  $("history-uptime-time").textContent = fmtDuration(data.uptime_seconds || 0);
  $("history-downtime").textContent = fmtDuration(data.downtime_seconds || 0);
  $("history-outages").textContent = String(data.outage_count || 0);
  $("history-longest").textContent = fmtDuration(
    data.longest_outage_seconds || 0
  );
  $("history-avg").textContent =
    "avg " + fmtDuration(data.avg_outage_seconds || 0);
}

document.querySelectorAll(".history__tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document
      .querySelectorAll(".history__tab")
      .forEach((b) => b.classList.remove("is-active"));
    btn.classList.add("is-active");
    historyRange = btn.dataset.range;
    setHistoryInputForRange(historyRange, true);
    fetchHistory();
  });
});
historyDateInput.addEventListener("change", fetchHistory);

setHistoryInputForRange("day");

const historyDetails = document.getElementById("history-details");
historyDetails.addEventListener("toggle", () => {
  if (historyDetails.open) fetchHistory();
});

poll();
setInterval(poll, POLL_MS);
setInterval(tickLocal, 1000);
