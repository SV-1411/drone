#!/usr/bin/env bash
# Launch ArduCopter SITL via the dronekit-sitl pip package.
# Works identically on Linux/macOS/WSL and inside the Docker SITL container.
set -euo pipefail

HOME_LAT="${HOME_LAT:-28.6139}"
HOME_LON="${HOME_LON:-77.2090}"
HOME_ALT="${HOME_ALT:-584}"
HOME_HDG="${HOME_HDG:-0}"
SITL_PORT="${SITL_PORT:-5760}"

echo "[sitl] launching ArduCopter SITL"
echo "[sitl] home = ${HOME_LAT},${HOME_LON},${HOME_ALT},${HOME_HDG}"
echo "[sitl] TCP MAVLink will be on 0.0.0.0:${SITL_PORT}"

# dronekit-sitl writes binaries to ~/.dronekit-sitl; first run downloads them.
exec dronekit-sitl copter \
  --home="${HOME_LAT},${HOME_LON},${HOME_ALT},${HOME_HDG}"
