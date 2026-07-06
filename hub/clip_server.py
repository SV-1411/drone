"""Clip upload server — nodes POST their 4 s WAV evidence clip here over
WiFi/ESP-NOW-bridge right after sending the LoRa alert.

    PUT/POST http://<hub>:8990/clip/{node_id}/{counter}   (body = WAV bytes)

The pipeline looks for hub/clips/<node_id>_<counter>.wav; this server just
lands the bytes at that path.
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request

from .config import CONFIG

log = logging.getLogger("hub.clips")

app = FastAPI(title="VanniKawachh clip receiver")


@app.post("/clip/{node_id}/{counter}")
@app.put("/clip/{node_id}/{counter}")
async def upload_clip(node_id: int, counter: int, request: Request):
    os.makedirs(CONFIG.clips_dir, exist_ok=True)
    body = await request.body()
    path = os.path.join(CONFIG.clips_dir, f"{node_id}_{counter}.wav")
    with open(path, "wb") as f:
        f.write(body)
    log.info("clip stored: %s (%d bytes)", path, len(body))
    return {"ok": True, "bytes": len(body)}
