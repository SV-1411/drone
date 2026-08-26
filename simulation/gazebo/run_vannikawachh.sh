#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
WORLD="$ROOT/simulation/gazebo/worlds/vannikawachh_f450.sdf"

# Lightning Studios exposes project directories below ~/content; a local
# workstation normally uses $HOME directly. Reuse the existing installs and
# permit callers to supply explicit roots—never clone or replace ArduPilot.
find_existing_root() {
  local override="${1:-}"
  local directory_name="$2"
  local candidate
  for candidate in "$override" "$HOME/$directory_name" "$HOME/content/$directory_name" "$(dirname "$ROOT")/$directory_name"; do
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

ARDUPILOT_ROOT="$(find_existing_root "${ARDUPILOT_ROOT:-}" ardupilot)" || {
  echo "Existing ArduPilot checkout not found. Set ARDUPILOT_ROOT." >&2
  exit 2
}
ARDUPILOT_GAZEBO_ROOT="$(find_existing_root "${ARDUPILOT_GAZEBO_ROOT:-}" ardupilot_gazebo)" || {
  echo "Existing ardupilot_gazebo checkout not found. Set ARDUPILOT_GAZEBO_ROOT." >&2
  exit 2
}

MODEL="$ARDUPILOT_GAZEBO_ROOT/models/vannikawachh_f450/model.sdf"
MODE="${1:-all}"
HEADLESS="${HEADLESS:-1}"

export GZ_VERSION=harmonic
# User-scoped Python tools (notably MAVProxy) install their entry points here
# on Linux. Keep the system PATH intact for local/venv installations.
export PATH="$HOME/.local/bin:$PATH"
export GZ_SIM_SYSTEM_PLUGIN_PATH="$ARDUPILOT_GAZEBO_ROOT/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$ARDUPILOT_GAZEBO_ROOT/models:$ARDUPILOT_GAZEBO_ROOT/worlds:${GZ_SIM_RESOURCE_PATH:-}"

if [ ! -f "$MODEL" ]; then
  echo "F450 model is not prepared. Run: python3 simulation/gazebo/prepare_f450.py" >&2
  exit 2
fi

find_sim_vehicle() {
  if [ -x "$ARDUPILOT_ROOT/Tools/autotest/sim_vehicle.py" ]; then
    echo "$ARDUPILOT_ROOT/Tools/autotest/sim_vehicle.py"
    return
  fi
  if command -v sim_vehicle.py >/dev/null 2>&1; then
    command -v sim_vehicle.py
    return
  fi
  echo "sim_vehicle.py not found." >&2
  exit 3
}

ensure_bridge_dependencies() {
  if python3 - <<'PY'
import importlib.util
missing = [name for name in ("pymavlink", "MAVProxy", "requests") if importlib.util.find_spec(name) is None]
raise SystemExit(1 if missing else 0)
PY
  then
    return
  fi

  # Lightning's managed Python is PEP 668 externally managed. Installs are
  # deliberately user-scoped, and the compatibility flag is added only when
  # that marker is present. This leaves a normal local Python untouched.
  PIP_ARGS=(--user)
  if python3 - <<'PY'
import pathlib, sysconfig
raise SystemExit(0 if (pathlib.Path(sysconfig.get_path("stdlib")) / "EXTERNALLY-MANAGED").exists() else 1)
PY
  then
    PIP_ARGS+=(--break-system-packages)
  fi
  python3 -m pip install "${PIP_ARGS[@]}" -r "$ROOT/simulation/requirements-sitl.txt"
}

start_mavproxy() {
  # sim_vehicle launches MAVProxy interactively by default. In a headless
  # Studio its stdin closes, which makes MAVProxy exit and tears down SITL.
  # Run its non-interactive mode explicitly and keep the PID for cleanup.
  mavproxy.py --non-interactive --retries 5 \
    --out=udp:127.0.0.1:14550 \
    --master=tcp:127.0.0.1:5760 \
    --sitl=127.0.0.1:5501
}

start_gazebo() {
  if [ "$HEADLESS" = "1" ]; then
    gz sim -s -r "$WORLD"
  else
    gz sim -v4 -r "$WORLD"
  fi
}

start_sitl() {
  cd "$ARDUPILOT_ROOT"
  SIM_VEHICLE="$(find_sim_vehicle)"
  local extra=()
  if [ "$HEADLESS" != "1" ]; then
    extra+=(--console --map)
  fi
  if [ "$HEADLESS" = "1" ]; then
    ( sleep 5; start_mavproxy ) > /tmp/vannikawachh-mavproxy.log 2>&1 &
  fi
  exec python3 "$SIM_VEHICLE" -v ArduCopter -f gazebo-iris --model JSON --no-mavproxy \
    --add-param-file="$ROOT/simulation/gazebo/arducopter-f450.parm" \
    "${extra[@]}"
}

start_bridge() {
  cd "$ROOT"
  ensure_bridge_dependencies
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
    cd "$ARDUPILOT_ROOT"
    SIM_VEHICLE="$(find_sim_vehicle)"
    SITL_EXTRA=()
    if [ "$HEADLESS" != "1" ]; then
      SITL_EXTRA+=(--console --map)
    fi
    python3 "$SIM_VEHICLE" -v ArduCopter -f gazebo-iris --model JSON --no-mavproxy \
      --add-param-file="$ROOT/simulation/gazebo/arducopter-f450.parm" \
      "${SITL_EXTRA[@]}" > /tmp/vannikawachh-sitl.log 2>&1 &
    SITL_PID=$!
    if [ "$HEADLESS" = "1" ]; then
      sleep 5
      start_mavproxy > /tmp/vannikawachh-mavproxy.log 2>&1 &
      MAVPROXY_PID=$!
    fi
    trap 'kill "${MAVPROXY_PID:-}" 2>/dev/null || true; kill "$SITL_PID" 2>/dev/null || true; kill "$GZ_PID" 2>/dev/null || true' EXIT
    sleep 8

    echo "Starting VanniKawachh SITL bridge..."
    cd "$ROOT"
    ensure_bridge_dependencies
    exec env VANNIKAWACHH_HUB="${VANNIKAWACHH_HUB:-https://vannikawachh-hub.onrender.com}" \
      MAVLINK_CONNECTION="${MAVLINK_CONNECTION:-udp:127.0.0.1:14550}" \
      python3 "$ROOT/simulation/sitl_bridge.py"
    ;;
  *)
    echo "Usage: $0 {gazebo|sitl|bridge|all}" >&2
    exit 64
    ;;
esac
