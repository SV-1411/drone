"""Real AudioSet distress detector (YAMNet, TFLite).

YAMNet is Google's AudioSet classifier (521 sound classes, trained on ~2M real
YouTube clips). It directly outputs probabilities for Screaming, Shout, Yell,
Crying/sobbing, Wail/moan and Whimper -- so unlike the DSP heuristic
(`scream_dsp.py`) it recognises what a distress vocalisation *is*, not just
what it sounds like spectrally. It does NOT recognise spoken words
("help"/"bachao"); the keyword path stays with browser speech recognition.

Model files (committed in hub/models/):
  * yamnet.tflite          -- full YAMNet TFLite export (~16 MB): input is a
                              float32 16 kHz waveform of any length, output is
                              per-frame class scores [n_frames, 521]
  * yamnet_class_map.csv   -- index -> AudioSet display name

Backend resolution: any available TFLite interpreter works --
ai-edge-litert, tflite-runtime, or full tensorflow. If none is installed
(e.g. the free cloud tier), `available()` is False and callers fall back to
the DSP detector.
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Optional

import numpy as np

log = logging.getLogger("hub.yamnet")

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.environ.get(
    "YAMNET_MODEL", os.path.join(_HERE, "models", "yamnet.tflite"))
CLASS_MAP_PATH = os.environ.get(
    "YAMNET_CLASS_MAP", os.path.join(_HERE, "models", "yamnet_class_map.csv"))

SR = 16000

# AudioSet display-name fragments that count toward the distress score.
# "(dog)" excludes the canine Whimper class.
DISTRESS_FRAGMENTS = ("scream", "shout", "yell", "crying", "wail", "whimper")
EXCLUDE_FRAGMENTS = ("(dog)",)


def _load_interpreter(model_path: str):
    """Return a TFLite Interpreter from whichever runtime is installed."""
    try:
        from ai_edge_litert.interpreter import Interpreter    # lightest
        return Interpreter(model_path=model_path)
    except ImportError:
        pass
    try:
        from tflite_runtime.interpreter import Interpreter
        return Interpreter(model_path=model_path)
    except ImportError:
        pass
    import tensorflow as tf                                    # full TF
    return tf.lite.Interpreter(model_path=model_path)


class YamnetDetector:
    """Scores 16 kHz mono audio for scream/shout/cry content, 0..1."""

    def __init__(self, model_path: str = MODEL_PATH,
                 class_map_path: str = CLASS_MAP_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(model_path)
        self._interp = _load_interpreter(model_path)
        self._names = self._read_class_map(class_map_path)
        self._distress_idx = [
            i for i, n in enumerate(self._names)
            if any(f in n.lower() for f in DISTRESS_FRAGMENTS)
            and not any(x in n.lower() for x in EXCLUDE_FRAGMENTS)]
        if not self._distress_idx:
            raise RuntimeError("no distress classes found in class map")
        in_det = self._interp.get_input_details()[0]
        self._in_idx = in_det["index"]
        self._out_idx = self._interp.get_output_details()[0]["index"]
        log.info("YAMNet loaded (%d classes, %d distress-relevant: %s)",
                 len(self._names), len(self._distress_idx),
                 ", ".join(self._names[i] for i in self._distress_idx))

    @staticmethod
    def _read_class_map(path: str) -> list:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        return [r[2] for r in rows[1:] if len(r) >= 3]

    def _scores(self, audio: np.ndarray, sr: int = SR) -> np.ndarray:
        """Run YAMNet; returns per-frame class scores [n_frames, 521]."""
        x = np.asarray(audio, dtype=np.float32)
        if sr != SR and x.size > 1:
            idx = np.linspace(0, x.size - 1,
                              int(x.size * SR / sr)).astype(np.int64)
            x = x[idx]
        # YAMNet needs at least one 0.975 s frame
        if x.size < int(0.975 * SR) + 1:
            x = np.pad(x, (0, int(0.975 * SR) + 1 - x.size))
        self._interp.resize_tensor_input(self._in_idx, [x.size])
        self._interp.allocate_tensors()
        self._interp.set_tensor(self._in_idx, x)
        self._interp.invoke()
        return self._interp.get_tensor(self._out_idx)

    def distress_score(self, audio: np.ndarray, sr: int = SR) -> float:
        """Max over frames of the summed distress-class probability, 0..1."""
        scores = self._scores(audio, sr)
        per_frame = scores[:, self._distress_idx].sum(axis=1)
        return round(float(min(1.0, per_frame.max())), 3)

    def distress_label(self, audio: np.ndarray, sr: int = SR):
        """(score, best_class_name) for the strongest frame."""
        scores = self._scores(audio, sr)
        dist = scores[:, self._distress_idx]
        frame = int(dist.sum(axis=1).argmax())
        best = int(dist[frame].argmax())
        score = float(min(1.0, dist[frame].sum()))
        return round(score, 3), self._names[self._distress_idx[best]]

    def top_labels(self, audio: np.ndarray, sr: int = SR, k: int = 5):
        """[(class_name, score)] for the clip's loudest-scoring frame -- for
        tests and debugging, so decisions are explainable."""
        scores = self._scores(audio, sr).max(axis=0)
        order = np.argsort(scores)[::-1][:k]
        return [(self._names[i], round(float(scores[i]), 3)) for i in order]


_detector = None


def get_detector() -> Optional[YamnetDetector]:
    """Load YAMNet once; None when the model/runtime is unavailable."""
    global _detector
    if _detector is None:
        try:
            _detector = YamnetDetector()
        except Exception as exc:
            log.warning("YAMNet unavailable (%s)", exc)
            _detector = False
    return _detector or None


def available() -> bool:
    return get_detector() is not None
