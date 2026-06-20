"""Recall-first threshold tuning for the ECG pathology classifiers.

Clinical objective (teacher's requirement): a screening tool must not MISS a
positive — false negatives are far costlier than false positives. So instead of
maximizing F1 (the balanced objective in eval_ecg_classifier.py), we pick, per
pathology, the **largest threshold whose validation recall >= TARGET** (default
0.95). Largest-threshold-that-still-hits-target = best precision we can keep
while guaranteeing the recall floor. Recall is monotonically decreasing in the
threshold, so this is a clean scan with no leakage: thresholds are chosen on
fold 9 (validation) and reported on fold 10 (test), exactly like the F1 tuning.

Runs instantly from the cached scores written by:
    python tools/eval_ecg_classifier.py --ptbxl <root> --tune-fold 9 --fold 10 \
        --save-scores tools/ecg_scores_finetuned.json

Usage:
    python tools/tune_ecg_recall.py [--target 0.95] [--scores tools/ecg_scores_finetuned.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

PATHOLOGIES = ["AFIB", "1AVB", "STACH", "SBRAD", "RBBB", "LBBB", "PVC"]


def metrics_at(probs, y, thr):
    pred = (probs >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {"thr": thr, "recall": rec, "precision": prec, "specificity": spec,
            "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def recall_first_threshold(probs, y, target):
    """Largest threshold whose recall >= target (best precision at the floor).

    If no threshold reaches target (degenerate), return the threshold that
    maximizes recall (i.e. the smallest scanned)."""
    grid = np.linspace(0.01, 0.99, 99)
    ok = [t for t in grid if metrics_at(probs, y, t)["recall"] >= target]
    if ok:
        return float(max(ok))
    return float(grid[0])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", default="tools/ecg_scores_finetuned.json")
    ap.add_argument("--target", type=float, default=0.95,
                    help="minimum recall to guarantee per pathology (default 0.95)")
    args = ap.parse_args()

    cache = json.loads(Path(args.scores).read_text())
    v, t = cache["val"], cache["test"]

    print(f"Recall-first ECG thresholds (target recall >= {args.target:.2f})")
    print("Tuned on fold 9 ({} val), reported on fold 10 ({} test). No leakage.".format(
        v["total"], t["total"]))
    print()
    hdr = "{:<7}{:>6}{:>9}{:>9}{:>8}{:>8}{:>6}{:>6}  {}".format(
        "path", "thr", "recall", "prec", "spec", "F1", "FN", "FP", "note")
    print(hdr)
    print("-" * len(hdr))

    new_thresholds = {}
    rec_sum = prec_sum = f1_sum = 0.0
    fn_total = fp_total = 0
    for p in PATHOLOGIES:
        pv = np.asarray(v["scores"][p], dtype=float)
        yv = np.asarray(v["truths"][p], dtype=int)
        pt = np.asarray(t["scores"][p], dtype=float)
        yt = np.asarray(t["truths"][p], dtype=int)
        thr = recall_first_threshold(pv, yv, args.target)
        m = metrics_at(pt, yt, thr)
        new_thresholds[p] = round(thr, 2)
        note = "" if m["recall"] >= args.target else "TEST RECALL BELOW TARGET"
        print("{:<7}{:>6.2f}{:>9.3f}{:>9.3f}{:>8.3f}{:>8.3f}{:>6}{:>6}  {}".format(
            p, thr, m["recall"], m["precision"], m["specificity"], m["f1"],
            m["fn"], m["fp"], note))
        rec_sum += m["recall"]; prec_sum += m["precision"]; f1_sum += m["f1"]
        fn_total += m["fn"]; fp_total += m["fp"]

    k = len(PATHOLOGIES)
    print()
    print("macro recall    : {:.3f}   (target >= {:.2f})".format(rec_sum / k, args.target))
    print("macro precision : {:.3f}   (the cost we pay for high recall)".format(prec_sum / k))
    print("macro F1        : {:.3f}".format(f1_sum / k))
    print("total false negatives on fold 10 (2,198 records): {}".format(fn_total))
    print("total false positives on fold 10                : {}".format(fp_total))
    print()
    print("Drop-in for ecg_pipeline.py (DETECTION_THRESHOLDS):")
    print("    DETECTION_THRESHOLDS = {")
    for p in PATHOLOGIES:
        print(f"        {p!r:8}: {new_thresholds[p]:.2f},")
    print("    }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
