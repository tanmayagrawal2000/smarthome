import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "smarthome.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('on','off'))
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);

CREATE TABLE IF NOT EXISTS state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    current_status TEXT NOT NULL,
    since TEXT NOT NULL,
    last_heartbeat_at TEXT
);
"""


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        row = conn.execute("SELECT id FROM state WHERE id = 1").fetchone()
        if row is None:
            now = utcnow_iso()
            conn.execute(
                "INSERT INTO state (id, current_status, since, last_heartbeat_at) "
                "VALUES (1, 'off', ?, NULL)",
                (now,),
            )
            conn.execute(
                "INSERT INTO events (timestamp, status) VALUES (?, 'off')",
                (now,),
            )


def get_state() -> sqlite3.Row:
    with connect() as conn:
        return conn.execute("SELECT * FROM state WHERE id = 1").fetchone()


def record_heartbeat() -> tuple[str, bool]:
    """Update last_heartbeat_at. If currently off, flip to on. Returns (status, flipped)."""
    now = utcnow_iso()
    with connect() as conn:
        row = conn.execute("SELECT current_status FROM state WHERE id = 1").fetchone()
        flipped = False
        if row["current_status"] == "off":
            conn.execute(
                "UPDATE state SET current_status='on', since=?, last_heartbeat_at=? WHERE id=1",
                (now, now),
            )
            conn.execute(
                "INSERT INTO events (timestamp, status) VALUES (?, 'on')",
                (now,),
            )
            flipped = True
        else:
            conn.execute(
                "UPDATE state SET last_heartbeat_at=? WHERE id=1",
                (now,),
            )
        return ("on", flipped)


def mark_off_if_stale(threshold_seconds: int) -> bool:
    """If state is 'on' but last_heartbeat is older than threshold, flip to 'off'. Returns True if flipped."""
    now_dt = datetime.now(timezone.utc)
    with connect() as conn:
        row = conn.execute(
            "SELECT current_status, last_heartbeat_at FROM state WHERE id = 1"
        ).fetchone()
        if row["current_status"] != "on":
            return False
        last_hb = row["last_heartbeat_at"]
        if last_hb is None:
            return False
        last_dt = datetime.fromisoformat(last_hb)
        if (now_dt - last_dt).total_seconds() <= threshold_seconds:
            return False
        flip_at = last_dt  # treat outage as starting when heartbeats stopped
        flip_iso = flip_at.isoformat(timespec="seconds")
        conn.execute(
            "UPDATE state SET current_status='off', since=? WHERE id=1",
            (flip_iso,),
        )
        conn.execute(
            "INSERT INTO events (timestamp, status) VALUES (?, 'off')",
            (flip_iso,),
        )
        return True


def events_since(start_iso: str) -> list[sqlite3.Row]:
    with connect() as conn:
        return conn.execute(
            "SELECT timestamp, status FROM events WHERE timestamp >= ? ORDER BY timestamp ASC",
            (start_iso,),
        ).fetchall()


def last_event_before(start_iso: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT timestamp, status FROM events WHERE timestamp < ? ORDER BY timestamp DESC LIMIT 1",
            (start_iso,),
        ).fetchone()
