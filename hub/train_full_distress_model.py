"""One-command local training for the project's full distress model.

Run from the repository root:
    python -m hub.train_full_distress_model

This is intentionally a local-data command. It prepares CREMA-D, ASVP-ESD and
ESC-50 on the user's machine, extracts the existing Phase-1/YAMNet features,
uses a speaker/source-aware split, trains the existing RBF SVM, reports metrics,
and saves the model artifact. It never changes the runtime pipeline itself.
"""
from __future__ import annotations

import argparse
import csv
import os
import pickle
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from hub.audio_features import FEATURE_NAMES
from hub.distress_classifier import CLASS_NAMES, build_feature_vector, train_classifier, save_artifacts
from hub.prepare_full_dataset import main as prepare_main
from hub.yamnet_detector import get_detector


def load_wav(path: str):
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate(); channels = wf.getnchannels(); width = wf.getsampwidth(); raw = wf.readframes(wf.getnframes())
    if width == 2: x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 1: x = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 4: x = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else: raise ValueError(f"unsupported WAV sample width {width}: {path}")
    if channels > 1: x = x.reshape(-1, channels).mean(axis=1)
    return x.astype(np.float32), int(sr)


def read_manifest(dataset: Path):
    manifest = dataset / "manifest.csv"
    if not manifest.exists(): raise SystemExit(f"Missing {manifest}; run dataset preparation first")
    rows=[]
    with manifest.open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p=Path(r["path"]); p=p if p.is_absolute() else dataset/p
            if p.exists() and r["label"] in CLASS_NAMES: rows.append((p,r["label"],r.get("group","") or str(p),r.get("source","")))
    return rows


def group_split(rows, test_size=0.25, seed=42):
    from sklearn.model_selection import GroupShuffleSplit, train_test_split
    y=np.asarray([r[1] for r in rows]); groups=np.asarray([r[2] for r in rows])
    if len(set(groups)) >= 6 and all(len(set(groups[y==c])) >= 2 for c in CLASS_NAMES):
        tr,te=next(GroupShuffleSplit(n_splits=1,test_size=test_size,random_state=seed).split(np.zeros(len(rows)),y,groups))
        if set(y[tr])==set(CLASS_NAMES) and set(y[te])==set(CLASS_NAMES): return tr,te,"group-aware"
    tr,te=train_test_split(np.arange(len(rows)),test_size=test_size,random_state=seed,stratify=y)
    return tr,te,"stratified-fallback"


def main():
    p=argparse.ArgumentParser(); p.add_argument("--dataset",default="dataset"); p.add_argument("--work-dir",default=".cache/audio-datasets"); p.add_argument("--max-per-class",type=int,default=400); p.add_argument("--output",default="hub/models"); p.add_argument("--seed",type=int,default=42); p.add_argument("--skip-prepare",action="store_true"); args=p.parse_args()
    if not args.skip_prepare:
        sys.argv=[sys.argv[0],"--work-dir",args.work_dir,"--dataset-dir",args.dataset,"--max-per-class",str(args.max_per_class),"--seed",str(args.seed)]
        prepare_main()
    dataset=Path(args.dataset); rows=read_manifest(dataset)
    if len(rows)<30: raise SystemExit("Prepared dataset is too small; need at least 30 curated clips.")
    counts={c:sum(r[1]==c for r in rows) for c in CLASS_NAMES}
    if any(v<5 for v in counts.values()): raise SystemExit(f"Insufficient class balance: {counts}")
    detector=get_detector()
    if detector is None: raise SystemExit("YAMNet is unavailable. Install/configure the existing YAMNet dependency first.")
    X=[]; y=[]; groups=[]
    cache=dataset/".feature_cache"; cache.mkdir(exist_ok=True)
    for i,(path,label,group,source) in enumerate(rows,1):
        key=__import__('hashlib').sha1(str(path).encode()).hexdigest()[:16]; cp=cache/f"{key}.npz"
        if cp.exists():
            vec=np.load(cp)["x"]
        else:
            audio,sr=load_wav(str(path)); rep=detector.embedding(audio,sr)
            if rep is None: rep=detector.class_score_vector(audio,sr)
            vec=build_feature_vector(audio,sr,np.asarray(rep,dtype=np.float32).reshape(-1)); np.savez_compressed(cp,x=vec)
        if not np.isfinite(vec).all(): raise SystemExit(f"Non-finite features: {path}")
        X.append(vec); y.append(label); groups.append(group); print(f"[{i}/{len(rows)}] {label:16s} {path}")
    X=np.asarray(X,dtype=np.float32); y=np.asarray(y)
    tr,te,split_method=group_split(rows,seed=args.seed)
    model=train_classifier(X[tr],y[tr])
    from sklearn.metrics import classification_report,confusion_matrix
    pred=model.predict(X[te]); print(f"\nSplit method: {split_method}"); print("Confusion matrix [background_noise, normal_human, distress]:"); print(confusion_matrix(y[te],pred,labels=list(CLASS_NAMES))); print("\nClassification report:"); print(classification_report(y[te],pred,labels=list(CLASS_NAMES),zero_division=0))
    truth=y[te]=="distress"; guessed=pred=="distress"; tn=int(((~truth)&(~guessed)).sum()); fp=int(((~truth)&guessed).sum()); fn=int((truth&(~guessed)).sum()); tp=int((truth&guessed).sum()); specificity=tn/max(1,tn+fp); fpr=fp/max(1,fp+tn)
    print(f"Distress-vs-rest: TP={tp} TN={tn} FP={fp} FN={fn}"); print(f"Specificity: {specificity:.3f}"); print(f"False-positive rate: {fpr:.3f}")
    save_artifacts(model,{"version":4,"classes":CLASS_NAMES,"yamnet_representation_dim":int(X.shape[1]-len(FEATURE_NAMES)),"acoustic_feature_names":tuple(FEATURE_NAMES),"feature_order":"[yamnet_representation, phase1_acoustic_features]","classifier":"rbf_svm","threshold":.70,"split_method":split_method,"seed":args.seed,"class_counts":counts,"sources":["ASVP-ESD","CREMA-D","ESC-50"]},args.output)
    print(f"\nModel saved to {args.output}/distress_svm.pkl")
    return 0
if __name__=="__main__": raise SystemExit(main())
