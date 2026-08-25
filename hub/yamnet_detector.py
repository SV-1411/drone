"""Real AudioSet distress detector (YAMNet, TFLite).

Phase 1 extends the original detector with an explicit representation API:
- frame-level 521-class scores
- clip-level learned AudioSet score vector (521-D)
- optional 1024-D embedding when the loaded TFLite export exposes one

The repository's committed YAMNet export currently exposes class scores only,
so ``embedding()`` returns None unless a compatible embedding output is added.
This avoids pretending that the 521-class output is a 1024-D neural embedding.
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Optional

import numpy as np

log = logging.getLogger("hub.yamnet")

_HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.environ.get("YAMNET_MODEL", os.path.join(_HERE, "models", "yamnet.tflite"))
CLASS_MAP_PATH = os.environ.get("YAMNET_CLASS_MAP", os.path.join(_HERE, "models", "yamnet_class_map.csv"))
SR = 16000
DISTRESS_FRAGMENTS = ("scream", "shout", "yell", "crying", "wail", "whimper")
EXCLUDE_FRAGMENTS = ("(dog)",)


def _load_interpreter(model_path: str):
    """Return a TFLite Interpreter from whichever runtime is installed."""
    try:
        from ai_edge_litert.interpreter import Interpreter
        return Interpreter(model_path=model_path)
    except ImportError:
        pass
    try:
        from tflite_runtime.interpreter import Interpreter
        return Interpreter(model_path=model_path)
    except ImportError:
        pass
    import tensorflow as tf
    return tf.lite.Interpreter(model_path=model_path)


class YamnetDetector:
    """Scores 16 kHz mono audio for scream/shout/cry content, 0..1."""

    def __init__(self, model_path: str = MODEL_PATH, class_map_path: str = CLASS_MAP_PATH):
        if not os.path.exists(model_path):
            raise FileNotFoundError(model_path)
        self._interp = _load_interpreter(model_path)
        self._names = self._read_class_map(class_map_path)
        self._distress_idx = [
            i for i, n in enumerate(self._names)
            if any(f in n.lower() for f in DISTRESS_FRAGMENTS)
            and not any(x in n.lower() for x in EXCLUDE_FRAGMENTS)
        ]
        if not self._distress_idx:
            raise RuntimeError("no distress classes found in class map")
        in_det = self._interp.get_input_details()[0]
        self._in_idx = in_det["index"]
        outputs = self._interp.get_output_details()
        self._out_idx = outputs[0]["index"]
        self._embedding_out_idx = None
        for out in outputs:
            shape = tuple(int(v) for v in np.asarray(out.get("shape", ())).reshape(-1))
            if len(shape) == 2 and shape[-1] == 1024:
                self._embedding_out_idx = out["index"]
                break
        if self._embedding_out_idx is None:
            log.info("YAMNet export exposes class scores but no 1024-D embedding output")
        else:
            log.info("YAMNet embedding output detected")
        log.info("YAMNet loaded (%d classes, %d distress-relevant)", len(self._names), len(self._distress_idx))

    @staticmethod
    def _read_class_map(path: str) -> list[str]:
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        return [r[2] for r in rows[1:] if len(r) >= 3]

    @staticmethod
    def _resample(audio: np.ndarray, sr: int) -> np.ndarray:
        x = np.asarray(audio, dtype=np.float32)
        if sr == SR or x.size <= 1:
            return x
        n = max(1, int(round(x.size * SR / sr)))
        src = np.linspace(0.0, 1.0, x.size, dtype=np.float64)
        dst = np.linspace(0.0, 1.0, n, dtype=np.float64)
        return np.interp(dst, src, x).astype(np.float32)

    def _scores(self, audio: np.ndarray, sr: int = SR) -> np.ndarray:
        """Run YAMNet; returns per-frame class scores [n_frames, 521]."""
        x = self._resample(audio, sr)
        if x.size < int(0.975 * SR) + 1:
            x = np.pad(x, (0, int(0.975 * SR) + 1 - x.size))
        self._interp.resize_tensor_input(self._in_idx, [x.size])
        self._interp.allocate_tensors()
        self._interp.set_tensor(self._in_idx, x)
        self._interp.invoke()
        scores = self._interp.get_tensor(self._out_idx)
        return np.asarray(scores, dtype=np.float32)

    def frame_scores(self, audio: np.ndarray, sr: int = SR) -> np.ndarray:
        """Return the raw per-frame 521-class YAMNet score matrix."""
        return self._scores(audio, sr)

    def class_score_vector(self, audio: np.ndarray, sr: int = SR) -> np.ndarray:
        """Return a fixed 521-D learned AudioSet representation (mean over frames)."""
        scores = self._scores(audio, sr)
        return scores.mean(axis=0).astype(np.float32)

    def embedding(self, audio: np.ndarray, sr: int = SR) -> Optional[np.ndarray]:
        """Return a 1024-D YAMNet embedding when the TFLite export provides one.

        The committed model currently does not expose this intermediate tensor;
        in that case return None rather than treating class probabilities as an
        embedding.
        """
        if self._embedding_out_idx is None:
            return None
        x = self._resample(audio, sr)
        if x.size < int(0.975 * SR) + 1:
            x = np.pad(x, (0, int(0.975 * SR) + 1 - x.size))
        self._interp.resize_tensor_input(self._in_idx, [x.size])
        self._interp.allocate_tensors()
        self._interp.set_tensor(self._in_idx, x)
        self._interp.invoke()
        emb = np.asarray(self._interp.get_tensor(self._embedding_out_idx), dtype=np.float32)
        return emb.mean(axis=0) if emb.ndim == 2 else emb.reshape(-1)

    def distress_score(self, audio: np.ndarray, sr: int = SR) -> float:
        """Max over frames of the summed distress-class probability, 0..1."""
        scores = self._scores(audio, sr)
        per_frame = scores[:, self._distress_idx].sum(axis=1)
        return round(float(min(1.0, per_frame.max())), 3)

    def distress_label(self, audio: np.ndarray, sr: int = SR):
        """Return (score, best distress class) for the strongest frame."""
        scores = self._scores(audio, sr)
        dist = scores[:, self._distress_idx]
        frame = int(dist.sum(axis=1).argmax())
        best = int(dist[frame].argmax())
        score = float(min(1.0, dist[frame].sum()))
        return round(score, 3), self._names[self._distress_idx[best]]

    def top_labels(self, audio: np.ndarray, sr: int = SR, k: int = 5):
        """Return top labels for the strongest-scoring frame."""
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
