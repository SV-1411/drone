#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORLD="$ROOT/simulation/gazebo/worlds/vannikawachh_f450.sdf"
MODEL="$HOME/ardupilot_gazebo/models/vannikawachh_f450/model.sdf"
MODE="${1:-all}"

export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH="$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:${GZ_SIM_RESOURCE_PATH:-}"

if [ ! -f "$MODEL" ]; then
  echo "F450 model is not prepared. Run: ./simulation/gazebo/setup_f450_harmonic.sh" >&2
  exit 2
fi

find_sim_vehicle() {
  if command -v sim_vehicle.py >/dev/null 2>&1; then
    command -v sim_vehicle.py
    return
  fi
  if [ -x "$HOME/ardupilot/Tools/autotest/sim_vehicle.py" ]; then
    echo "$HOME/ardupilot/Tools/autotest/sim_vehicle.py"
    return
  fi
  echo "sim_vehicle.py not found. Source the ArduPilot environment first." >&2
  exit 3
}

case "$MODE" in
  gazebo)
    exec gz sim -v4 -r "$WORLD"
    ;;
  sitl)
    cd "$HOME/ardupilot"
    SIM_VEHICLE="$(find_sim_vehicle)"
    exec python3 "$SIM_VEHICLE" -v ArduCopter -f gazebo-iris --model JSON \
      --add-param-file="$ROOT/simulation/gazebo/arducopter-f450.parm" \
      --console --map
    ;;
  bridge)
    cd "$ROOT"
    if [ ! -d "$ROOT/.venv-sitl" ]; then
      python3 -m venv "$ROOT/.venv-sitl"
      "$ROOT/.venv-sitl/bin/pip" install -r "$ROOT/simulation/requirements-sitl.txt"
    fi
    exec env VANNIKAWACHH_HUB="${VANNIKAWACHH_HUB:-https://vannikawachh-hub.onrender.com}" \
      MAVLINK_CONNECTION="${MAVLINK_CONNECTION:-udp:127.0.0.1:14550}" \
      "$ROOT/.venv-sitl/bin/python" "$ROOT/simulation/sitl_bridge.py"
    ;;
  all)
    echo "Starting Gazebo in background..."
    gz sim -v4 -r "$WORLD" > /tmp/vannikawachh-gazebo.log 2>&1 &
    GZ_PID=$!
    trap 'kill "$GZ_PID" 2>/dev/null || true' EXIT
    sleep 5

    echo "Starting ArduCopter SITL..."
    cd "$HOME/ardupilot"
    SIM_VEHICLE="$(find_sim_vehicle)"
    python3 "$SIM_VEHICLE" -v ArduCopter -f gazebo-iris --model JSON \
      --add-param-file="$ROOT/simulation/gazebo/arducopter-f450.parm" \
      --console --map > /tmp/vannikawachh-sitl.log 2>&1 &
    SITL_PID=$!
    trap 'kill "$SITL_PID" 2>/dev/null || true; kill "$GZ_PID" 2>/dev/null || true' EXIT
    sleep 8

    echo "Starting VanniKawachh SITL bridge..."
    cd "$ROOT"
    if [ ! -d "$ROOT/.venv-sitl" ]; then
      python3 -m venv "$ROOT/.venv-sitl"
      "$ROOT/.venv-sitl/bin/pip" install -r "$ROOT/simulation/requirements-sitl.txt"
    fi
    exec env VANNIKAWACHH_HUB="${VANNIKAWACHH_HUB:-https://vannikawachh-hub.onrender.com}" \
      MAVLINK_CONNECTION="${MAVLINK_CONNECTION:-udp:127.0.0.1:14550}" \
      "$ROOT/.venv-sitl/bin/python" "$ROOT/simulation/sitl_bridge.py"
    ;;
  *)
    echo "Usage: $0 {gazebo|sitl|bridge|all}" >&2
    exit 64
    ;;
esac
