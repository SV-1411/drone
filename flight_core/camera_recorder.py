"""Evidence camera recorder.

On the real drone (Pi Zero 2 W + Camera Module 3) this records H.264 to an
mp4 tagged with the mission id, spanning the hover/observation window. On dev
machines and SITL, picamera2 is absent and every call is a logged no-op — the
mission is never blocked by camera trouble.

Live streaming to authorities (RTSP/WebRTC over LTE) is future work; this
module is the seam where it plugs in.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

log = logging.getLogger("flight_core.camera")


class CameraRecorder:
    def __init__(self, out_dir: str = "recordings"):
        self.out_dir = out_dir
        self._cam = None
        self._encoder = None
        self._path: Optional[str] = None

    @property
    def available(self) -> bool:
        try:
            import picamera2  # noqa: F401
            return True
        except ImportError:
            return False

    def start(self, mission_id: str) -> Optional[str]:
        """Begin recording. Returns the output path, or None if no camera."""
        if not self.available:
            log.info("camera unavailable (SITL/dev) — recording skipped")
            return None
        try:
            from picamera2 import Picamera2
            from picamera2.encoders import H264Encoder
            from picamera2.outputs import FfmpegOutput
            os.makedirs(self.out_dir, exist_ok=True)
            self._path = os.path.join(
                self.out_dir, f"{mission_id}_{int(time.time())}.mp4")
            self._cam = Picamera2()
            self._cam.configure(self._cam.create_video_configuration())
            self._encoder = H264Encoder(bitrate=4_000_000)
            self._cam.start_recording(self._encoder, FfmpegOutput(self._path))
            log.info("evidence recording started: %s", self._path)
            return self._path
        except Exception as exc:
            log.error("camera start failed (mission continues): %s", exc)
            self._cam = None
            return None

    def stop(self) -> Optional[str]:
        if self._cam is None:
            return None
        try:
            self._cam.stop_recording()
            self._cam.close()
            log.info("evidence recording stopped: %s", self._path)
        except Exception as exc:
            log.error("camera stop failed: %s", exc)
        finally:
            self._cam = None
        return self._path
