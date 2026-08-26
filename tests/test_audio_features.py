"""Unit tests for Phase-1 acoustic feature extraction and YAMNet APIs."""
import numpy as np

from hub.audio_features import FEATURE_NAMES, extract_features, extract_frame_features, modulation_roughness
from hub.yamnet_detector import YamnetDetector


def test_feature_vector_is_fixed_shape_and_finite_at_16khz():
    sr = 16000
    t = np.arange(sr * 2, dtype=np.float32) / sr
    audio = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    features = extract_features(audio, sr)
    assert features.shape == (len(FEATURE_NAMES),)
    assert np.isfinite(features).all()


def test_feature_vector_resamples_non_16khz_input():
    sr = 8000
    t = np.arange(sr * 2, dtype=np.float32) / sr
    audio = (0.4 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    features = extract_features(audio, sr)
    assert features.shape == (len(FEATURE_NAMES),)
    assert np.isfinite(features).all()


def test_silence_has_zero_roughness_and_valid_frame_features():
    audio = np.zeros(16000 * 2, dtype=np.float32)
    assert modulation_roughness(audio) == 0.0
    frame = extract_frame_features(audio)
    assert all(np.isfinite(v).all() for v in frame.values())
    assert np.all(frame["rms"] < 1e-4)


def test_modulation_roughness_responds_to_80hz_am():
    sr = 16000
    t = np.arange(sr * 2, dtype=np.float32) / sr
    audio = ((1.0 + 0.8 * np.sin(2 * np.pi * 80 * t)) * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    roughness = modulation_roughness(audio, sr)
    assert 0.0 <= roughness <= 1.0
    assert roughness > 0.05


class _FakeInterpreter:
    def __init__(self):
        self._scores = np.zeros((3, 521), dtype=np.float32)
        self._scores[:, 10] = [0.1, 0.7, 0.9]

    def get_input_details(self):
        return [{"index": 0, "shape": np.array([15600])}]

    def get_output_details(self):
        return [{"index": 1, "shape": np.array([3, 521])}]

    def resize_tensor_input(self, index, shape):
        assert index == 0

    def allocate_tensors(self):
        pass

    def set_tensor(self, index, value):
        assert index == 0
        assert value.dtype == np.float32

    def invoke(self):
        pass

    def get_tensor(self, index):
        assert index == 1
        return self._scores


def test_yamnet_representation_and_optional_embedding_api():
    det = YamnetDetector.__new__(YamnetDetector)
    det._interp = _FakeInterpreter()
    det._names = [f"class_{i}" for i in range(521)]
    det._distress_idx = [10]
    det._in_idx = 0
    det._out_idx = 1
    det._embedding_out_idx = None
    audio = np.zeros(16000, dtype=np.float32)
    matrix = det.frame_scores(audio)
    vector = det.class_score_vector(audio)
    assert matrix.shape == (3, 521)
    assert vector.shape == (521,)
    assert np.isfinite(vector).all()
    assert det.embedding(audio) is None
    assert det.distress_score(audio) == 0.9
