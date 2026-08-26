"""Hub-side import shim for the SIMNET MAVLink bridge.

The implementation lives in simulation/simnet_bridge.py so it can also be used
outside the FastAPI process. The hub imports this shim to keep the deployment
module layout stable.
"""
from simulation.simnet_bridge import SimnetMavlinkBridge, SimnetState, _haversine

__all__ = ["SimnetMavlinkBridge", "SimnetState", "_haversine"]
