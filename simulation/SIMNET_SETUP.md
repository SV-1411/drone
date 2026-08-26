# SIMNET (optional / archived)

SIMNET was evaluated as a high-fidelity alternative for the VanniKawachh project. It can provide worldwide 3D terrain and ArduPilot/PX4 SITL connections, but it requires a live session-specific TCP endpoint.

For the VanniKawachh seed-money demonstration, **SIMNET is no longer the primary flight simulator**. The primary simulation is now **ArduPilot SITL + Gazebo Harmonic** because it can run locally without a SIMNET free-trial/session dependency and can be automated from the repository.

Use:

```text
simulation/gazebo/setup_f450_harmonic.sh
simulation/gazebo/run_vannikawachh.sh all
```

See `simulation/gazebo/README.md` for the full setup and mission flow.

The old SIMNET connection code is intentionally not required by Render. This means the deployed web demo remains usable when no external simulation session exists.
