# Start the SmartHome server (Windows).
#
# Paths are derived from this script's location, so the repo can live
# anywhere. Override host/port with SMARTHOME_HOST / SMARTHOME_PORT env vars.
#
# Usage:   .\deploy\start.ps1
#          $env:SMARTHOME_PORT = 9000; .\deploy\start.ps1

$ErrorActionPreference = "Stop"

$repoRoot  = Split-Path -Parent $PSScriptRoot
$serverDir = Join-Path $repoRoot "server"
$pythonExe = Join-Path $serverDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Error "Python venv not found at $pythonExe`nCreate it with: python -m venv `"$serverDir\.venv`""
    exit 1
}

$smartHost = if ($env:SMARTHOME_HOST) { $env:SMARTHOME_HOST } else { "0.0.0.0" }
$smartPort = if ($env:SMARTHOME_PORT) { $env:SMARTHOME_PORT } else { "8000" }

Write-Host "Starting SmartHome on http://${smartHost}:${smartPort}/  (Ctrl+C to stop)"
& $pythonExe -m uvicorn --app-dir $serverDir main:app --host $smartHost --port $smartPort
