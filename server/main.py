import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, time, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from db import (
    events_since,
    get_state,
    init_db,
    last_event_before,
    mark_off_if_stale,
    record_heartbeat,
)

HEARTBEAT_INTERVAL_S = 5
OFFLINE_THRESHOLD_S = 15
CHECK_INTERVAL_S = 2

STATIC_DIR = Path(__file__).parent / "static"


async def stale_watcher() -> None:
    while True:
        try:
            mark_off_if_stale(OFFLINE_THRESHOLD_S)
        except Exception as exc:
            print(f"[stale_watcher] {exc!r}")
        await asyncio.sleep(CHECK_INTERVAL_S)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(stale_watcher())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)


@app.post("/api/heartbeat")
async def heartbeat():
    status, flipped = record_heartbeat()
    return {"status": status, "flipped": flipped}


def _local_midnight_utc_iso() -> str:
    local_now = datetime.now().astimezone()
    local_midnight = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    return local_midnight.astimezone(timezone.utc).isoformat(timespec="seconds")


def _today_stats() -> dict:
    start_iso = _local_midnight_utc_iso()
    start_dt = datetime.fromisoformat(start_iso)
    now_dt = datetime.now(timezone.utc)

    segments: list[tuple[datetime, str]] = []
    prior = last_event_before(start_iso)
    if prior is not None:
        segments.append((start_dt, prior["status"]))
    for row in events_since(start_iso):
        segments.append((datetime.fromisoformat(row["timestamp"]), row["status"]))

    if not segments:
        return {
            "uptime_seconds": 0,
            "downtime_seconds": 0,
            "outage_count": 0,
            "uptime_percent": 0.0,
            "outages": [],
        }

    uptime = 0.0
    downtime = 0.0
    outages: list[dict] = []
    for i, (ts, status) in enumerate(segments):
        end = segments[i + 1][0] if i + 1 < len(segments) else now_dt
        duration = max(0.0, (end - ts).total_seconds())
        if status == "on":
            uptime += duration
        else:
            downtime += duration
            outages.append(
                {
                    "start": ts.isoformat(timespec="seconds"),
                    "duration_seconds": int(duration),
                    "ongoing": i + 1 == len(segments),
                }
            )

    total = uptime + downtime
    percent = round((uptime / total) * 100, 2) if total > 0 else 0.0
    outage_count = sum(1 for _, s in segments if s == "off")
    return {
        "uptime_seconds": int(uptime),
        "downtime_seconds": int(downtime),
        "outage_count": outage_count,
        "uptime_percent": percent,
        "outages": outages,
    }


@app.get("/api/status")
async def status():
    st = get_state()
    since_dt = datetime.fromisoformat(st["since"])
    now_dt = datetime.now(timezone.utc)
    duration = int((now_dt - since_dt).total_seconds())
    return {
        "status": st["current_status"],
        "since": st["since"],
        "duration_seconds": max(0, duration),
        "last_heartbeat_at": st["last_heartbeat_at"],
        "server_time": now_dt.isoformat(timespec="seconds"),
        "today": _today_stats(),
    }


@app.get("/api/health")
async def health():
    return JSONResponse({"ok": True})


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
