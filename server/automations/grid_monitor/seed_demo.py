"""Seed the grid_monitor tables with a realistic history of demo events.

Wipes grid_events + grid_state, then inserts ~HISTORY_DAYS days of generated
events plus a fixed schedule for today. Useful for screenshotting / demoing
the dashboard and the Day / Week / Month history views without waiting for
real heartbeats to accumulate.

Usage (stop the server first so the stale-watcher doesn't insert rows
mid-seed) — run as a module from the server/ directory so the relative
imports resolve cleanly:

    cd C:\\Projects\\SmartHome\\server
    .\\.venv\\Scripts\\python.exe -m automations.grid_monitor.seed_demo
"""
import random
from datetime import datetime, time, timedelta, timezone

from db import connect

from .tables import init_schema

HISTORY_DAYS = 60
RNG = random.Random(42)  # deterministic so the demo is reproducible

# Fixed schedule for today (minutes after local midnight, status).
# Events scheduled past "now" are skipped automatically.
TODAY_SCHEDULE = [
    (0,            "on"),
    (6 * 60 + 30,  "off"),
    (6 * 60 + 35,  "on"),
    (9 * 60,       "off"),
    (9 * 60 + 1,   "on"),
    (12 * 60 + 30, "off"),
    (12 * 60 + 45, "on"),
    (16 * 60,      "off"),
    (16 * 60 + 3,  "on"),
    (18 * 60 + 30, "off"),
    (19 * 60 + 15, "on"),
    (22 * 60 + 10, "off"),
    (22 * 60 + 12, "on"),
]


def _outages_for_day() -> list[tuple[int, int]]:
    """Return [(start_minute_of_day, duration_minutes), ...] for one historical day."""
    p = RNG.random()
    if p < 0.05:
        durations = []                                       # perfect day
    elif p < 0.60:
        durations = [RNG.randint(1, 5) for _ in range(RNG.choice([0, 1, 1, 2]))]
    elif p < 0.90:
        durations = [RNG.randint(2, 30) for _ in range(RNG.randint(2, 4))]
    else:
        durations = [RNG.randint(5, 60) for _ in range(RNG.randint(5, 9))]  # bad day

    outages = sorted((RNG.randint(6 * 60, 22 * 60), d) for d in durations)
    deduped: list[tuple[int, int]] = []
    for start, dur in outages:
        # drop overlaps with at least 5 min gap between outages
        if not deduped or start > deduped[-1][0] + deduped[-1][1] + 5:
            deduped.append((start, dur))
    return deduped


def _build_events(today_midnight_local: datetime, now_utc: datetime) -> list[tuple[datetime, str]]:
    events: list[tuple[datetime, str]] = []

    history_start_local = today_midnight_local - timedelta(days=HISTORY_DAYS)
    events.append((history_start_local.astimezone(timezone.utc), "on"))

    for days_ago in range(HISTORY_DAYS, 0, -1):
        day_local = today_midnight_local - timedelta(days=days_ago)
        for start_min, dur_min in _outages_for_day():
            off_local = day_local + timedelta(minutes=start_min)
            on_local = off_local + timedelta(minutes=dur_min)
            events.append((off_local.astimezone(timezone.utc), "off"))
            events.append((on_local.astimezone(timezone.utc), "on"))

    midnight_utc = today_midnight_local.astimezone(timezone.utc)
    now_offset_min = (now_utc - midnight_utc).total_seconds() / 60
    for offset_min, status in TODAY_SCHEDULE:
        if offset_min > now_offset_min:
            break
        events.append((midnight_utc + timedelta(minutes=offset_min), status))

    cleaned: list[tuple[datetime, str]] = []
    for ev in events:
        if cleaned and cleaned[-1][1] == ev[1]:
            continue
        cleaned.append(ev)
    return cleaned


def seed() -> None:
    init_schema()
    local_now = datetime.now().astimezone()
    today_midnight_local = datetime.combine(local_now.date(), time.min, tzinfo=local_now.tzinfo)
    now_utc = datetime.now(timezone.utc)

    events = _build_events(today_midnight_local, now_utc)
    if not events:
        events = [(now_utc, "on")]

    last_ts, last_status = events[-1]
    last_hb = now_utc if last_status == "on" else last_ts

    with connect() as conn:
        conn.execute("DELETE FROM grid_events")
        conn.execute("DELETE FROM grid_state")
        conn.executemany(
            "INSERT INTO grid_events (timestamp, status) VALUES (?, ?)",
            [(ts.isoformat(timespec="seconds"), status) for ts, status in events],
        )
        conn.execute(
            "INSERT INTO grid_state (id, current_status, since, last_heartbeat_at) "
            "VALUES (1, ?, ?, ?)",
            (
                last_status,
                last_ts.isoformat(timespec="seconds"),
                last_hb.isoformat(timespec="seconds"),
            ),
        )

    off_count = sum(1 for _, s in events if s == "off")
    print(f"Seeded {len(events)} events ({off_count} outages) across {HISTORY_DAYS}+ days.")
    print(f"First: {events[0][0].isoformat(timespec='seconds')} -> {events[0][1]}")
    print(f"Last:  {last_ts.isoformat(timespec='seconds')} -> {last_status}")


if __name__ == "__main__":
    seed()
