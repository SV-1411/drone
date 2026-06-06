# One-command launcher for the drone safety system (Windows / native).
# Starts: dronekit-sitl  +  FastAPI trigger  +  Vite dashboard
# Each runs in its own background window so logs are visible.
#
# Usage:    pwsh -File run_all.ps1
#           (or:  .\run_all.ps1)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Output "==========================================================="
Write-Output " DRONE SAFETY SYSTEM — native launcher"
Write-Output " Root: $Root"
Write-Output "==========================================================="

# 1) Make sure Python deps are installed
Write-Output "`n[boot] checking Python dependencies..."
$probe = & python -c "import dronekit, dronekit_sitl, fastapi, uvicorn" 2>&1
if (-not $?) {
  Write-Output "[boot] installing requirements.txt"
  & python -m pip install --upgrade pip
  & python -m pip install -r "$Root\requirements.txt"
}

# 2) Make sure Node deps are installed
if (-not (Test-Path "$Root\dashboard\node_modules")) {
  Write-Output "[boot] installing dashboard npm deps (first time)"
  Push-Location "$Root\dashboard"
  & npm install
  Pop-Location
}

# 3) SITL
Write-Output "`n[boot] launching SITL window"
$sitlCmd = "cd `"$Root`"; python -m dronekit_sitl copter --home=28.6139,77.2090,584,0"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $sitlCmd -WindowStyle Normal

# 4) Wait for SITL TCP port
Write-Output "[boot] waiting for SITL on 127.0.0.1:5760..."
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", 5760)
    $c.Close()
    Write-Output "[boot] SITL is listening"
    break
  } catch {
    Start-Sleep -Seconds 2
  }
}

# 5) API
Write-Output "[boot] launching FastAPI trigger window"
$apiCmd = "cd `"$Root`"; `$env:MAVLINK_CONNECTION='tcp:127.0.0.1:5760'; `$env:SITL_MODE='1'; python -m uvicorn trigger_api.main:app --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd -WindowStyle Normal

# 6) Dashboard
Write-Output "[boot] launching dashboard window"
$dashCmd = "cd `"$Root\dashboard`"; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $dashCmd -WindowStyle Normal

Write-Output ""
Write-Output "All three services launching. Once they print 'ready':"
Write-Output "  Dashboard:  http://localhost:5173"
Write-Output "  API docs:   http://localhost:8000/docs"
Write-Output "  SITL TCP:   127.0.0.1:5760"
Write-Output ""
Write-Output "Trigger a mission (no manual flight needed):"
Write-Output '  Invoke-RestMethod -Method Post -Uri http://localhost:8000/trigger -ContentType application/json -Body (@{lat=28.62; lon=77.215; priority="high"; incident_type="medical"} | ConvertTo-Json)'
Write-Output ""
Write-Output "Or run the full automated test:"
Write-Output "  python tests\test_full_mission.py"
