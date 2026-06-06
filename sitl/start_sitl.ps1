# Launch ArduCopter SITL on Windows via the dronekit-sitl pip package.
# dronekit-sitl auto-downloads a Windows ArduCopter binary on first run.
param(
  [double]$HomeLat = 28.6139,
  [double]$HomeLon = 77.2090,
  [double]$HomeAlt = 584,
  [double]$HomeHdg = 0
)

$ErrorActionPreference = "Stop"

Write-Output "[sitl] launching ArduCopter SITL"
Write-Output "[sitl] home = $HomeLat,$HomeLon,$HomeAlt,$HomeHdg"
Write-Output "[sitl] TCP MAVLink will be on 127.0.0.1:5760"

# Make sure dronekit-sitl is installed
$check = & python -c "import dronekit_sitl; print(dronekit_sitl.__version__)" 2>$null
if (-not $?) {
  Write-Output "[sitl] dronekit-sitl not installed; installing now"
  & python -m pip install dronekit-sitl==3.3.0
}

$homeArg = "--home=$HomeLat,$HomeLon,$HomeAlt,$HomeHdg"
& dronekit-sitl copter $homeArg
