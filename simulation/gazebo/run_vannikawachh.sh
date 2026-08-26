#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORLD="$ROOT/simulation/gazebo/worlds/vannikawachh_f450.sdf"
MODEL="$HOME/ardupilot_gazebo/models/vannikawachh_f450/model.sdf"
MODE="${1:-all}"
HEADLESS="${HEADLESS:-1}"

export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH="$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:${GZ_SIM_RESOURCE_PATH:-}"

if [ ! -f "$MODEL" ]; then
  echo "F450 model is not prepared. Run: python3 simulation/gazebo/prepare_f450.py" >&2
  exit 2
fi

find_sim_vehicle() {
  if [ -x "$HOME/ardupilot/Tools/autotest/sim_vehicle.py" ]; then
    echo "$HOME/ardupilot/Tools/autotest/sim_vehicle.py"
    return
  fi
  if command -v sim_vehicle.py >/dev/null 2>&1; then
    command -v sim_vehicle.py
    return
  fi
  echo "sim_vehicle.py not found." >&2
  exit 3
}

start_gazebo() {
  if [ "$HEADLESS" = "1" ]; then
    gz sim -s -r "$WORLD"
  else
    gz sim -v4 -r "$WORLD"
  fi
}

start_sitl() {
  cd "$HOME/ardupilot"
  SIM_VEHICLE="$(find_sim_vehicle)"
  local extra=()
  if [ "$HEADLESS" != "1" ]; then
    extra+=(--console --map)
  fi
  exec python3 "$SIM_VEHICLE" -v ArduCopter -f gazebo-iris --model JSON \
    --add-param-file="$ROOT/simulation/gazebo/arducopter-f450.parm" \
    "${extra[@]}"
}

start_bridge() {
  cd "$ROOT"
  # Lightning Studios provide one managed Conda environment and disallow nested
  # virtualenvs. Use that existing Python environment for the bridge.
  python3 - <<'PY'
import importlib.util
missing = [m for m in ("pymavlink", "requests") if importlib.util.find_spec(m) is None]
if missing:
    print("Missing Python packages:", ", ".join(missing))
    raise SystemExit(10)
PY
  exec env VANNIKAWACHH_HUB="${VANNIKAWACHH_HUB:-https://vannikawachh-hub.onrender.com}" \
    MAVLINK_CONNECTION="${MAVLINK_CONNECTION:-udp:127.0.0.1:14550}" \
    python3 "$ROOT/simulation/sitl_bridge.py"
}

case "$MODE" in
  gazebo)
    start_gazebo
    ;;
  sitl)
    start_sitl
    ;;
  bridge)
    start_bridge
    ;;
  all)
    echo "Starting Gazebo ${HEADLESS:+(headless)}..."
    if [ "$HEADLESS" = "1" ]; then
      gz sim -s -r "$WORLD" > /tmp/vannikawachh-gazebo.log 2>&1 &
    else
      gz sim -v4 -r "$WORLD" > /tmp/vannikawachh-gazebo.log 2>&1 &
    fi
    GZ_PID=$!
    trap 'kill "$GZ_PID" 2>/dev/null || true' EXIT
    sleep 5

    echo "Starting ArduCopter SITL..."
    cd "$HOME/ardupilot"
    SIM_VEHICLE="$(find_sim_vehicle)"
    SITL_EXTRA=()
    if [ "$HEADLESS" != "1" ]; then
      SITL_EXTRA+=(--console --map)
    fi
    python3 "$SIM_VEHICLE" -v ArduCopter -f gazebo-iris --model JSON \
      --add-param-file="$ROOT/simulation/gazebo/arducopter-f450.parm" \
      "${SITL_EXTRA[@]}" > /tmp/vannikawachh-sitl.log 2>&1 &
    SITL_PID=$!
    trap 'kill "$SITL_PID" 2>/dev/null || true; kill "$GZ_PID" 2>/dev/null || true' EXIT
    sleep 8

    echo "Starting VanniKawachh SITL bridge..."
    cd "$ROOT"
    python3 - <<'PY'
import importlib.util, subprocess, sys
missing = [m for m in ("pymavlink", "requests") if importlib.util.find_spec(m) is None]
if missing:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "simulation/requirements-sitl.txt"])
PY
    exec env VANNIKAWACHH_HUB="${VANNIKAWACHH_HUB:-https://vannikawachh-hub.onrender.com}" \
      MAVLINK_CONNECTION="${MAVLINK_CONNECTION:-udp:127.0.0.1:14550}" \
      python3 "$ROOT/simulation/sitl_bridge.py"
    ;;
  *)
    echo "Usage: $0 {gazebo|sitl|bridge|all}" >&2
    exit 64
    ;;
esac
