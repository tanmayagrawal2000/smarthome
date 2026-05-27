# SmartHome

A modular home-automation server. Each automation lives in its own package
under `server/automations/`, shares the same SQLite database + virtualenv,
and exposes its endpoints under a dedicated URL prefix (e.g. `/api/grid/`).

## Automations

| Name                                 | Purpose                                                       |
| ------------------------------------ | ------------------------------------------------------------- |
| [`grid_monitor`](#grid_monitor)      | Detect grid power outages via an ESP32 heartbeat              |

## Project layout

```
SmartHome/
├── server/
│   ├── main.py                          orchestrator (mounts all automations)
│   ├── db.py                            shared SQLite primitives
│   ├── config.py                        per-automation config classes
│   ├── requirements.txt
│   ├── static/                          dashboard (HTML/CSS/JS)
│   └── automations/
│       └── grid_monitor/
│           ├── tables.py                schema + low-level queries
│           ├── service.py               business logic + background task
│           ├── routes.py                FastAPI router (prefix /api/grid)
│           └── seed_demo.py             demo-data seeder
├── deploy/
│   ├── start.ps1                        launcher (Windows)
│   └── start.sh                         launcher (Linux / macOS)
├── firmware/
│   └── grid_monitor/
│       └── grid_monitor.ino             ESP32 sketch
└── README.md
```

## Run the server

Requires Python 3.10+.

**First-time setup** (creates the virtualenv and installs dependencies):

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

```bash
cd server
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

**Start the server** — use the launcher in `deploy/` so you don't need to
remember the full uvicorn invocation. The scripts derive their paths from
their own location, so the repo can live anywhere:

```powershell
# Windows
.\deploy\start.ps1
```

```bash
# Linux / macOS
./deploy/start.sh
```

Override the bind host or port with env vars (defaults: `0.0.0.0:8000`):

```powershell
$env:SMARTHOME_PORT = 9000; .\deploy\start.ps1
```

```bash
SMARTHOME_PORT=9000 ./deploy/start.sh
```

Then open <http://localhost:8000/> on your phone or laptop. The SQLite
database (`server/smarthome.db`) is created automatically on first run, and
every automation's tables are created on startup.

## Adding a new automation

1. Create `server/automations/<name>/` with at least `__init__.py`,
   `tables.py`, `service.py`, `routes.py`.
2. Expose these names from `__init__.py`:
   - `router` — a `fastapi.APIRouter` (typically prefixed `/api/<name>`)
   - `init_schema()` — idempotent table creation
   - `lifespan_task()` — optional async coroutine to run for the app's
     lifetime (cancelled cleanly on shutdown)
3. Add the package to the `AUTOMATIONS` list in `server/main.py`.
4. If the automation has tunables, add a class in `server/config.py`.
5. Tables and API paths should be namespaced (e.g. `mything_events`,
   `/api/mything/...`) to avoid collisions with other automations.

---

## grid_monitor

Uses a grid-powered ESP32 as a "canary." It heartbeats the server every 5 s;
if heartbeats stop for 15 s the server flips state to OFF and records an
outage. A responsive web dashboard shows current status, today's stats, and
a collapsible Day/Week/Month history view.

```
[ESP32 on grid]  --POST /api/grid/heartbeat every 5s-->  [FastAPI + SQLite]
                                                                |
[Browser]  --GET /api/grid/status every 2s---------------->  HTML/CSS/JS
```

**Server host:** any always-on machine on the same LAN as the ESP32. A
Raspberry Pi on a small UPS is the recommended setup so the server itself
keeps running through the outage it's recording.

### Flash the ESP32

1. Open `firmware/grid_monitor/grid_monitor.ino` in the Arduino IDE.
2. Install the **ESP32 by Espressif Systems** board package
   (Boards Manager).
3. Edit the `CONFIG` block at the top:
   - `WIFI_SSID`, `WIFI_PASSWORD` — your Wi-Fi credentials.
   - `SERVER_URL` — `http://<server-LAN-IP>:8000/api/grid/heartbeat`.
4. Select your ESP32 board + COM port and flash.

Serial Monitor (115200 baud) will print `heartbeat code=200 ok=1` once per
cycle when things are working.

### End-to-end test (no ESP32 needed)

```powershell
curl -X POST http://localhost:8000/api/grid/heartbeat   # flips state to ON
curl http://localhost:8000/api/grid/status              # inspect JSON
# wait > 15s without sending → state flips back to OFF
```

### Seed demo data

```powershell
# stop the server first
cd C:\Projects\SmartHome\server
.\.venv\Scripts\python.exe -m automations.grid_monitor.seed_demo
```

Wipes `grid_events` + `grid_state` and inserts ~60 days of deterministic
demo history. Run as a module (`-m ...`) from the `server/` directory so
the relative imports resolve.

### API

| Method | Path                       | Purpose                                              |
| ------ | -------------------------- | ---------------------------------------------------- |
| POST   | `/api/grid/heartbeat`      | ESP32 calls this every 5 s.                          |
| GET    | `/api/grid/status`         | Dashboard polls this every 2 s. Current state + today's stats. |
| GET    | `/api/grid/stats?start&end`| Aggregated stats for an arbitrary ISO-8601 range.    |
| GET    | `/api/health`              | Liveness check (server-wide).                        |
| GET    | `/`                        | Dashboard.                                           |

### Notes

- All timestamps in the DB are stored as **UTC ISO-8601**.
- The "today" boundary for stats uses the **server's local timezone**.
- Back up the database by copying `server/smarthome.db` (WAL files
  `-wal` / `-shm` can be ignored when the server is stopped).
