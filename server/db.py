"""Shared SQLite primitives for all SmartHome automations.

Each automation owns its own tables (typically declared in
`automations/<name>/tables.py`) and reuses `connect()` from here so the
whole project stores everything in a single `smarthome.db` file.

Keep this module free of automation-specific schema or queries — those
belong inside the automation packages.
"""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "smarthome.db"


def utcnow_iso() -> str:
    """Current UTC time formatted as ISO-8601 to the second."""
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
