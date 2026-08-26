#!/usr/bin/env bash
# Start the *actual* Gazebo Harmonic GUI and publish it through noVNC.
#
# This is intentionally separate from run_vannikawachh.sh: the latter owns the
# authoritative physics/SITL stack, while this process is the graphical client
# that attaches to that running Gazebo server.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DISPLAY_NAME="${GAZEBO_GUI_DISPLAY:-:99}"
VNC_PORT="${GAZEBO_VNC_PORT:-5900}"
WEB_PORT="${GAZEBO_WEB_PORT:-6080}"
WIDTH="${GAZEBO_GUI_WIDTH:-1920}"
HEIGHT="${GAZEBO_GUI_HEIGHT:-1080}"
DEPTH="${GAZEBO_GUI_DEPTH:-24}"

find_existing_root() {
  local override="${1:-}" directory_name="$2" candidate
  for candidate in "$override" "$HOME/$directory_name" "$HOME/content/$directory_name" "$(dirname "$ROOT")/$directory_name"; do
    if [ -n "$candidate" ] && [ -d "$candidate" ]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done
  return 1
}

ARDUPILOT_GAZEBO_ROOT="$(find_existing_root "${ARDUPILOT_GAZEBO_ROOT:-}" ardupilot_gazebo)" || {
  echo "Existing ardupilot_gazebo checkout not found. Set ARDUPILOT_GAZEBO_ROOT." >&2
  exit 2
}

command -v gz >/dev/null || { echo "Gazebo Harmonic (gz) is not installed." >&2; exit 3; }
command -v x11vnc >/dev/null || { echo "x11vnc is missing; run setup_gazebo_gui_stream.sh." >&2; exit 3; }
command -v websockify >/dev/null || { echo "websockify is missing; run setup_gazebo_gui_stream.sh." >&2; exit 3; }

NOVNC_WEB_ROOT="${NOVNC_WEB_ROOT:-}"
if [ -z "$NOVNC_WEB_ROOT" ]; then
  for candidate in /usr/share/novnc /usr/share/novnc/vnc_lite.html; do
    if [ -d "$candidate" ]; then NOVNC_WEB_ROOT="$candidate"; break; fi
  done
fi
[ -n "$NOVNC_WEB_ROOT" ] && [ -d "$NOVNC_WEB_ROOT" ] || {
  echo "noVNC web root not found. Set NOVNC_WEB_ROOT." >&2
  exit 3
}

export GZ_VERSION=harmonic
export GZ_SIM_RESOURCE_PATH="$ARDUPILOT_GAZEBO_ROOT/models:$ARDUPILOT_GAZEBO_ROOT/worlds:${GZ_SIM_RESOURCE_PATH:-}"
export DISPLAY="$DISPLAY_NAME"

XVFB_PID="" GUI_PID="" VNC_PID="" WEB_PID=""
cleanup() {
  for pid in "$WEB_PID" "$VNC_PID" "$GUI_PID" "$XVFB_PID"; do
    [ -n "${pid:-}" ] && kill "$pid" 2>/dev/null || true
  done
}
trap cleanup EXIT INT TERM

# For production GPU rendering, point GAZEBO_GUI_DISPLAY to a real headless
# Xorg display (usually :0) and set GAZEBO_START_XVFB=0. Xvfb is a portable
# fallback and does not claim to provide accelerated NVIDIA/AMD rendering.
if [ "${GAZEBO_START_XVFB:-1}" = "1" ]; then
  command -v Xvfb >/dev/null || { echo "Xvfb is missing; run setup_gazebo_gui_stream.sh." >&2; exit 3; }
  Xvfb "$DISPLAY_NAME" -screen 0 "${WIDTH}x${HEIGHT}x${DEPTH}" +extension GLX +render -noreset > /tmp/vannikawachh-xvfb.log 2>&1 &
  XVFB_PID=$!
  sleep 1
fi

echo "[gazebo-gui] attaching Gazebo GUI to the active server on DISPLAY=$DISPLAY_NAME"
# `-g` is GUI-only: the already running `-s -r` server remains the sole
# simulation authority and this client simply connects to it.
gz sim -g -v 3 > /tmp/vannikawachh-gazebo-gui.log 2>&1 &
GUI_PID=$!

echo "[gazebo-gui] starting private VNC listener on 127.0.0.1:$VNC_PORT"
x11vnc -display "$DISPLAY_NAME" -rfbport "$VNC_PORT" -localhost -forever -shared -nopw -xkb > /tmp/vannikawachh-x11vnc.log 2>&1 &
VNC_PID=$!
sleep 1

echo "[gazebo-gui] serving noVNC on 0.0.0.0:$WEB_PORT"
websockify --web "$NOVNC_WEB_ROOT" "$WEB_PORT" "127.0.0.1:$VNC_PORT" > /tmp/vannikawachh-novnc.log 2>&1 &
WEB_PID=$!
wait "$WEB_PID"
