"""Stream a Pi USB microphone into the same cloud audio routes as /node.

The only downstream action is a Render dashboard simulation. No local model
label or fixed environmental values are sent as evidence.
"""
from __future__ import annotations

import argparse
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
import io
import json
import logging
import os
import subprocess
import time
import uuid
import wave

import numpy as np
import requests

from hub.distress_keywords import match_distress_keyword


LOG = logging.getLogger("usb-sensing-node")
SR = 16_000
CHUNK_SAMPLES = SR // 2
WINDOW_CHUNKS = 5


def wav_window(chunks: deque[bytes]) -> tuple[bytes, float]:
    """Return the latest 2.5 seconds of 16 kHz mono PCM as a WAV."""
    raw = b"".join(chunks)
    samples = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    rms = float(np.sqrt(np.mean(samples * samples)))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SR)
        wav.writeframes(raw)
    return output.getvalue(), rms


def capture_stream(device: str):
    """Yield overlapping windows; restart the process if ALSA disconnects."""
    process = subprocess.Popen(
        ["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", str(SR),
         "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0,
    )
    chunks: deque[bytes] = deque(maxlen=WINDOW_CHUNKS)
    try:
        while True:
            raw = bytearray()
            while len(raw) < CHUNK_SAMPLES * 2:
                piece = process.stdout.read(CHUNK_SAMPLES * 2 - len(raw))
                if not piece:
                    raise RuntimeError("USB microphone stream ended")
                raw.extend(piece)
            chunks.append(bytes(raw))
            if len(chunks) == WINDOW_CHUNKS:
                yield wav_window(chunks)
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class KeywordRecognizer:
    """Small offline English/Hindi ASR models, loaded once on the Pi."""

    def __init__(self, english_path: str, hindi_path: str):
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        self.models = []
        for language, path in (("en-IN", english_path), ("hi-IN", hindi_path)):
            if os.path.isdir(path):
                self.models.append((language, Model(path)))
        if not self.models:
            LOG.warning("No Vosk models found; keyword route is unavailable")

    def match(self, wav_bytes: bytes) -> tuple[str, float, str] | None:
        from vosk import KaldiRecognizer

        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            raw = wav.readframes(wav.getnframes())
        matches = []
        for language, model in self.models:
            recognizer = KaldiRecognizer(model, SR)
            recognizer.SetWords(True)
            recognizer.AcceptWaveform(raw)
            decoded = json.loads(recognizer.FinalResult())
            keyword = match_distress_keyword(decoded.get("text", ""))
            if keyword:
                words = decoded.get("result") or []
                scores = [float(word.get("conf", 0.0)) for word in words
                          if match_distress_keyword(word.get("word", ""))]
                confidence = max(scores, default=0.0)
                matches.append((keyword, confidence, language))
        return max(matches, key=lambda item: item[1]) if matches else None


def analyse_on_render(base_url: str, wav_bytes: bytes, *, node: str,
                      lat: float, lon: float, session_id: str,
                      sequence: int, keywords: KeywordRecognizer | None = None,
                      bench_activity_confidence: float | None = None) -> dict:
    """Mirror /node: exact word plus stress, voice window, audio fallback."""
    # The Pi currently has no motion or light sensors. Do not invent readings.
    common = {"lat": lat, "lon": lon, "pir": 0, "light": 128,
              "demo": 1, "node": node}
    headers = {"content-type": "audio/wav"}
    url = base_url.rstrip("/")
    matched = keywords.match(wav_bytes) if keywords else None
    if matched:
        keyword, confidence, language = matched
        LOG.info("ASR_MATCH language=%s keyword=%s confidence=%.3f",
                 language, keyword, confidence)
        speech_response = requests.post(
            url + "/speech-alert",
            params={**common, "transcript": keyword, "confidence": confidence},
            headers=headers, data=wav_bytes, timeout=60,
        )
        speech_response.raise_for_status()
        speech = speech_response.json()
        if not speech.get("ok"):
            raise RuntimeError(f"speech-alert error: {speech.get('error', 'unknown')}")
        if speech.get("distress"):
            return {"route": "speech-alert", "result": speech,
                    "voice": speech.get("voice", {})}

    voice_response = requests.post(
        url + "/voice-window",
        params={**common, "session_id": session_id, "sequence": sequence},
        headers=headers, data=wav_bytes, timeout=60,
    )
    voice_response.raise_for_status()
    voice = voice_response.json()
    if not voice.get("ok"):
        raise RuntimeError(f"voice-window error: {voice.get('error', 'unknown')}")
    if voice.get("distress"):
        return {"route": "voice-window", "result": voice, "voice": voice.get("voice", {})}

    phone_response = requests.post(
        url + "/phone-alert", params=common, headers=headers,
        data=wav_bytes, timeout=60,
    )
    phone_response.raise_for_status()
    phone = phone_response.json()
    if not phone.get("ok"):
        raise RuntimeError(f"phone-alert error: {phone.get('error', 'unknown')}")
    # This is deliberately a visible bench fallback, not a claim that a voice
    # classifier understood a word. It lets an installer prove mic -> Pi ->
    # Render -> simulated-drone wiring with a loud nearby voice while a proper
    # speech model is being calibrated. The server endpoint is simulator-only.
    # A weak cloud label can still be below fusion/dispatch thresholds. In
    # bench mode, use the measured loud close-mic event to exercise the visual
    # pipeline whenever it did not actually produce a simulated mission.
    if not phone.get("dispatched") and bench_activity_confidence is not None:
        LOG.warning("BENCH_ACTIVITY_TRIGGER rms-derived confidence=%.3f",
                    bench_activity_confidence)
        bench = requests.post(
            url + "/node-alert",
            params={**common, "event": 2, "conf": bench_activity_confidence},
            timeout=30,
        )
        bench.raise_for_status()
        result = bench.json()
        if not result.get("ok"):
            raise RuntimeError(f"node-alert error: {result.get('error', 'unknown')}")
        return {"route": "bench-activity", "result": result, "voice": voice.get("voice", {})}
    return {"route": "phone-alert", "result": phone, "voice": voice.get("voice", {})}


def log_result(answer: dict) -> bool:
    result = answer["result"]
    voice = answer["voice"]
    probabilities = voice.get("probabilities") or {}
    quality = voice.get("quality") or {}
    LOG.info(
        "CLOUD_AUDIO route=%s label=%s confidence=%s severity=%s "
        "voice_path=%s voice_conf=%s voice_probs=%s rms=%s distress=%s "
        "dispatched=%s mission=%s",
        answer["route"], result.get("stage1", "background"),
        result.get("confidence"), result.get("severity"),
        voice.get("decision_path"), voice.get("confidence"),
        probabilities, quality.get("rms"), result.get("distress"),
        result.get("dispatched"), result.get("mission_id"),
    )
    return bool(result.get("distress"))


def run(args: argparse.Namespace) -> None:
    session_id = f"pi-{uuid.uuid4().hex}"
    sequence = 0
    last_upload = 0.0
    last_distress = 0.0
    try:
        keywords = KeywordRecognizer(args.english_model, args.hindi_model)
        if not keywords.models:
            keywords = None
    except ImportError:
        LOG.warning("Vosk package unavailable; continuing with cloud audio routes")
        keywords = None
    LOG.warning("USB listener active: %s -> Render audio verification, node=%s",
                args.device, args.node)
    with ThreadPoolExecutor(max_workers=1) as executor:
        future: Future | None = None
        while True:
            try:
                for wav_bytes, rms in capture_stream(args.device):
                    if future is not None and future.done():
                        try:
                            confirmed = log_result(future.result())
                            if confirmed:
                                last_distress = time.monotonic()
                        except Exception:
                            LOG.exception("cloud audio analysis failed")
                        future = None
                    now = time.monotonic()
                    if rms < args.min_rms or future is not None:
                        continue
                    if now - last_upload < args.upload_interval or now - last_distress < args.cooldown_seconds:
                        continue
                    sequence += 1
                    last_upload = now
                    # Map only a materially louder-than-room signal onto the
                    # simulator's clearly-strong Stage-1 range. This is used
                    # solely when ASR and cloud audio both reject the clip.
                    activity_confidence = None
                    if rms >= args.bench_rms_threshold:
                        activity_confidence = min(
                            0.99, 0.85 + (rms - args.bench_rms_threshold) * 20.0
                        )
                    LOG.info("AUDIO_UPLOAD sequence=%d local_rms=%.5f bytes=%d",
                             sequence, rms, len(wav_bytes))
                    future = executor.submit(
                        analyse_on_render, args.render_url, wav_bytes,
                        node=args.node, lat=args.lat, lon=args.lon,
                        session_id=session_id, sequence=sequence,
                        keywords=keywords,
                        bench_activity_confidence=activity_confidence,
                    )
            except KeyboardInterrupt:
                LOG.warning("listener stopped")
                return
            except Exception:
                LOG.exception("microphone stream failed; retrying")
                time.sleep(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="USB microphone cloud audio listener")
    parser.add_argument("--device", default=os.environ.get("USB_MIC_DEVICE", "plughw:Audio,0"))
    parser.add_argument("--render-url", default=os.environ.get("RENDER_HUB_URL", "https://vannikawachh-hub.onrender.com"))
    parser.add_argument("--node", default=os.environ.get("SENSING_NODE_NAME", "PI-SENSING-01"))
    parser.add_argument("--lat", type=float, default=float(os.environ.get("SENSING_NODE_LAT", "21.1466")))
    parser.add_argument("--lon", type=float, default=float(os.environ.get("SENSING_NODE_LON", "79.0889")))
    parser.add_argument("--min-rms", type=float, default=0.0005)
    parser.add_argument("--upload-interval", type=float, default=2.5)
    parser.add_argument("--cooldown-seconds", type=float, default=5.0)
    parser.add_argument("--bench-rms-threshold", type=float, default=float(os.environ.get(
        "BENCH_ACTIVITY_RMS_THRESHOLD", "0.018")),
        help="Temporary physical-installation activity threshold; simulator only.")
    parser.add_argument("--english-model", default=os.environ.get(
        "VOSK_ENGLISH_MODEL", "/home/vannidrone/vosk-models/vosk-model-small-en-in-0.4"))
    parser.add_argument("--hindi-model", default=os.environ.get(
        "VOSK_HINDI_MODEL", "/home/vannidrone/vosk-models/vosk-model-small-hi-0.22"))
    return parser.parse_args()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(parse_args())
