#!/usr/bin/env bash
set -euo pipefail

# VanniKawachh Gazebo Harmonic + ArduPilot + F450 visual setup for Ubuntu 22.04/WSL2.
# Run from the repository root: ./simulation/gazebo/setup_f450_harmonic.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export GZ_VERSION=harmonic

sudo apt update
sudo apt install -y git curl wget python3 python3-pip python3-venv build-essential cmake rapidjson-dev \
  libopencv-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
  gstreamer1.0-gl

if [ ! -d "$HOME/ardupilot" ]; then
  git clone https://github.com/ArduPilot/ardupilot.git --depth 1 "$HOME/ardupilot"
fi

if [ ! -f "$HOME/ardupilot/Tools/environment_install/install-prereqs-ubuntu.sh" ]; then
  echo "ArduPilot source exists but prereq installer was not found" >&2
  exit 1
fi

cd "$HOME/ardupilot"
Tools/environment_install/install-prereqs-ubuntu.sh -y
. "$HOME/.profile"
./waf configure --board sitl
./waf copter

if [ ! -d "$HOME/ardupilot_gazebo" ]; then
  git clone https://github.com/ArduPilot/ardupilot_gazebo.git --depth 1 "$HOME/ardupilot_gazebo"
fi

cd "$HOME/ardupilot_gazebo"
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j"$(nproc)"

cat >> "$HOME/.bashrc" <<'EOF'
export GZ_VERSION=harmonic
export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH}
export GZ_SIM_RESOURCE_PATH=$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:${GZ_SIM_RESOURCE_PATH}
EOF

# Optional upstream F450 visual source; kept outside this repository so its
# original mesh license/attribution remains intact.
mkdir -p "$ROOT/third_party"
if [ ! -d "$ROOT/third_party/px4-quadrotor-HW-parts" ]; then
  git clone https://github.com/beomsu7/px4-quadrotor-HW-parts.git "$ROOT/third_party/px4-quadrotor-HW-parts"
fi

python3 "$ROOT/simulation/gazebo/prepare_f450.py"

python3 - <<'PY'
print('\nVanniKawachh Gazebo setup complete.')
print('Restart WSL or run: source ~/.bashrc')
print('Then: ./simulation/gazebo/run_vannikawachh.sh all')
PY
