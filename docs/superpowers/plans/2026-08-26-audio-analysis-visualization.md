# VanniKawachh Audio Analysis Visualization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared phone-node-to-hub distress decision explainable with live waveform, spectral evidence, temporal peak state, and hub incident evidence.

**Architecture:** Add deterministic frame analysis and a temporal peak state machine in the hub package. The node page produces compact frames from its real Web Audio analyser and posts only the final captured clip for YAMNet/fusion; the server attaches the same analysis summary to the resulting incident. Both dashboards render the recorded state and never independently decide distress.

**Tech Stack:** Python 3.11, NumPy, FastAPI, browser Web Audio API/Canvas, vanilla JavaScript, pytest.

**Spec:** `C:\Users\Admin\.codex\attachments\8b0635f4-ad54-446f-91e9-baa93a753314\pasted-text.txt`

## Global Constraints

- Keep `stage1_phone` / YAMNet and the existing `fuse()` severity decision in the central server path.
- Do not infer distress from frequency alone; use energy, RMS, vocal range, persistence and existing classifier/fusion outcome.
- Keep analysis histories bounded and visualization work on `requestAnimationFrame`.
- Use environment-backed configuration; do not scatter magic thresholds.
- Preserve existing location, simulation, LoRa/fusion and autonomous dispatch behavior.

---

### Task 1: Shared audio analysis and temporal peak state

**Files:**
- Create: `hub/audio_analysis.py`
- Modify: `hub/config.py`
- Test: `tests/test_audio_analysis.py`

**Interfaces:**
- Produces: `AudioAnalysisFrame`, `AudioAnalysisSession`, `analyze_frame(samples, sample_rate)`.
- Consumes: `HubConfig` audio thresholds.

- [ ] **Step 1: Write failing frequency and state-machine tests**

```python
def test_dominant_frequency_tracks_a_1200_hz_tone():
    frame = analyzer.process(tone(1200, seconds=.1), 16000, now_ms=0)
    assert frame.dominant_frequency_hz == pytest.approx(1200, abs=60)

def test_short_peak_is_not_confirmed_then_sustained_peak_is():
    assert analyzer.process(peak, 16000, now_ms=900).state != "DISTRESS_CONFIRMED"
    assert analyzer.process(peak, 16000, now_ms=2000).state == "PEAK_SUSTAINED"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `python -m pytest tests/test_audio_analysis.py -v`

- [ ] **Step 3: Implement the bounded analyser**

```python
@dataclass
class AudioAnalysisFrame:
    timestamp_ms: int
    rms_amplitude: float
    dominant_frequency_hz: float
    peak_magnitude: float
    spectral_energy: float
    noise_floor: float
    frequency_threshold_hz: float
    is_peak: bool
    peak_duration_ms: int
    state: str
```

- [ ] **Step 4: Run focused and existing hub tests**

Run: `python -m pytest tests/test_audio_analysis.py tests/test_hub.py -v`

### Task 2: Attach explainable evidence to hub incidents

**Files:**
- Modify: `hub/pipeline.py`
- Modify: `hub/webapp.py`
- Test: `tests/test_hub.py`

**Interfaces:**
- Consumes: `AudioAnalysisFrame` summary and classifier label/confidence.
- Produces: `/phone-alert` and `/incidents` fields named `audio_analysis`, `confirmation_reasons`, `timeline`.

- [ ] **Step 1: Write the failing incident serialization test**

```python
assert response["audio_analysis"]["dominant_frequency_hz"] > 0
assert "YAMNet" in response["confirmation_reasons"][0]
```

- [ ] **Step 2: Implement optional evidence fields on `Incident`**

```python
audio_analysis: dict | None = None
confirmation_reasons: list[str] = field(default_factory=list)
timeline: list[dict] = field(default_factory=list)
```

- [ ] **Step 3: Make `/incidents` serialize those fields and run hub tests**

Run: `python -m pytest tests/test_hub.py -v`

### Task 3: Node live analysis visualization

**Files:**
- Modify: `hub/webapp.py` (`NODE_HTML` only)

**Interfaces:**
- Consumes: browser `AnalyserNode` time/frequency arrays and API confirmation fields.
- Produces: bounded waveform/history Canvas rendering, state, peak timer, and explanation.

- [ ] **Step 1: Add canvas elements and inactive/calibrating/live states**

```html
<canvas id="waveform" aria-label="Live audio waveform"></canvas>
<canvas id="spectrum" aria-label="Frequency spectrum"></canvas>
<canvas id="frequencyHistory" aria-label="Dominant frequency history"></canvas>
```

- [ ] **Step 2: Implement `requestAnimationFrame` drawing from `AnalyserNode`**

```js
analyser.getByteTimeDomainData(timeData);
analyser.getByteFrequencyData(freqData);
requestAnimationFrame(drawAudioAnalysis);
```

- [ ] **Step 3: Feed simulation audio through the same analyser-state updater before posting the clip**

- [ ] **Step 4: Ensure stop cancels animation, stops tracks, closes context, and resets temporary peak state**

### Task 4: Hub evidence visualization

**Files:**
- Modify: `hub/webapp.py` (`DASHBOARD_HTML` only)

**Interfaces:**
- Consumes: `/incidents` evidence fields.
- Produces: compact active-event audio panel, expandable incident evidence, and timestamped timeline.

- [ ] **Step 1: Extend incident renderer with an expandable evidence section**

```js
<details><summary>AUDIO EVIDENCE</summary><div>Peak frequency …</div></details>
```

- [ ] **Step 2: Add a compact canvas frequency-history graph using actual incident history**

- [ ] **Step 3: Render only server-provided timeline timestamps and confirmation reasons**

### Task 5: Verification and handoff

**Files:**
- Test: `tests/test_audio_analysis.py`, `tests/test_hub.py`

- [ ] **Step 1: Run the complete Python suite**

Run: `python -m pytest`

- [ ] **Step 2: Run dashboard build and static syntax checks**

Run: `npm --prefix dashboard run build`

- [ ] **Step 3: Start the hub and run Playwright checks for microphone-inactive, simulate, and rendered hub evidence states**

- [ ] **Step 4: Review browser console errors and bounded-history behavior**

- [ ] **Step 5: Commit only after all available checks pass**

## Self-Review

- The plan covers shared analysis, no-frequency-alone confirmation, node visualization, hub evidence/timeline, simulation, cleanup, tests and verification.
- All exposed interfaces use the same `AudioAnalysisFrame` / incident evidence naming.
- The image-reference service was unavailable (HTTP 403), so this plan follows the established VanniKawachh visual system rather than a generated asset.
