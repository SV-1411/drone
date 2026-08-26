#!/usr/bin/env bash
set -euo pipefail

# VanniKawachh Gazebo Harmonic + ArduPilot + F450 visual setup.
# Supported: Ubuntu 22.04 (jammy) and Ubuntu 24.04 (noble), including WSL2.
# Run from repository root:
#   ./simulation/gazebo/setup_f450_harmonic.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export GZ_VERSION=harmonic

DISTRO="$(lsb_release -cs 2>/dev/null || true)"
case "$DISTRO" in
  jammy|noble) ;;
  *)
    echo "This setup supports Ubuntu 22.04 (jammy) and Ubuntu 24.04 (noble). Current distro: ${DISTRO:-unknown}" >&2
    exit 2
    ;;
esac

echo "[VanniKawachh] Ubuntu ${DISTRO} detected — installing Gazebo Harmonic + ArduPilot SITL."

# Gazebo Harmonic official binary installation. Harmonic binaries are
# officially provided for both Jammy and Noble.
sudo apt-get update
sudo apt-get install -y curl lsb-release gnupg git wget python3 python3-pip python3-venv \
  build-essential cmake rapidjson-dev libgz-sim8-dev \
  libopencv-dev libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev \
  gstreamer1.0-plugins-bad gstreamer1.0-libav gstreamer1.0-gl

sudo curl -fsSL https://packages.osrfoundation.org/gazebo.gpg \
  --output /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] https://packages.osrfoundation.org/gazebo/ubuntu-stable ${DISTRO} main" \
  | sudo tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null
sudo apt-get update
sudo apt-get install -y gz-harmonic

# ArduPilot SITL.
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

# Official ArduPilot Gazebo Harmonic plugin.
if [ ! -d "$HOME/ardupilot_gazebo" ]; then
  git clone https://github.com/ArduPilot/ardupilot_gazebo.git --depth 1 "$HOME/ardupilot_gazebo"
fi

cd "$HOME/ardupilot_gazebo"
mkdir -p build
cd build
cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo
make -j"$(nproc)"

# Make plugins and models visible to gz sim.
PROFILE_LINE_1='export GZ_VERSION=harmonic'
PROFILE_LINE_2='export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH}'
PROFILE_LINE_3='export GZ_SIM_RESOURCE_PATH=$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:${GZ_SIM_RESOURCE_PATH}'
for line in "$PROFILE_LINE_1" "$PROFILE_LINE_2" "$PROFILE_LINE_3"; do
  grep -Fqx "$line" "$HOME/.bashrc" || echo "$line" >> "$HOME/.bashrc"
done
export GZ_SIM_SYSTEM_PLUGIN_PATH="$HOME/ardupilot_gazebo/build:${GZ_SIM_SYSTEM_PLUGIN_PATH:-}"
export GZ_SIM_RESOURCE_PATH="$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:${GZ_SIM_RESOURCE_PATH:-}"

# F450 visual source. Mesh assets remain outside this repository so their
# original upstream license/attribution remains intact.
mkdir -p "$ROOT/third_party"
if [ ! -d "$ROOT/third_party/px4-quadrotor-HW-parts" ]; then
  git clone https://github.com/beomsu7/px4-quadrotor-HW-parts.git "$ROOT/third_party/px4-quadrotor-HW-parts"
fi

python3 "$ROOT/simulation/gazebo/prepare_f450.py"

# Smoke checks before declaring setup complete.
command -v gz >/dev/null || { echo 'gz command not found after install' >&2; exit 4; }
gz sim --help >/dev/null
[ -f "$HOME/ardupilot_gazebo/models/vannikawachh_f450/model.sdf" ] || { echo 'F450 model preparation failed' >&2; exit 5; }

python3 - <<'PY'
print()
print('VanniKawachh Gazebo Harmonic setup complete.')
print('Reload environment: source ~/.bashrc')
print('Smoke test: gz sim -v4 -r shapes.sdf')
print('Full mission: ./simulation/gazebo/run_vannikawachh.sh all')
print('The Render dashboard stays online and becomes the GCS when SITL telemetry is reporting.')
PY
