"""Grid power outage detector.

ESP32 powered from the grid pings /api/grid/heartbeat every few seconds.
When pings stop, the server infers an outage. Exposes a status endpoint
and a historical stats endpoint, both backed by a single SQLite events
log scoped to this automation's tables (`grid_events`, `grid_state`).

Public surface used by `main.py`:

- `router`         -- FastAPI APIRouter to include
- `init_schema`    -- create tables + seed initial state row
- `lifespan_task`  -- async background task to run for the app's lifetime
"""
from .routes import router
from .service import init_schema, lifespan_task

__all__ = ["router", "init_schema", "lifespan_task"]
