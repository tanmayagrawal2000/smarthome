# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

All commands are PowerShell on Windows.

**Run the server** (serves both the API and the dashboard):

```powershell
C:\Projects\SmartHome\server\.venv\Scripts\python.exe -m uvicorn --app-dir C:\Projects\SmartHome\server main:app --host 0.0.0.0 --port 8000
```

Dashboard at `http://127.0.0.1:8000/`. Stop with `Ctrl+C`, or kill by port:

```powershell
Stop-Process -Id (Get-NetTCPConnection -LocalPort 8000).OwningProcess -Force
```

**Recreate the venv** (only on fresh clone or if `server\.venv\` is gone):

```powershell
cd C:\Projects\SmartHome\server
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

**End-to-end smoke test without an ESP32** — start the server, then:

```powershell
curl -X POST http://127.0.0.1:8000/api/heartbeat   # flips state to ON
curl http://127.0.0.1:8000/api/status              # inspect JSON
# wait > 15s without sending heartbeats → state flips back to OFF
```

There are no unit tests in this repo; verification is the manual flow above.

## Architecture

The core insight is that **the ESP32 is the sensor**, not just a client. It's wired to grid power, so when the grid drops, the ESP32 dies and stops calling `/api/heartbeat`. The server infers grid state purely from heartbeat arrival times — there is no explicit "off" signal. The server itself must be on a UPS / battery / cloud host so it survives the outage it's recording.

**Control flow (`server/main.py`):**

- `record_heartbeat()` is called on every `POST /api/heartbeat`. It updates `state.last_heartbeat_at`. If `current_status` was `off`, it also flips to `on` and appends an `on` event.
- `stale_watcher()` is an asyncio task started by the FastAPI `lifespan` context manager. Every `CHECK_INTERVAL_S` (2 s) it calls `mark_off_if_stale()`, which flips state to `off` if `last_heartbeat_at` is older than `OFFLINE_THRESHOLD_S` (15 s, i.e. 3× the ESP32's 5 s ping interval to absorb single dropped packets).
- `/api/status` reads the single-row `state` table for the fast path, then computes today's stats by walking the `events` log from local midnight forward.

**Database (`server/db.py`)** uses two SQLite tables. `state` is a single-row "current snapshot" — fast to read on every dashboard poll. `events` is an append-only log of transitions; today's-stats queries replay it. All timestamps in the DB are **UTC ISO-8601**; the "today" boundary uses the server's **local timezone** (`_local_midnight_utc_iso()` in `main.py`). `mark_off_if_stale` intentionally attributes the outage start to `last_heartbeat_at`, not "now," so the recorded outage start reflects when the grid likely failed — not when the watcher noticed.

**Frontend (`server/static/`)** is plain HTML/CSS/vanilla JS — no build step, no framework. `app.js` polls `/api/status` every 2 s and uses a 1 s local interval (`tickLocal()`) only to advance the live duration counter between polls; all derived state (today's stats, outage list) comes from the server. Status styling is driven by the `data-status` attribute on the `.app` root in `index.html` — CSS selectors like `.app[data-status="on"] .hero__dot` keyframe-animate the pulsing dot. To add a new state-driven visual, add a `data-status="..."` branch in CSS rather than toggling classes from JS.

**ESP32 firmware (`firmware/grid_monitor.ino`)** is intentionally minimal: connect Wi-Fi, `POST {}` to `SERVER_URL` every 5 s, reconnect on Wi-Fi drop. The body is empty by design — the *fact* of the request is the signal. Edit the `CONFIG` block at the top with real Wi-Fi credentials and the server's LAN IP, then flash via Arduino IDE with the ESP32 board package.

## Things to watch for when editing

- The static-files mount `app.mount("/", StaticFiles(...), html=True)` in `main.py` is a catch-all and **must stay last**. Any route added after it will be unreachable.
- If you change `HEARTBEAT_INTERVAL_S` in the firmware, also change `OFFLINE_THRESHOLD_S` in `server/main.py` (keep the ~3× ratio) and the `POLL_MS` in `server/static/app.js` if you want the UI to feel as live.
- Wi-Fi credentials in `firmware/grid_monitor.ino` are placeholders in the committed copy. Never commit real credentials — keep the change unstaged, or split into a `firmware/secrets.h` that is gitignored and `#include`d.
- The SQLite DB (`server/smarthome.db` + `-wal`, `-shm`) is gitignored. To reset state in development, stop the server and delete those files — `init_db()` will recreate the schema and seed state to `off` on next start.
