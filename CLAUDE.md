# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

All commands are PowerShell on Windows.

**Run the server** (mounts every automation under its own `/api/<name>/` prefix and serves the dashboard at `/`). Use the launcher in `deploy/` — it derives paths from its own location, so the long uvicorn incantation isn't needed:

```powershell
# Windows
.\deploy\start.ps1

# Linux / macOS
./deploy/start.sh

# Override host/port via env vars (both scripts):
$env:SMARTHOME_PORT = 9000; .\deploy\start.ps1
SMARTHOME_PORT=9000 ./deploy/start.sh
```

The raw uvicorn command is still available if you need it (the launcher just shells out to this):

```powershell
C:\Projects\SmartHome\server\.venv\Scripts\python.exe -m uvicorn --app-dir C:\Projects\SmartHome\server main:app --host 0.0.0.0 --port 8000
```

Stop with `Ctrl+C`, or kill by port:

```powershell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force
```

**Recreate the venv** (only on fresh clone or if `server\.venv\` is gone):

```powershell
cd C:\Projects\SmartHome\server
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

**End-to-end smoke test for the grid_monitor automation** — start the server, then:

```powershell
curl -X POST http://127.0.0.1:8000/api/grid/heartbeat   # flips state to ON
curl http://127.0.0.1:8000/api/grid/status              # inspect JSON
# wait > 15s without sending heartbeats → state flips back to OFF
```

**Seed demo data** for grid_monitor (wipes its tables and re-inserts ~60 days of deterministic history). Must be invoked as a module so the package-relative imports resolve:

```powershell
# stop the server first
cd C:\Projects\SmartHome\server
.\.venv\Scripts\python.exe -m automations.grid_monitor.seed_demo
```

**Reset the entire SQLite database** (wipes `smarthome.db` + WAL/SHM siblings; refuses to run while uvicorn is bound to port 8000):

```powershell
.\.venv\Scripts\python.exe reset_db.py            # empty DB
.\.venv\Scripts\python.exe reset_db.py --seed     # + re-init schemas + run every automation's seed_demo
```

**Probe a historical stats range** (Day/Week/Month all use this):

```powershell
$start = "2026-05-01T00:00:00+05:30"; $end = "2026-06-01T00:00:00+05:30"
curl "http://127.0.0.1:8000/api/grid/stats?start=$([uri]::EscapeDataString($start))&end=$([uri]::EscapeDataString($end))"
```

There are no unit tests in this repo; verification is the manual flow above. To statically check Python wiring after a refactor:

```powershell
& C:\Projects\SmartHome\server\.venv\Scripts\python.exe -c "import main; print(len(main.app.routes), 'routes')"
```

## Architecture

The project is structured as a **single FastAPI app + multiple automation packages**. `server/main.py` is a thin orchestrator — it imports each automation from `server/automations/<name>/`, calls its `init_schema()` to create tables, includes its `router`, and starts its optional `lifespan_task()` as an asyncio task. Adding an automation = creating a new package and appending it to the `AUTOMATIONS` list in `main.py`. The orchestrator deliberately knows nothing automation-specific.

```
server/
├── main.py                     orchestrator — iterates AUTOMATIONS list
├── db.py                       shared SQLite primitives (connect, utcnow_iso)
├── config.py                   one nested class per automation
├── static/                     dashboard (currently grid_monitor only)
└── automations/
    └── grid_monitor/
        ├── __init__.py         re-exports router, init_schema, lifespan_task
        ├── tables.py           SCHEMA + low-level SQLite queries
        ├── service.py          business logic, stats helpers, background task
        ├── routes.py           APIRouter(prefix="/api/grid")
        └── seed_demo.py        run via `python -m automations.grid_monitor.seed_demo`

firmware/
└── grid_monitor/
    └── grid_monitor.ino        ESP32 sketch; SERVER_URL ends /api/grid/heartbeat
```

**Shared modules (used by every automation):**

- `server/db.py` — `connect()` context manager and `utcnow_iso()` only. No automation-specific schema or queries belong here.
- `server/config.py` — one class per automation (currently just `GridMonitor`). Services import the specific class they need.

**Each automation package** exposes three names from its `__init__.py`: `router`, `init_schema`, `lifespan_task`. Internal layout is `tables.py` (DDL + low-level SQLite queries), `service.py` (business logic / aggregation / background coroutine), `routes.py` (FastAPI `APIRouter`). Each automation also namespaces its SQLite tables (e.g. `grid_events`, `grid_state`) and URL paths (e.g. `/api/grid/...`) so multiple automations can coexist in one DB without collisions.

### Adding a new automation

1. Create `server/automations/<name>/` with `__init__.py`, `tables.py`, `service.py`, `routes.py`.
2. In `routes.py`, define `router = APIRouter(prefix="/api/<name>", tags=["<name>"])` and attach the HTTP endpoints to it.
3. In `tables.py`, define a `SCHEMA` SQL string and an `init_schema()` function that runs the DDL (idempotent — use `CREATE TABLE IF NOT EXISTS`) and seeds any required initial rows.
4. In `service.py`, put business logic + an `async def lifespan_task()` if you need a background coroutine.
5. Re-export `router`, `init_schema`, and `lifespan_task` from the package `__init__.py` (matching `grid_monitor/__init__.py` line-for-line is fine).
6. Append the package to the `AUTOMATIONS` list in `server/main.py`. No other change is needed there.
7. If the automation has tunable constants, add a class to `server/config.py` (mirror the `GridMonitor` shape).
8. Verify with `python -c "import main; print(len(main.app.routes))"` — the new route count should reflect the added endpoints.

### grid_monitor

The core insight is that **the ESP32 is the sensor**, not just a client. It's wired to grid power, so when the grid drops, the ESP32 dies and stops calling `/api/grid/heartbeat`. The server infers grid state purely from heartbeat arrival times — there is no explicit "off" signal. The server itself must be on a UPS / battery / cloud host so it survives the outage it's recording.

**Control flow:**

- `tables.record_heartbeat()` runs on every `POST /api/grid/heartbeat`. It updates `grid_state.last_heartbeat_at`; if `current_status` was `off`, it also flips to `on` and appends an `on` event.
- `service.lifespan_task()` is an asyncio coroutine started by `main.py`'s `lifespan` context manager. Every `GridMonitor.CHECK_INTERVAL_S` (2 s) it calls `tables.mark_off_if_stale()`, which flips state to `off` if `last_heartbeat_at` is older than `GridMonitor.OFFLINE_THRESHOLD_S` (15 s, i.e. 3× the ESP32's 5 s ping interval to absorb single dropped packets).
- `/api/grid/status` reads the single-row `grid_state` table for the fast path, then calls `service.today_stats()` for the day's segments + aggregates.
- `/api/grid/stats?start=…&end=…` exposes the same `service.stats_for_range()` helper for arbitrary ranges. It clamps `end` at "now" so future-window queries still return valid data up to the present.
- All shared range logic lives in `service.stats_for_range(start_iso, end_iso)`. It uses `last_event_before` to determine the status at the start of the window, then `events_in_range` to walk transitions. Both today and history go through this helper — change the aggregation shape in one place and both views update.

**Database** uses two SQLite tables, both prefixed. `grid_state` is a single-row "current snapshot" — fast to read on every dashboard poll. `grid_events` is an append-only log of transitions; range queries replay it. All timestamps in the DB are **UTC ISO-8601**; the "today" boundary uses the server's **local timezone** (`service.local_midnight_utc_iso()`). `mark_off_if_stale` deliberately uses **two different timestamps** when flipping ON→OFF: the `grid_events` row records the true outage start (`last_heartbeat_at`) for accurate history, but `grid_state.since` is reset to `now` so the dashboard's live duration counter restarts at 0 on the visible flip. Changing this requires updating both places together.

**Frontend (`server/static/`)** is plain HTML/CSS/vanilla JS — no build step, no framework. `app.js` polls `/api/grid/status` every 2 s and uses a 1 s local interval (`tickLocal()`) only to advance the live duration counter between polls; all derived state (today's stats, outage list) comes from the server. Status styling is driven by the `data-status` attribute on the `.app` root in `index.html` — CSS selectors like `.app[data-status="on"] .hero__dot` keyframe-animate the pulsing dot. To add a new state-driven visual, add a `data-status="..."` branch in CSS rather than toggling classes from JS.

The status timeline pill bar is rendered by `renderTimeline(barEl, axisEl, data)` and is reused for both the Today view and the History section's range timeline (segments + window_start/end have the same shape). Tooltips/axis labels switch from time-only to date-prefixed when the window spans more than 36 hours. The History `<details>` element is collapsed by default and only triggers its first `/api/grid/stats` fetch on the `toggle` event — opening it lazily, refetching on each re-open.

**ESP32 firmware (`firmware/grid_monitor/grid_monitor.ino`)** is intentionally minimal: connect Wi-Fi, `POST {}` to `SERVER_URL` every 5 s, reconnect on Wi-Fi drop. The body is empty by design — the *fact* of the request is the signal. Edit the `CONFIG` block at the top with real Wi-Fi credentials and the server's LAN IP, then flash via Arduino IDE with the ESP32 board package.

## Things to watch for when editing

- All tunable backend timing values (heartbeat interval, offline threshold, watcher tick) live in `server/config.py` under the `GridMonitor` class. Services import via `from config import GridMonitor`; don't hardcode the constants back into service or route code.
- The static-files mount `app.mount("/", StaticFiles(...), html=True)` in `main.py` is a catch-all and **must stay last**. Any route added after it will be unreachable.
- New automations must namespace their tables and API paths. If you add an automation that wants `events` or `status`, prefix it (e.g. `mything_events`, `/api/mything/status`) so it doesn't collide with `grid_monitor`'s.
- The dashboard at `static/` is currently grid_monitor-only. If a new automation needs UI, either add a dedicated page or restructure the frontend to support tabs — don't conflate routes between automations in `app.js`.
- If you change `HEARTBEAT_INTERVAL_S` in `config.py`, also change `HEARTBEAT_INTERVAL_MS` in `firmware/grid_monitor/grid_monitor.ino` (×1000) and keep `OFFLINE_THRESHOLD_S` at roughly 3× the heartbeat interval. `POLL_MS` in `server/static/app.js` only affects how snappy the dashboard feels.
- Wi-Fi credentials in `firmware/grid_monitor/grid_monitor.ino` are placeholders in the committed copy. Never commit real credentials — keep the change unstaged, or split into a `firmware/grid_monitor/secrets.h` that is gitignored and `#include`d.
- The SQLite DB (`server/smarthome.db` + `-wal`, `-shm`) is gitignored. To reset state in development, stop the server and delete those files — every automation's `init_schema()` will recreate its tables on next start. To populate with realistic demo history instead of starting empty, run the per-automation seeder (e.g. `python -m automations.grid_monitor.seed_demo`).
- The project targets **Python 3.10**, whose `datetime.fromisoformat` does **not** accept the `Z` suffix that JavaScript's `Date.prototype.toISOString` always emits. The `parse_iso` helper in `automations/grid_monitor/service.py` normalizes `Z` to `+00:00` before parsing — any new endpoint that accepts ISO datetimes from the browser should adopt the same pattern (or be rewritten if the project ever moves to 3.11+).
- `seed_demo.py` uses a fixed RNG seed (`random.Random(42)`) so the demo dataset is reproducible across runs. Change the seed if you want different demo data; do not commit it as an unseeded `random.random()` call.
