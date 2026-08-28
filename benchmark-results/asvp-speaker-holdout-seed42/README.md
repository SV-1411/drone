# ASVP Speaker-Disjoint Holdout Benchmark

This run evaluates the trained `distress_svm.pkl` (SHA-256 `2610638366a5c713d0fd437e4d05b188fe958a71c958ca596b719e33a0cdcbcf`) on the untouched test side of the group-aware ASVP-ESD split created with `seed=42`. The model was fitted only on the complementary partition. It uses the production YAMNet TFLite representation, `build_feature_vector`, and `DistressClassifier.predict_features` route for every WAV.

This is speaker-disjoint internal validation, not a source-external benchmark: ASVP-ESD also supplied the training positive class. H-VB was checked as the appropriate direct-distress external benchmark, but its Zenodo record is access-restricted and therefore its audio cannot be retrieved without approval.

| Metric | Value |
| --- | ---: |
| Samples | 218 |
| Accuracy | 0.9725 |
| Balanced accuracy | 0.9718 |
| Macro-F1 | 0.9679 |
| Distress precision / recall | 0.9420 / 0.9701 |
| Specificity | 0.9735 |
| False-positive rate | 0.0265 |
| TN / FP / FN / TP | 147 / 4 / 2 / 65 |

`false_positives.csv` lists all four false-triggered clips. The strict zero-FP requirement failed on this holdout. A finite zero-FP result, if achieved in a later benchmark, would still not establish zero real-world false triggers.
