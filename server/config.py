"""Tunable parameters for SmartHome automations.

Each automation gets its own nested class. Add a new class when adding a
new automation; service code imports the specific class it needs:

    from config import GridMonitor
    if elapsed > GridMonitor.OFFLINE_THRESHOLD_S: ...
"""


class GridMonitor:
    """Grid power outage detector via ESP32 heartbeats."""

    # Expected interval between heartbeats from the ESP32 (seconds).
    # Keep in sync with HEARTBEAT_INTERVAL_MS in firmware/grid_monitor/grid_monitor.ino.
    HEARTBEAT_INTERVAL_S = 5

    # How long to wait without a heartbeat before declaring the grid OFF.
    # Recommended: ~3x HEARTBEAT_INTERVAL_S to absorb a single dropped packet.
    OFFLINE_THRESHOLD_S = 15

    # How often the background stale-watcher checks for missed heartbeats
    # (seconds). Lower = faster outage detection; higher = less CPU.
    CHECK_INTERVAL_S = 2
