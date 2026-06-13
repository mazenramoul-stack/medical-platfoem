"""Evaluation harness for the 12-lead ECG pathology classifiers (ecglib DenseNet-1D).

ECG diagnosis is MULTI-LABEL: each of the 7 pathology models is an independent
binary classifier, so the model is scored per-pathology, not as a single pick.

Two modes:

  (A) Prediction dump  — no labels needed. Runs inference on a folder of ECG
      files and prints the per-pathology probability table per record. Use this
      to smoke-test the pipeline or spot-check unlabeled data.

          python tools/eval_ecg_classifier.py samples/ecg

  (B) Labeled evaluation — computes per-pathology AUC, and precision/recall/F1
      at a probability threshold (default 0.5), plus TP/FP/FN/TN counts.

      Generic labels CSV (one row per record):
          record,labels
          00001_hr,AFIB;1AVB
          00002_hr,
          ...
      `record` matches the file basename (extension optional); `labels` is a
      ';'- or ','-separated list of POSITIVE pathology codes drawn from:
          AFIB 1AVB STACH SBRAD RBBB LBBB PVC

          python tools/eval_ecg_classifier.py path/to/records --labels labels.csv

      PTB-XL adapter (recommended for a report-grade number):
          python tools/eval_ecg_classifier.py --ptbxl path/to/ptbxl

      This reads ptbxl_database.csv, resolves each record's WFDB path via the
      `filename_hr` column, and maps PTB-XL SCP codes to ecglib's vocabulary
      using SCP_TO_ECGLIB below.

Faithful to deployment: replicates the exact preprocessing from
apps.inference.ecg_pipeline (0.5-40 Hz band-pass + per-lead z-score) and the
same `_scalar_probability` read-out. Skips NeuroKit2/plotting for speed.
First run loads the 7 ecglib models (cached thereafter). No database needed.
"""

from __future__ import annotations

import argparse
import ast
import csv
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

PATHOLOGIES = ["AFIB", "1AVB", "STACH", "SBRAD", "RBBB", "LBBB", "PVC"]
ECG_EXTS = {".csv", ".edf", ".dat", ".hea"}

# PTB-XL SCP-ECG codes -> ecglib pathology. ecglib's RBBB/LBBB are general
# (complete OR incomplete), so each maps to both PTB-XL variants.
SCP_TO_ECGLIB = {
    "AFIB": "AFIB",
    "1AVB": "1AVB",
    "STACH": "STACH",
    "SBRAD": "SBRAD",
    "CRBBB": "RBBB", "IRBBB": "RBBB",
    "CLBBB": "LBBB", "ILBBB": "LBBB",
    "PVC": "PVC",
}


# --- inference (deployed classification path, minus plotting) ---------------

def predict_probs(file_path: str, loader, np, torch):
    """Return {pathology: probability} for one ECG, matching ecg_pipeline."""
    from scipy.signal import butter, filtfilt

    from apps.inference.ecg_pipeline import _scalar_probability
    from apps.inference.utils import load_ecg_signal

    signal, fs = load_ecg_signal(file_path)              # (12, 5000)
    b, a = butter(4, [0.5, 40], btype="bandpass", fs=fs)
    filtered = filtfilt(b, a, signal, axis=1)
    norm = (filtered - filtered.mean(axis=1, keepdims=True)) / (filtered.std(axis=1, keepdims=True) + 1e-8)

    tensor = torch.from_numpy(norm).float().unsqueeze(0).to(loader.get_device())
    models = loader.get_ecg_models()
    out = {}
    for code, model in models.items():
        with torch.no_grad():
            out[code] = _scalar_probability(model(tensor))
    return out


# --- label sources ----------------------------------------------------------

def load_generic_labels(csv_path: Path) -> dict[str, set[str]]:
    """record-basename -> set of positive ecglib codes, from a generic CSV."""
    truth: dict[str, set[str]] = {}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rec = Path(str(row.get("record", "")).strip()).stem
            if not rec:
                continue
            raw = (row.get("labels") or "").replace(",", ";")
            codes = {c.strip().upper() for c in raw.split(";") if c.strip()}
            truth[rec] = {c for c in codes if c in PATHOLOGIES}
    return truth


def iter_ptbxl(ptbxl_dir: Path, min_likelihood: float, fold: int | None = None):
    """Yield (wfdb_record_path, set_of_positive_ecglib_codes) from PTB-XL.

    A SCP code counts as a positive label when its likelihood >= min_likelihood.
    PTB-XL convention: a present code with likelihood 0.0 is still a positive
    annotation, so the default min_likelihood=0 treats key-present as positive
    (matching the Wagner et al. benchmark). `fold` restricts to one strat_fold
    (use 10 for PTB-XL's official held-out test set).
    """
    db = ptbxl_dir / "ptbxl_database.csv"
    if not db.exists():
        print(f"ERROR: {db} not found — is this a PTB-XL root?", file=sys.stderr)
        return
    with open(db, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if fold is not None:
                try:
                    if int(float(row.get("strat_fold", -1))) != fold:
                        continue
                except (ValueError, TypeError):
                    continue
            fname = row.get("filename_hr") or row.get("filename_lr")
            if not fname:
                continue
            try:
                scp = ast.literal_eval(row.get("scp_codes", "{}") or "{}")
            except (ValueError, SyntaxError):
                scp = {}
            positives = {
                SCP_TO_ECGLIB[code]
                for code, lk in scp.items()
                if code in SCP_TO_ECGLIB and float(lk) >= min_likelihood
            }
            # PTB-XL's filename_hr has no extension (e.g. records500/00000/00001_hr);
            # append .dat so load_ecg_signal routes to its WFDB (.dat/.hea) branch.
            yield ptbxl_dir / (fname + ".dat"), positives


# --- metrics ----------------------------------------------------------------

def auc_score(scores, labels) -> float | None:
    """Dependency-free ROC-AUC via average-rank (Mann-Whitney U). None if degenerate."""
    import numpy as np
    from scipy.stats import rankdata

    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=int)
    finite = np.isfinite(scores)            # drop NaN/Inf scores so they can't poison the ranks
    scores, labels = scores[finite], labels[finite]
    n_pos = int(labels.sum())
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = rankdata(scores)
    return (ranks[labels == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def run_prediction_dump(paths, loader, np, torch) -> int:
    n = 0
    for p in paths:
        try:
            probs = predict_probs(str(p), loader, np, torch)
        except Exception as e:
            print(f"  ! {p.name}: {type(e).__name__}: {e}")
            continue
        n += 1
        top = sorted(probs.items(), key=lambda kv: -kv[1])
        cells = "  ".join(f"{c}={v:.2f}{'*' if v > 0.5 else ' '}" for c, v in top)
        print(f"  {p.name:<22} {cells}")
    if n == 0:
        print("\nNo ECG files found.")
        return 1
    print(f"\n{n} record(s).  '*' = probability > 0.5 (detected).  No labels -> no accuracy.")
    print("Provide --labels or --ptbxl to compute metrics.")
    return 0


def collect_scores(items, loader, np, torch, label="records"):
    """Run inference over items; return (scores, truths, total) as per-pathology lists."""
    scores = {c: [] for c in PATHOLOGIES}
    truths = {c: [] for c in PATHOLOGIES}
    total = 0
    for path, positives in items:
        try:
            probs = predict_probs(str(path), loader, np, torch)
        except Exception as e:
            print(f"  ! {Path(path).name}: {type(e).__name__}: {e}")
            continue
        total += 1
        for c in PATHOLOGIES:
            scores[c].append(probs.get(c, 0.0))
            truths[c].append(1 if c in positives else 0)
        if total % 200 == 0:
            print(f"  ...{total} {label}")
    return scores, truths, total


def best_threshold(s, y, np) -> float:
    """Threshold in (0,1) that maximizes F1 on (scores s, labels y). 0.5 if degenerate."""
    if int(y.sum()) == 0 or int(y.sum()) == len(y):
        return 0.5
    best_t, best_f1 = 0.5, -1.0
    for t in np.linspace(0.01, 0.99, 99):
        pred = (s >= t).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        if f1 > best_f1:
            best_f1, best_t = f1, float(t)
    return best_t


def tune_thresholds(scores, truths, np) -> dict:
    """Per-pathology F1-optimal thresholds."""
    return {c: best_threshold(np.asarray(scores[c]), np.asarray(truths[c]), np) for c in PATHOLOGIES}


def report_metrics(scores, truths, total, thresholds, np, title: str) -> dict:
    """Print the per-pathology metrics table; return {macro_f1, micro_f1, weighted_f1, macro_auc}."""
    print(f"\n{title}\n")
    print(f"{'pathology':<10}{'thr':>6}{'support':>8}{'AUC':>8}{'prec':>8}{'recall':>8}{'F1':>8}"
          f"{'TP':>6}{'FP':>6}{'FN':>6}{'TN':>6}")
    f1_sum = auc_sum = auc_count = 0.0
    wF1_sum = support_sum = 0.0
    TP = FP = FN = 0
    for c in PATHOLOGIES:
        y = np.asarray(truths[c]); s = np.asarray(scores[c])
        t = thresholds[c]
        pred = (s >= t).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum())
        fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum())
        tn = int(((pred == 0) & (y == 0)).sum())
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        auc = auc_score(s, y)
        support = int(y.sum())
        f1_sum += f1
        wF1_sum += f1 * support
        support_sum += support
        TP += tp; FP += fp; FN += fn
        if auc is not None:
            auc_sum += auc; auc_count += 1
        auc_str = f"{auc:>8.3f}" if auc is not None else f"{'n/a':>8}"
        print(f"{c:<10}{t:>6.2f}{support:>8}{auc_str}{prec:>8.3f}{rec:>8.3f}{f1:>8.3f}"
              f"{tp:>6}{fp:>6}{fn:>6}{tn:>6}")
    macro_f1 = f1_sum / len(PATHOLOGIES)
    weighted_f1 = (wF1_sum / support_sum) if support_sum else 0.0
    micro_prec = TP / (TP + FP) if (TP + FP) else 0.0
    micro_rec = TP / (TP + FN) if (TP + FN) else 0.0
    micro_f1 = 2 * micro_prec * micro_rec / (micro_prec + micro_rec) if (micro_prec + micro_rec) else 0.0
    macro_auc = auc_sum / auc_count if auc_count else 0.0
    print(f"  -> macro F1 {macro_f1:.3f}   micro F1 {micro_f1:.3f}   weighted F1 {weighted_f1:.3f}"
          + (f"   macro AUC {macro_auc:.3f}" if auc_count else ""))
    return {"macro_f1": macro_f1, "micro_f1": micro_f1, "weighted_f1": weighted_f1, "macro_auc": macro_auc}


def report_comprehensive(scores, truths, total, thresholds, np, title: str) -> None:
    """Print the FULL validation suite: per-pathology accuracy/sensitivity/
    specificity/precision/F1/AUC + counts, then multi-label aggregate metrics."""
    print(f"\n{title}")
    print(f"(threshold per pathology shown as 'thr'; {total} records)\n")
    print(f"{'pathology':<10}{'thr':>6}{'supp':>6}{'base':>7}{'AUC':>7}{'acc':>7}{'balAcc':>8}"
          f"{'sens':>7}{'spec':>7}{'prec':>7}{'F1':>7}{'TP':>5}{'FP':>5}{'FN':>5}{'TN':>6}")

    p_sum = r_sum = f_sum = auc_sum = auc_n = ba_sum = 0.0
    wp = wr = wf = supp_tot = 0.0
    TP = FP = FN = TN = 0
    for c in PATHOLOGIES:
        y = np.asarray(truths[c]); s = np.asarray(scores[c])
        pred = (s >= thresholds[c]).astype(int)
        tp = int(((pred == 1) & (y == 1)).sum()); fp = int(((pred == 1) & (y == 0)).sum())
        fn = int(((pred == 0) & (y == 1)).sum()); tn = int(((pred == 0) & (y == 0)).sum())
        supp = int(y.sum()); n = tp + fp + fn + tn
        acc = (tp + tn) / n if n else 0.0
        baseline = max(tp + fn, tn + fp) / n if n else 0.0   # majority-class predictor accuracy
        sens = tp / (tp + fn) if (tp + fn) else 0.0          # recall / true-positive rate
        spec = tn / (tn + fp) if (tn + fp) else 0.0          # true-negative rate
        bal_acc = (sens + spec) / 2                          # imbalance-robust accuracy
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        f1 = 2 * prec * sens / (prec + sens) if (prec + sens) else 0.0
        auc = auc_score(s, y)
        p_sum += prec; r_sum += sens; f_sum += f1; ba_sum += bal_acc
        wp += prec * supp; wr += sens * supp; wf += f1 * supp; supp_tot += supp
        TP += tp; FP += fp; FN += fn; TN += tn
        if auc is not None:
            auc_sum += auc; auc_n += 1
        auc_str = f"{auc:>7.3f}" if auc is not None else f"{'n/a':>7}"
        print(f"{c:<10}{thresholds[c]:>6.2f}{supp:>6}{baseline:>7.3f}{auc_str}{acc:>7.3f}{bal_acc:>8.3f}"
              f"{sens:>7.3f}{spec:>7.3f}{prec:>7.3f}{f1:>7.3f}{tp:>5}{fp:>5}{fn:>5}{tn:>6}")

    K = len(PATHOLOGIES)
    macro = (p_sum / K, r_sum / K, f_sum / K)
    weighted = ((wp / supp_tot, wr / supp_tot, wf / supp_tot) if supp_tot else (0, 0, 0))
    mp = TP / (TP + FP) if (TP + FP) else 0.0
    mr = TP / (TP + FN) if (TP + FN) else 0.0
    micro = (mp, mr, 2 * mp * mr / (mp + mr) if (mp + mr) else 0.0)

    # record-level (true) multi-label metrics
    S = np.array([scores[c] for c in PATHOLOGIES], dtype=float).T          # (total, K)
    THR = np.array([thresholds[c] for c in PATHOLOGIES], dtype=float)
    P = (S >= THR).astype(int)
    Y = np.array([truths[c] for c in PATHOLOGIES], dtype=int).T            # (total, K)
    subset_acc = float((P == Y).all(axis=1).mean())                        # exact-match
    hamming = float((P != Y).mean())                                       # per-label error rate
    inter = (P & Y).sum(axis=1); union = (P | Y).sum(axis=1)
    jaccard = float(np.where(union == 0, 1.0, inter / np.maximum(union, 1)).mean())

    print("\nAggregate metrics")
    print(f"  {'avg':<10}{'precision':>11}{'recall':>9}{'F1':>9}")
    print(f"  {'macro':<10}{macro[0]:>11.3f}{macro[1]:>9.3f}{macro[2]:>9.3f}")
    print(f"  {'micro':<10}{micro[0]:>11.3f}{micro[1]:>9.3f}{micro[2]:>9.3f}")
    print(f"  {'weighted':<10}{weighted[0]:>11.3f}{weighted[1]:>9.3f}{weighted[2]:>9.3f}")
    print(f"  mean AUC (ROC)          : {auc_sum / auc_n:.3f}" if auc_n else "  mean AUC : n/a")
    print(f"  macro balanced accuracy : {ba_sum / K:.3f}  (50% = trivial/all-negative model)")
    print("\nMulti-label (record-level)")
    print(f"  subset / exact-match accuracy : {subset_acc:.3f}")
    print(f"  Jaccard (example-based acc)   : {jaccard:.3f}")
    print(f"  Hamming loss (lower=better)   : {hamming:.3f}")
    print("\n  Note: plain 'acc' is inflated by class imbalance — compare it to 'base'")
    print("  (the majority/all-negative baseline). Use 'balAcc' = (sens+spec)/2, AUC,")
    print("  F1, sensitivity & specificity as the real measures of model quality.")


def run_labeled_eval(items, loader, np, torch, threshold: float) -> int:
    """Single-threshold evaluation over items (path, positive-codes)."""
    scores, truths, total = collect_scores(items, loader, np, torch)
    if total == 0:
        print("\nNo records evaluated.")
        return 1
    thresholds = {c: threshold for c in PATHOLOGIES}
    report_metrics(scores, truths, total, thresholds, np,
                   f"Evaluated {total} records at fixed threshold {threshold:.2f}")
    if total < 100:
        print("\nNOTE: small sample — indicative only. PTB-XL test split gives a")
        print("report-grade number:  python tools/eval_ecg_classifier.py --ptbxl path/to/ptbxl")
    return 0


def run_tuned_eval(tune_items, eval_items, loader, np, torch, default_threshold: float,
                   save_scores: str | None = None) -> int:
    """Tune per-pathology thresholds on tune_items (validation), then report
    test metrics at the default threshold (BEFORE) vs tuned thresholds (AFTER)."""
    print("Pass 1/2 — collecting validation scores to tune thresholds...")
    v_scores, v_truths, v_total = collect_scores(tune_items, loader, np, torch, "val records")
    if v_total == 0:
        print("\nNo validation records — cannot tune.")
        return 1
    thresholds = tune_thresholds(v_scores, v_truths, np)

    print(f"\nPass 2/2 — collecting test scores...")
    t_scores, t_truths, t_total = collect_scores(eval_items, loader, np, torch, "test records")
    if t_total == 0:
        print("\nNo test records evaluated.")
        return 1

    if save_scores:
        import json
        with open(save_scores, "w") as f:
            json.dump({"thresholds": thresholds,
                       "val": {"scores": v_scores, "truths": v_truths, "total": v_total},
                       "test": {"scores": t_scores, "truths": t_truths, "total": t_total}}, f)
        print(f"\nCached scores -> {save_scores}  (recompute any metric with --from-scores)")

    print(f"\n{'=' * 72}")
    print(f"Tuned on {v_total} validation records; evaluated on {t_total} test records.")
    print("Thresholds chosen to maximize F1 on the validation fold only (no test leakage).")
    print('=' * 72)

    default_t = {c: default_threshold for c in PATHOLOGIES}
    before = report_metrics(t_scores, t_truths, t_total, default_t, np,
                            f"BEFORE — fixed threshold {default_threshold:.2f} (original pipeline)")
    after = report_metrics(t_scores, t_truths, t_total, thresholds, np,
                           "AFTER — per-pathology tuned thresholds")

    print("\nTuned thresholds (drop-in for ecg_pipeline.py):")
    print("    DETECTION_THRESHOLDS = {")
    for c in PATHOLOGIES:
        print(f"        {c!r:8}: {thresholds[c]:.2f},")
    print("    }")
    print("\nImprovement (BEFORE -> AFTER):")
    for key, label in [("macro_f1", "macro F1   "), ("micro_f1", "micro F1   "),
                       ("weighted_f1", "weighted F1")]:
        d = after[key] - before[key]
        print(f"  {label}: {before[key]:.3f} -> {after[key]:.3f}  ({'+' if d >= 0 else ''}{d:.3f})")
    print(f"  macro AUC  : {after['macro_auc']:.3f}  (threshold-independent — unchanged by tuning)")
    report_comprehensive(t_scores, t_truths, t_total, thresholds, np,
                         "FULL VALIDATION SUITE — test fold @ tuned thresholds")
    return 0


def iter_ecg_files(root: Path):
    if root.is_file():
        yield root
        return
    seen = set()
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in ECG_EXTS:
            # collapse .dat/.hea pairs to a single record
            key = p.with_suffix("")
            if p.suffix.lower() in (".dat", ".hea"):
                if key in seen:
                    continue
                seen.add(key)
            yield p


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the ECG pathology classifiers.")
    ap.add_argument("data_dir", nargs="?", default=str(PROJECT_ROOT / "samples" / "ecg"),
                    help="ECG file or directory (ignored when --ptbxl is used)")
    ap.add_argument("--labels", help="generic labels CSV (record,labels)")
    ap.add_argument("--ptbxl", help="path to a PTB-XL root (contains ptbxl_database.csv)")
    ap.add_argument("--threshold", type=float, default=0.5, help="detection threshold (default 0.5)")
    ap.add_argument("--min-likelihood", type=float, default=0.0,
                    help="PTB-XL: min SCP likelihood to count a label positive "
                         "(default 0 = key-present, per the PTB-XL benchmark convention)")
    ap.add_argument("--fold", type=int, default=None,
                    help="PTB-XL: restrict to one strat_fold (use 10 for the official test set)")
    ap.add_argument("--tune-fold", type=int, default=None,
                    help="PTB-XL: tune per-pathology thresholds on this fold (e.g. 9 = validation), "
                         "then report BEFORE/AFTER on --fold. Requires --fold.")
    ap.add_argument("--save-scores", default=None,
                    help="cache raw scores+truths to this JSON file (use with --tune-fold)")
    ap.add_argument("--from-scores", default=None,
                    help="recompute the tuned BEFORE/AFTER report from a cached --save-scores file "
                         "(no inference, instant)")
    ap.add_argument("--limit", type=int, default=0, help="max records (0 = all)")
    args = ap.parse_args()

    import numpy as np

    # Fast path: recompute metrics from cached scores, no model inference.
    if args.from_scores:
        import json
        with open(args.from_scores) as f:
            cache = json.load(f)
        thresholds = cache["thresholds"]
        v, t = cache["val"], cache["test"]
        print(f"Recomputed from {args.from_scores}: "
              f"{v['total']} val / {t['total']} test records (no inference)")
        print('=' * 72)
        default_t = {c: args.threshold for c in PATHOLOGIES}
        before = report_metrics(t["scores"], t["truths"], t["total"], default_t, np,
                                f"BEFORE — fixed threshold {args.threshold:.2f}")
        after = report_metrics(t["scores"], t["truths"], t["total"], thresholds, np,
                               "AFTER — per-pathology tuned thresholds")
        print("\nImprovement (BEFORE -> AFTER):")
        for key, label in [("macro_f1", "macro F1   "), ("micro_f1", "micro F1   "),
                           ("weighted_f1", "weighted F1")]:
            d = after[key] - before[key]
            print(f"  {label}: {before[key]:.3f} -> {after[key]:.3f}  ({'+' if d >= 0 else ''}{d:.3f})")
        report_comprehensive(t["scores"], t["truths"], t["total"], thresholds, np,
                             "FULL VALIDATION SUITE — test fold @ tuned thresholds")
        return 0

    import torch
    from apps.inference.model_loader import ModelLoader

    loader = ModelLoader()
    print(f"Device: {loader.get_device()}  (first run loads 7 ecglib models)\n")

    def capped(it):
        if not args.limit:
            yield from it; return
        for i, x in enumerate(it):
            if i >= args.limit:
                break
            yield x

    if args.ptbxl:
        root = Path(args.ptbxl)
        if args.tune_fold is not None:
            if args.fold is None:
                print("ERROR: --tune-fold requires --fold (the test fold).", file=sys.stderr)
                return 2
            print(f"PTB-XL tuned eval: {root}  tune_fold={args.tune_fold} -> test_fold={args.fold}, "
                  f"min_likelihood={args.min_likelihood}")
            tune_items = capped(iter_ptbxl(root, args.min_likelihood, args.tune_fold))
            eval_items = capped(iter_ptbxl(root, args.min_likelihood, args.fold))
            return run_tuned_eval(tune_items, eval_items, loader, np, torch, args.threshold,
                                  save_scores=args.save_scores)
        fold_msg = f", fold={args.fold}" if args.fold is not None else " (all folds)"
        print(f"PTB-XL eval: {root}{fold_msg}, min_likelihood={args.min_likelihood}")
        return run_labeled_eval(capped(iter_ptbxl(root, args.min_likelihood, args.fold)),
                                loader, np, torch, args.threshold)

    root = Path(args.data_dir)
    if not root.exists():
        print(f"ERROR: path not found: {root}", file=sys.stderr)
        return 2

    if args.labels:
        truth = load_generic_labels(Path(args.labels))
        items = ((p, truth.get(p.stem, set())) for p in iter_ecg_files(root) if p.stem in truth)
        print(f"Labeled eval: {root}  (labels: {args.labels}, {len(truth)} entries)")
        return run_labeled_eval(capped(items), loader, np, torch, args.threshold)

    print(f"Prediction dump (no labels): {root}\n")
    return run_prediction_dump(capped(iter_ecg_files(root)), loader, np, torch)


if __name__ == "__main__":
    raise SystemExit(main())
