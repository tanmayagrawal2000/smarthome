"""Schema + low-level SQLite queries for the grid_monitor automation."""
import sqlite3
from datetime import datetime, timezone

from db import connect, utcnow_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS grid_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('on','off'))
);
CREATE INDEX IF NOT EXISTS idx_grid_events_timestamp ON grid_events(timestamp);

CREATE TABLE IF NOT EXISTS grid_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_status TEXT NOT NULL,
    since TEXT NOT NULL,
    last_heartbeat_at TEXT
);
"""


def init_schema() -> None:
    """Create tables + seed the single-row state record if missing."""
    with connect() as conn:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT id FROM grid_state WHERE id = 1").fetchone()
        if row is None:
            now = utcnow_iso()
            conn.execute(
                "INSERT INTO grid_state (id, current_status, since, last_heartbeat_at) "
                "VALUES (1, 'off', ?, NULL)",
                (now,),
            )
            conn.execute(
                "INSERT INTO grid_events (timestamp, status) VALUES (?, 'off')",
                (now,),
            )


def get_state() -> sqlite3.Row:
    with connect() as conn:
        return conn.execute("SELECT * FROM grid_state WHERE id = 1").fetchone()


def record_heartbeat() -> tuple[str, bool]:
    """Update last_heartbeat_at. If currently off, flip to on. Returns (status, flipped)."""
    now = utcnow_iso()
    with connect() as conn:
        row = conn.execute("SELECT current_status FROM grid_state WHERE id = 1").fetchone()
        flipped = False
        if row["current_status"] == "off":
            conn.execute(
                "UPDATE grid_state SET current_status='on', since=?, last_heartbeat_at=? WHERE id=1",
                (now, now),
            )
            conn.execute(
                "INSERT INTO grid_events (timestamp, status) VALUES (?, 'on')",
                (now,),
            )
            flipped = True
        else:
            conn.execute(
                "UPDATE grid_state SET last_heartbeat_at=? WHERE id=1",
                (now,),
            )
        return ("on", flipped)


def mark_off_if_stale(threshold_seconds: int) -> bool:
    """If state is 'on' but last_heartbeat is older than threshold, flip to 'off'.

    The event row records the true outage start (last_heartbeat_at) so historical
    stats are accurate, but state.since uses 'now' so the dashboard's live duration
    counter visibly resets to 0 on the flip.
    """
    now_dt = datetime.now(timezone.utc)
    with connect() as conn:
        row = conn.execute(
            "SELECT current_status, last_heartbeat_at FROM grid_state WHERE id = 1"
        ).fetchone()
        if row["current_status"] != "on":
            return False
        last_hb = row["last_heartbeat_at"]
        if last_hb is None:
            return False
        last_dt = datetime.fromisoformat(last_hb)
        if (now_dt - last_dt).total_seconds() <= threshold_seconds:
            return False
        event_iso = last_dt.isoformat(timespec="seconds")
        since_iso = now_dt.isoformat(timespec="seconds")
        conn.execute(
            "UPDATE grid_state SET current_status='off', since=? WHERE id=1",
            (since_iso,),
        )
        conn.execute(
            "INSERT INTO grid_events (timestamp, status) VALUES (?, 'off')",
            (event_iso,),
        )
        return True


def events_in_range(start_iso: str, end_iso: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT timestamp, status FROM grid_events "
            "WHERE timestamp >= ? AND timestamp < ? ORDER BY timestamp ASC",
            (start_iso, end_iso),
        ).fetchall()


def last_event_before(start_iso: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT timestamp, status FROM grid_events WHERE timestamp < ? "
            "ORDER BY timestamp DESC LIMIT 1",
            (start_iso,),
        ).fetchone()
