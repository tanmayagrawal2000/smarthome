"""Business logic for the grid_monitor automation.

Layers above the table-level queries in `tables.py`:
- background task (`lifespan_task`) that drives the stale-watcher
- ISO parsing helper that copes with browsers' "...Z" suffix
- `_stats_for_range` shared between today + history endpoints
"""
import asyncio
from datetime import datetime, time, timezone

from config import GridMonitor
from .tables import (
    events_in_range,
    init_schema as _init_schema,
    last_event_before,
    mark_off_if_stale,
)


def init_schema() -> None:
    _init_schema()


async def lifespan_task() -> None:
    """Run for the app's lifetime; cancelled cleanly on shutdown."""
    while True:
        try:
            mark_off_if_stale(GridMonitor.OFFLINE_THRESHOLD_S)
        except Exception as exc:
            print(f"[grid_monitor.stale_watcher] {exc!r}")
        await asyncio.sleep(GridMonitor.CHECK_INTERVAL_S)


def parse_iso(s: str) -> datetime:
    """Parse an ISO-8601 datetime, tolerating the 'Z' suffix.

    Python 3.10's `datetime.fromisoformat` rejects 'Z'; JavaScript's
    `toISOString` always emits it. Normalize here so every endpoint that
    accepts user-provided timestamps handles both.
    """
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def local_midnight_utc_iso() -> str:
    """ISO-8601 UTC string for the most recent local-midnight boundary."""
    local_now = datetime.now().astimezone()
    local_midnight = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    return local_midnight.astimezone(timezone.utc).isoformat(timespec="seconds")


def stats_for_range(start_iso: str, end_iso: str) -> dict:
    """Compute uptime/downtime/segments for [start_iso, end_iso).

    end_iso is clamped at "now" so future-window queries return data up to
    the present rather than padding with empty time.
    """
    start_dt = datetime.fromisoformat(start_iso)
    end_dt = datetime.fromisoformat(end_iso)
    now_dt = datetime.now(timezone.utc)
    effective_end = min(end_dt, now_dt)

    raw: list[tuple[datetime, str]] = []
    prior = last_event_before(start_iso)
    if prior is not None:
        raw.append((start_dt, prior["status"]))
    for row in events_in_range(start_iso, effective_end.isoformat(timespec="seconds")):
        raw.append((datetime.fromisoformat(row["timestamp"]), row["status"]))

    empty = {
        "uptime_seconds": 0,
        "downtime_seconds": 0,
        "outage_count": 0,
        "uptime_percent": 0.0,
        "avg_outage_seconds": 0,
        "longest_outage_seconds": 0,
        "outages": [],
        "segments": [],
        "window_start": start_iso,
        "window_end": effective_end.isoformat(timespec="seconds"),
    }
    if not raw:
        return empty

    uptime = 0.0
    downtime = 0.0
    outages: list[dict] = []
    segments: list[dict] = []
    for i, (ts, status) in enumerate(raw):
        seg_end = raw[i + 1][0] if i + 1 < len(raw) else effective_end
        duration = max(0.0, (seg_end - ts).total_seconds())
        ongoing = (i + 1 == len(raw)) and end_dt > now_dt
        segments.append(
            {
                "start": ts.isoformat(timespec="seconds"),
                "end": seg_end.isoformat(timespec="seconds"),
                "duration_seconds": int(duration),
                "status": status,
                "ongoing": ongoing,
            }
        )
        if status == "on":
            uptime += duration
        else:
            downtime += duration
            outages.append(
                {
                    "start": ts.isoformat(timespec="seconds"),
                    "end": seg_end.isoformat(timespec="seconds"),
                    "duration_seconds": int(duration),
                    "ongoing": ongoing,
                }
            )

    total = uptime + downtime
    uptime_percent = round((uptime / total) * 100, 2) if total > 0 else 0.0
    outage_durations = [o["duration_seconds"] for o in outages]
    avg_outage = int(sum(outage_durations) / len(outage_durations)) if outage_durations else 0
    longest_outage = max(outage_durations) if outage_durations else 0

    return {
        "uptime_seconds": int(uptime),
        "downtime_seconds": int(downtime),
        "outage_count": len(outages),
        "uptime_percent": uptime_percent,
        "avg_outage_seconds": avg_outage,
        "longest_outage_seconds": longest_outage,
        "outages": outages,
        "segments": segments,
        "window_start": start_iso,
        "window_end": effective_end.isoformat(timespec="seconds"),
    }


def today_stats() -> dict:
    start_iso = local_midnight_utc_iso()
    end_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return stats_for_range(start_iso, end_iso)
