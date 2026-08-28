# External Voice-Distress Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the fixed VanniKawachh YAMNet-plus-SVM classifier reproducibly evaluable against a labeled, held-out external WAV benchmark, with auditable metrics and false-positive evidence.

**Architecture:** Benchmarking does not train or mutate a model. A local runner will use the production YAMNet representation, feature construction, and SVM prediction path for every WAV and create file-level reports. The Colab notebook will invoke that runner instead of duplicating the evaluator.

**Tech Stack:** Python 3.13, NumPy, scikit-learn, pandas, matplotlib, TensorFlow Lite/YAMNet, pytest.

**Spec:** `VanniKawachh_End_to_End_External_Benchmark.ipynb`

## Global Constraints

- Do not retrain or mutate `hub/models/distress_svm.pkl` in the benchmark command.
- Use `get_detector`, `build_feature_vector`, and `DistressClassifier.predict_features` for every WAV.
- Only `distress`, `panic`, `scream_distress`, `pain`, and `cry_distress` map to positive truth.
- Require `path,label`, both binary truth classes, existing WAVs, and supported PCM widths.
- Report accuracy, balanced accuracy, precision, recall, binary macro-F1, specificity, FPR, TN/FP/FN/TP, and false-positive files.
- A zero-FP result applies only to the exact finite benchmark; it is not proof of zero real-world false triggers.
- Preserve unrelated untracked work and reject a source that overlaps model training as an external benchmark.

---

### Task 1: Add a testable local benchmark runner

**Files:**
- Create: `hub/external_benchmark.py`
- Create: `tests/test_external_benchmark.py`

**Interfaces:**
- Consumes: `labels.csv` (`path,label`), `hub.distress_classifier.DistressClassifier`, `build_feature_vector`, and `hub.yamnet_detector.get_detector`.
- Produces: `run_benchmark(benchmark_dir: Path, output_dir: Path, model_dir: Path) -> dict` and `python -m hub.external_benchmark --benchmark ... --output ... [--model-dir ...]`.

- [ ] **Step 1: Write failing metric and validation tests**

```python
def test_summary_uses_binary_macro_f1_and_lists_false_positives():
    summary, paths = summarize_rows(rows)
    assert summary["macro_f1"] == pytest.approx(expected_macro_f1)
    assert paths == ["b.wav"]
```

- [ ] **Step 2: Run the focused test to prove the runner is absent**

Run: `python -m pytest tests/test_external_benchmark.py -v`

Expected: FAIL because `hub.external_benchmark` does not exist.

- [ ] **Step 3: Implement deterministic production-path inference and reports**

```python
def run_benchmark(benchmark_dir: Path, output_dir: Path, model_dir: Path) -> dict:
    labels = load_labels(benchmark_dir)
    rows = [infer_one(row, get_detector(), DistressClassifier(model_path=str(model_dir / "distress_svm.pkl"))) for row in labels]
    summary, false_positive_paths = summarize_rows(rows)
    write_reports(rows, summary, false_positive_paths, output_dir, model_dir)
    return summary
```

- [ ] **Step 4: Verify focused and full unit tests**

Run: `python -m pytest tests/test_external_benchmark.py -v; python -m pytest`

Expected: PASS.

- [ ] **Step 5: Commit the runner and tests**

Run: `git add hub/external_benchmark.py tests/test_external_benchmark.py; git commit -m "feat: add reproducible external distress benchmark runner"`

### Task 2: Make Colab use the shared evaluator

**Files:**
- Modify: `VanniKawachh_End_to_End_External_Benchmark.ipynb`
- Modify: `tests/test_external_benchmark.py`

**Interfaces:**
- Consumes: `python -m hub.external_benchmark --benchmark /content/external_benchmark --output /content/external_benchmark_output --model-dir hub/models`.
- Produces: display of shared `summary.json`, `results.csv`, `false_positives.csv`, and `confusion_matrix.png`.

- [ ] **Step 1: Add a failing notebook-structure test**

```python
def test_notebook_calls_shared_runner():
    assert "hub.external_benchmark" in notebook_source("VanniKawachh_End_to_End_External_Benchmark.ipynb")
```

- [ ] **Step 2: Run it to verify the current duplicate notebook evaluator fails**

Run: `python -m pytest tests/test_external_benchmark.py::test_notebook_calls_shared_runner -v`

Expected: FAIL.

- [ ] **Step 3: Replace inline prediction and metric cells with the shared command**

```python
completed = subprocess.run([sys.executable, "-m", "hub.external_benchmark", "--benchmark", str(BENCH), "--output", "/content/external_benchmark_output", "--model-dir", str(MODEL_DIR)], check=True, text=True, capture_output=True)
```

- [ ] **Step 4: Run notebook-structure and full tests**

Run: `python -m pytest tests/test_external_benchmark.py -v; python -m pytest`

Expected: PASS.

- [ ] **Step 5: Commit the notebook update**

Run: `git add VanniKawachh_End_to_End_External_Benchmark.ipynb tests/test_external_benchmark.py; git commit -m "refactor: share external benchmark evaluator with Colab"`

### Task 3: Record a genuine external run

**Files:**
- Create: `benchmark-results/<dataset-id>/README.md`
- Create: `benchmark-results/<dataset-id>/summary.json`
- Create: `benchmark-results/<dataset-id>/results.csv`
- Create: `benchmark-results/<dataset-id>/false_positives.csv`
- Create: `benchmark-results/<dataset-id>/confusion_matrix.png`

**Interfaces:**
- Consumes: a trained artifact and a source-licensed, non-overlapping external WAV dataset with `labels.csv`.
- Produces: results tied to model SHA-256, source version/license, label mapping, command, and file-level errors/false positives.

- [ ] **Step 1: Verify provenance and run without retraining**

Run: `python -m hub.external_benchmark --benchmark <external-dir> --output benchmark-results/<dataset-id> --model-dir hub/models`

Expected: a report or a clear prerequisite error; never a fabricated result.

- [ ] **Step 2: Inspect all false-positive evidence and summary**

Run: `Get-Content benchmark-results/<dataset-id>/summary.json; Import-Csv benchmark-results/<dataset-id>/false_positives.csv`

Expected: reported FP total matches exactly.

- [ ] **Step 3: Run the unit tier after the benchmark**

Run: `python -m pytest`

Expected: PASS.

- [ ] **Step 4: Commit evidence only when model and dataset licenses allow it**

Run: `git add benchmark-results/<dataset-id>; git commit -m "test: record external voice-distress benchmark"`
