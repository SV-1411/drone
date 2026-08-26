#!/usr/bin/env python3
"""Request-driven launcher for the Lightning Studio F450 runtime.

The browser hardware page is a presentation layer.  This tiny stdlib-only
service is the Studio-facing control plane: Lightning wakes the Studio for a
request, this process starts the real Gazebo/SITL/bridge stack once, and
status endpoints make the runtime state observable without shell access.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "simulation" / "gazebo" / "run_vannikawachh.sh"
PORT = int(os.environ.get("STUDIO_CONTROL_PORT", "8000"))
# The public dashboard is hosted separately from the Studio.  Keep the
# control surface scoped to that origin instead of opening it to every site.
DASHBOARD_ORIGIN = os.environ.get(
    "GAZEBO_DASHBOARD_ORIGIN", "https://vannikawachh-hub.onrender.com"
)
_lock = threading.Lock()
_runtime: subprocess.Popen | None = None


def _running() -> bool:
    return _runtime is not None and _runtime.poll() is None


def start_runtime() -> dict:
    global _runtime
    with _lock:
        if not _running():
            log = open("/tmp/vannikawachh-auto.log", "ab", buffering=0)
            env = os.environ.copy()
            env["HEADLESS"] = "1"
            _runtime = subprocess.Popen(
                ["bash", str(LAUNCHER), "all"],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        return {"ok": True, "state": "running", "pid": _runtime.pid}


def stop_runtime() -> dict:
    global _runtime
    with _lock:
        if not _running():
            return {"ok": True, "state": "stopped"}
        os.killpg(_runtime.pid, signal.SIGTERM)
        return {"ok": True, "state": "stopping", "pid": _runtime.pid}


class Handler(BaseHTTPRequestHandler):
    def _cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", DASHBOARD_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Vary", "Origin")

    def _send(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("", "/start", "/trigger"):
            self._send(start_runtime())
        elif self.path.rstrip("/") in ("/health", "/status"):
            self._send({"ok": True, "state": "running" if _running() else "stopped"})
        else:
            self._send({"ok": False, "error": "use /start, /status, or /stop"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") in ("/start", "/trigger"):
            self._send(start_runtime(), 202)
        elif self.path.rstrip("/") == "/stop":
            self._send(stop_runtime())
        else:
            self._send({"ok": False, "error": "use /start, /trigger, or /stop"}, 404)

    def log_message(self, fmt: str, *args) -> None:
        print("[studio-control] " + fmt % args, flush=True)


if __name__ == "__main__":
    print(f"[studio-control] listening on 0.0.0.0:{PORT}; first request starts F450 runtime", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
