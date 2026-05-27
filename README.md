# SmartHome — Grid Power Monitor

Detects whether grid electricity is on or off using a grid-powered ESP32 as a
"canary." The ESP32 heartbeats a FastAPI server every 5 s; when heartbeats
stop, the server logs an outage. A responsive web dashboard shows current
status, current-state duration, and today's statistics.

## Architecture

```
[ESP32 on grid power]  --POST /api/heartbeat every 5s-->  [FastAPI server + SQLite]
                                                                  |
[Browser (phone/laptop)] -- GET /api/status every 2s -----> serves HTML/CSS/JS
```

- **Outage detection:** if no heartbeat has arrived in 15 s (3× the interval),
  state flips to `off` and an event is recorded.
- **Database:** SQLite — single file (`server/smarthome.db`), zero setup,
  perfect for the low data volume.
- **Server host:** any always-on machine on the same LAN as the ESP32 — a
  Raspberry Pi on a small UPS is the recommended setup so the server keeps
  running through an outage and can log it.

## Project layout

```
SmartHome/
├── server/
│   ├── main.py             FastAPI app + endpoints + background watcher
│   ├── db.py               SQLite schema + queries
│   ├── requirements.txt
│   └── static/             dashboard (HTML/CSS/JS)
├── firmware/
│   └── grid_monitor.ino    ESP32 sketch
└── README.md
```

## Run the server

Requires Python 3.10+.

```powershell
cd C:\Projects\SmartHome\server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Then open <http://localhost:8000/> on your phone or laptop.

The SQLite database (`smarthome.db`) is created automatically on first run.

## Flash the ESP32

1. Open `firmware/grid_monitor.ino` in the Arduino IDE.
2. Install the **ESP32 by Espressif Systems** board package
   (Boards Manager) if not already installed.
3. Edit the `CONFIG` block at the top:
   - `WIFI_SSID`, `WIFI_PASSWORD` — your Wi-Fi credentials.
   - `SERVER_URL` — replace `192.168.1.100` with the LAN IP of the machine
     running the server.
4. Select your ESP32 board + COM port and flash.

The Serial Monitor (115200 baud) will print `heartbeat code=200 ok=1` once
per cycle when things are working.

## End-to-end test (no ESP32 needed)

In one terminal, start the server (as above). Then:

```powershell
# fake a heartbeat
curl -X POST http://localhost:8000/api/heartbeat

# check status
curl http://localhost:8000/api/status
```

- Send a heartbeat → dashboard shows **ON**.
- Wait > 15 s without sending → dashboard flips to **OFF** automatically.
- Send another heartbeat → flips back to **ON**, today's outage list grows.

## API

| Method | Path              | Purpose                                              |
| ------ | ----------------- | ---------------------------------------------------- |
| POST   | `/api/heartbeat`  | ESP32 calls this every 5 s. Flips state to `on` if needed. |
| GET    | `/api/status`     | Dashboard polls this every 2 s. Returns current state + today's stats. |
| GET    | `/api/health`     | Liveness check.                                      |
| GET    | `/`               | Serves the dashboard.                                |

## Notes

- All timestamps in the DB are stored as **UTC ISO-8601**.
- The "today" boundary for stats uses the **server's local timezone**.
- Move `smarthome.db` to back up. WAL files (`-wal`, `-shm`) can be ignored
  when the server is stopped.
