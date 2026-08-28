#!/usr/bin/env bash
# Install only the browser-streaming prerequisites. Gazebo Harmonic and
# ArduPilot are installed by the existing setup_f450_harmonic.sh script.
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then SUDO=(); else SUDO=(sudo); fi
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y xvfb x11vnc novnc websockify mesa-utils
echo "Installed noVNC streaming prerequisites. For a permanent GPU host, follow PERMANENT_HOST.md to use a headless Xorg display instead of Xvfb."
