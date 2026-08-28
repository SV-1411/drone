# Permanent GPU host: live Gazebo F450 interface

This package separates the real flight physics, the real Gazebo renderer, and
the browser UI. The browser never generates the primary 3D scene.

```text
Gazebo server + ArduPilot SITL  ->  real F450 physics
Gazebo GUI on GPU display       ->  actual rendered scene
noVNC / websockify              ->  browser stream at /gazebo-ui/
Hub /drone-flight               ->  embeds that scene + telemetry + map
```

## Host prerequisites

Use a supported Ubuntu Linux host with a working NVIDIA or AMD driver and a
GPU-backed Xorg display. The GUI must run on that real display for accelerated
rendering. `Xvfb` is provided only as a compatibility fallback and is not the
production GPU path.

Keep the current repository and external checkouts adjacent, for example:

```text
/srv/vannikawachh/drone
/srv/vannikawachh/ardupilot
/srv/vannikawachh/ardupilot_gazebo
```

## One-time preparation

```bash
cd /srv/vannikawachh/drone
./simulation/gazebo/setup_f450_harmonic.sh
./simulation/gazebo/setup_gazebo_gui_stream.sh
python3 simulation/gazebo/prepare_f450.py
```

The existing setup script is responsible for the established Gazebo/ArduPilot
installation flow. Do not replace a working ArduPilot checkout just to deploy
this UI.

## First live validation

In terminal one, start the authoritative flight stack:

```bash
export ARDUPILOT_ROOT=/srv/vannikawachh/ardupilot
export ARDUPILOT_GAZEBO_ROOT=/srv/vannikawachh/ardupilot_gazebo
HEADLESS=1 ./simulation/gazebo/run_vannikawachh.sh all
```

In terminal two, attach the actual GUI to the running Gazebo server. For the
first portable test use Xvfb; for production use the GPU-backed display:

```bash
export ARDUPILOT_GAZEBO_ROOT=/srv/vannikawachh/ardupilot_gazebo
GAZEBO_START_XVFB=1 ./simulation/gazebo/gazebo_gui_stream.sh
```

The noVNC page is then reachable on port 6080. Its GUI is the real Gazebo
client; if the F450 takes off in the rendered scene, the physical simulation is
what is being shown.

## Connect the flight page

Run the hub and set this value in its service environment:

```bash
GAZEBO_VIEW_URL='/gazebo-ui/vnc.html?autoconnect=true&path=gazebo-ui/websockify'
```

Use `Caddyfile.example` to reverse-proxy the hub and the noVNC stream under one
HTTPS origin. The `/drone-flight` page will then
embed the live Gazebo screen as its primary viewport. The map below it is only
the mission companion view.

The systemd services are the always-on runtime owner, so leave
`GAZEBO_CONTROL_URL` empty on a permanent host unless an optional HTTP control
service is deliberately installed. In that normal configuration the page's
start and stop controls state that runtime control is not configured; systemd
keeps the real simulation running instead.

## Persistent services

Copy the two systemd templates from `systemd/`, replace every `CHANGE_ME`, then
install and enable them. The GUI service requires a real headless Xorg display
such as `:0`; configure the NVIDIA/AMD driver and display manager before setting
`GAZEBO_START_XVFB=0`.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vannikawachh-gazebo.service
sudo systemctl enable --now vannikawachh-gazebo-gui.service
```

Review `journalctl -u vannikawachh-gazebo -f` and
`journalctl -u vannikawachh-gazebo-gui -f` during the first startup.
