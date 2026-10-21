"""Temporary localhost form for entering the existing dashboard key privately."""
from __future__ import annotations

import contextlib
import html
import io
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from provision_esp32_relay import exchange

NONCE = secrets.token_urlsafe(32)
PAGE = """<!doctype html><meta charset=utf-8><title>VanniKawachh ESP setup</title>
<style>body{font:16px system-ui;max-width:620px;margin:50px auto;padding:20px;background:#f6f8fa;color:#17202a}
input,button{font:inherit;padding:12px;box-sizing:border-box;width:100%;margin:8px 0 20px}
button{background:#173f35;color:white;border:0;cursor:pointer}small{color:#52616b}</style>
<h1>Connect the ESP to your dashboard</h1>
<p>Enter the <b>same operator key</b> you use on the dashboard. There is no separate Pi token.</p>
<p>Use this setup only with the drone disarmed and propellers removed. USB access can reset the ESP.</p>
<form method=post action=/save><input type=hidden name=nonce value="__NONCE__">
<label>Dashboard operator key<input name=key type=password required minlength=32 maxlength=256 autocomplete=off></label>
<label>Battery cells, if confirmed (optional)<input name=cells type=number min=2 max=6 placeholder="For example: 3 for a 3S pack"></label>
<button>Save key to ESP32</button></form>
<small>Served only on this laptop. The key is sent over USB to COM12 and is never printed or saved to a file here.
Physical flight stays locked. Existing Wi-Fi settings are retained.</small>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status: int, body: str):
        encoded = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(encoded)

    def valid_host(self):
        return self.headers.get("Host") == "127.0.0.1:8767"

    def do_GET(self):
        if not self.valid_host() or self.path != "/":
            self.respond(404, "Unavailable")
            return
        self.respond(200, PAGE.replace("__NONCE__", NONCE))

    def do_POST(self):
        if (not self.valid_host() or self.path != "/save" or
                self.headers.get("Origin") not in (None, "http://127.0.0.1:8767")):
            self.respond(403, "Local setup origin required")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length < 4096:
                raise ValueError("invalid request size")
            form = parse_qs(self.rfile.read(length).decode())
            if not secrets.compare_digest(form.get("nonce", [""])[0], NONCE):
                raise ValueError("reload the setup form")
            key = form.get("key", [""])[0].strip()
            if not 32 <= len(key) <= 256 or any(ord(c) < 33 or ord(c) > 126 for c in key):
                raise ValueError("operator key must be 32 to 256 printable non-space characters")
            payload = {"op": "configure", "operator_key": key}
            if form.get("cells"):
                cells = int(form["cells"][0])
                if cells not in range(2, 7):
                    raise ValueError("cell count must be 2 through 6")
                payload["cells"] = cells
            with contextlib.redirect_stdout(io.StringIO()):
                replies = exchange("COM12", payload)
            if not any(r.get("configured") is True for r in replies):
                raise ValueError("ESP did not confirm saving; close other COM12 tools and retry")
            self.respond(200, "<meta charset=utf-8><h1>Key saved to ESP32</h1>"
                         "<p>Flight remains locked. The ESP is reconnecting to Wi-Fi.</p>"
                         "<p>You can close this tab. The temporary setup server is stopping.</p>")
            print(json.dumps({"operator_key_provisioned": True, "flight_locked": True}), flush=True)
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        except Exception as exc:
            # Only our explicit validation errors are suitable for display.
            detail = str(exc) if type(exc) is ValueError else "USB operation failed; verify COM12 is available"
            self.respond(400, "<h1>Setup incomplete</h1><p>" + html.escape(detail) + "</p><a href='/'>Retry</a>")


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 8767), Handler)
    server.daemon_threads = True
    print("ESP setup: http://127.0.0.1:8767/", flush=True)
    server.serve_forever()
    server.server_close()
