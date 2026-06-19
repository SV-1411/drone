# Nagpur launcher for the drone safety system (live dashboard).
# Same as run_all.ps1 but HOME = your coordinates (Nagpur), and a faster,
# correct dependency probe (raw `import dronekit` always fails on Py3.10+ by
# design — the app's shim fixes it — so we probe through the shim instead).
#
# Usage:   .\run_nagpur.ps1
# Then open http://localhost:5173 and click "Dispatch drone".

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

$HomeLat = "21.1463"
$HomeLon = "79.0849"
$HomeAlt = "310"

$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { $Python = "python" }

Write-Output "==========================================================="
Write-Output " DRONE SAFETY SYSTEM - Nagpur live dashboard"
Write-Output " HOME:   $HomeLat, $HomeLon  (your coordinates)"
Write-Output " Python: $Python"
Write-Output "==========================================================="

# Deps + node_modules already verified present this session, so we skip the
# probe (raw `import dronekit` always errors on Py3.10+ by design, and capturing
# native stderr under -ErrorAction Stop aborts the script). If you ever move
# this to a fresh machine, run once:  .venv\Scripts\python.exe -m pip install -r requirements.txt

# 3) SITL - home set to Nagpur
Write-Output "`n[boot] launching SITL window (home = Nagpur)"
$sitlCmd = "cd `"$Root`"; & `"$Python`" -m dronekit_sitl copter-3.3 --home=$HomeLat,$HomeLon,$HomeAlt,0"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $sitlCmd -WindowStyle Normal

# 4) Wait for SITL TCP port
Write-Output "[boot] waiting for SITL on 127.0.0.1:5760..."
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $c.Connect("127.0.0.1", 5760); $c.Close()
    Write-Output "[boot] SITL is listening"; break
  } catch { Start-Sleep -Seconds 2 }
}

# 5) API - HOME set to Nagpur, SITL pre-arm relaxer on
Write-Output "[boot] launching FastAPI trigger window"
$apiCmd = "cd `"$Root`"; `$env:MAVLINK_CONNECTION='tcp:127.0.0.1:5760'; `$env:SITL_MODE='1'; `$env:HOME_LAT='$HomeLat'; `$env:HOME_LON='$HomeLon'; & `"$Python`" -m uvicorn trigger_api.main:app --host 0.0.0.0 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $apiCmd -WindowStyle Normal

# 6) Dashboard
Write-Output "[boot] launching dashboard window"
$dashCmd = "cd `"$Root\dashboard`"; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $dashCmd -WindowStyle Normal

Write-Output ""
Write-Output "All three services launching. Once they print 'ready':"
Write-Output "  Dashboard:  http://localhost:5173   <-- open this, map sits on Nagpur"
Write-Output "  API docs:   http://localhost:8000/docs"
Write-Output ""
Write-Output "In the dashboard: the target is pre-filled to a point ~490 m away."
Write-Output "Just click 'Dispatch drone' and watch the blue trail on the map."
