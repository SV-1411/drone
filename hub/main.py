"""VanniKawachh hub entrypoint.

    python -m hub.main --serial COM3      # real gateway ESP32 on USB
    python -m hub.main --sim              # simulated: inject one test alert

The clip server (WiFi uploads from nodes) runs in a background thread on
CONFIG.clip_server_port. Ctrl+C to stop.
"""
from __future__ import annotations

import argparse
import logging
import os
import threading

from .config import CONFIG
from .lora_gateway import SerialGateway, SimGateway
from .node_registry import Node, NodeRegistry
from .packets import Alert, seal
from .pipeline import AlertPipeline

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("hub")


def _start_clip_server() -> None:
    import uvicorn
    from .clip_server import app

    def _run():
        uvicorn.run(app, host="0.0.0.0", port=CONFIG.clip_server_port,
                    log_level="warning")

    threading.Thread(target=_run, name="clip-server", daemon=True).start()
    log.info("clip server on :%d", CONFIG.clip_server_port)


def main() -> int:
    ap = argparse.ArgumentParser(description="VanniKawachh hub")
    ap.add_argument("--serial", metavar="PORT", help="gateway serial port")
    ap.add_argument("--sim", action="store_true", help="inject one simulated alert")
    ap.add_argument("--clip", metavar="WAV", help="(sim) WAV file to use as the clip")
    args = ap.parse_args()

    os.makedirs(CONFIG.clips_dir, exist_ok=True)
    registry = NodeRegistry(CONFIG.nodes_file)
    if len(registry) == 0:
        # Seed a demo node ~600 m NE of the default SITL home so a fresh
        # checkout works out of the box; real installs replace nodes.json.
        registry.add(Node(node_id=1, lat=28.6178, lon=77.2137, name="demo-pole-1"))
        registry.save()
        log.info("seeded demo node registry at %s", CONFIG.nodes_file)

    pipeline = AlertPipeline(CONFIG, registry)
    _start_clip_server()

    if args.sim:
        gw = SimGateway()
        master = bytes.fromhex(CONFIG.master_key_hex)
        node = registry.get(1)
        alert = Alert(node_id=1, counter=node.last_counter + 1, event=1,
                      confidence=0.86, pir=True, light=20, battery_pct=93)
        if args.clip:
            dst = pipeline.clip_path(1, alert.counter)
            with open(args.clip, "rb") as fsrc, open(dst, "wb") as fdst:
                fdst.write(fsrc.read())
        gw.inject(seal(master, alert))
        gw.close()
    elif args.serial:
        gw = SerialGateway(args.serial, CONFIG.serial_baud)
    else:
        gw = SerialGateway(CONFIG.serial_port, CONFIG.serial_baud)

    log.info("hub ready — verifier backend: %s",
             type(pipeline.verifier.backend).name)
    try:
        for packet in gw.packets():
            inc = pipeline.process_packet(packet)
            if inc is not None:
                log.info("incident recorded: severity=%.2f dispatched=%s mission=%s",
                         inc.severity, inc.dispatched, inc.mission_id)
    except KeyboardInterrupt:
        pass
    finally:
        gw.close() if hasattr(gw, "close") else None
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
