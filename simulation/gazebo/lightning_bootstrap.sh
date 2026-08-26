#!/usr/bin/env bash
set -euo pipefail

# Bootstrap VanniKawachh Gazebo + ArduPilot on a Lightning Studio without
# requiring GitHub git credentials. The repo is downloaded as a public tarball.
ROOT="${HOME}/vannikawachh"
REPO_TARBALL="https://github.com/SV-1411/drone/archive/refs/heads/main.tar.gz"
TMP="${HOME}/.cache/vannikawachh-main.tar.gz"

mkdir -p "$(dirname "$TMP")"
echo "[1/5] Downloading VanniKawachh source..."
curl -fL "$REPO_TARBALL" -o "$TMP"
rm -rf "$ROOT" "${ROOT}-main"
mkdir -p "$ROOT"
tar -xzf "$TMP" -C "$ROOT" --strip-components=1
cd "$ROOT"

echo "[2/5] Checking GPU..."
command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi || echo "WARN: nvidia-smi unavailable"

echo "[3/5] Running Gazebo/ArduPilot setup..."
chmod +x simulation/gazebo/setup_f450_harmonic.sh
./simulation/gazebo/setup_f450_harmonic.sh

cat > "$HOME/start_vannikawachh_sim.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
cd "$HOME/vannikawachh"
source "$HOME/.bashrc" 2>/dev/null || true
exec ./simulation/gazebo/run_vannikawachh.sh all
EOF
chmod +x "$HOME/start_vannikawachh_sim.sh"

echo "[4/5] Setup complete."
echo "[5/5] Start everything with:"
echo "  $HOME/start_vannikawachh_sim.sh"
