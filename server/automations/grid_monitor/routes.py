"""HTTP routes for the grid_monitor automation."""
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from .service import parse_iso, stats_for_range, today_stats
from .tables import get_state, record_heartbeat

router = APIRouter(prefix="/api/grid", tags=["grid_monitor"])


@router.post("/heartbeat")
async def heartbeat():
    status, flipped = record_heartbeat()
    return {"status": status, "flipped": flipped}


@router.get("/status")
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
        "today": today_stats(),
    }


@router.get("/stats")
async def stats(
    start: str = Query(..., description="ISO-8601 start of the range (inclusive)"),
    end: str = Query(..., description="ISO-8601 end of the range (exclusive)"),
):
    try:
        start_dt = parse_iso(start)
        end_dt = parse_iso(end)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid datetime: {exc}")
    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="end must be after start")
    start_utc = start_dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    end_utc = end_dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    return stats_for_range(start_utc, end_utc)
