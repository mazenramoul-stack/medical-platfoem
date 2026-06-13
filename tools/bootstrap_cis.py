"""Bootstrap 95% confidence intervals for the headline metrics.

Single-split point estimates (95.4 %, AUC 0.98, MAE 4.01 %, bal-acc 0.278) don't
say how stable they are. This script resamples the *cached* per-record predictions
(no model needed, no GPU) to attach a 95 % CI to each headline number, and runs a
permutation test for the EEG "above chance" claim.

Reads (all committed / produced by the eval harnesses):
  tools/echo_ef_pairs.json          {"true":[...], "pred":[...]}  (EchoNet EF)
  tools/mri_preds.json              [{"truth","pred","notumor_prob"}, ...]
  tools/ecg_scores_finetuned.json   {"test": {"scores":{path:[...]}, "truths":{path:[...]}}}
  tools/eeg_preds.json (optional)   {"y_true":[...], "y_pred":[...]}  (from eval_eeg.py --save-preds)

Usage:  python tools/bootstrap_cis.py [--boot 2000] [--seed 0]
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))

# Deployed ECG recall-first thresholds (apps/inference/ecg_pipeline.py:68-76).
ECG_RECALL_FIRST = {"AFIB": 0.10, "1AVB": 0.12, "STACH": 0.26, "SBRAD": 0.18,
                    "RBBB": 0.43, "LBBB": 0.66, "PVC": 0.49}
IIIC = ["SZ", "LPD", "GPD", "LRDA", "GRDA", "Other"]


def ci(samples, lo=2.5, hi=97.5):
    s = np.asarray([x for x in samples if x is not None and np.isfinite(x)], dtype=float)
    if s.size == 0:
        return (float("nan"), float("nan"))
    return float(np.percentile(s, lo)), float(np.percentile(s, hi))


def fmt(point, lohi, pct=False, dp=3):
    lo, hi = lohi
    if pct:
        return f"{point*100:.1f}% [{lo*100:.1f}, {hi*100:.1f}]"
    return f"{point:.{dp}f} [{lo:.{dp}f}, {hi:.{dp}f}]"


def auc_rank(scores, labels):
    """ROC-AUC via Mann-Whitney U (rank-based); None if degenerate."""
    from scipy.stats import rankdata
    scores = np.asarray(scores, float)
    labels = np.asarray(labels, int)
    finite = np.isfinite(scores)
    scores, labels = scores[finite], labels[finite]
    npos = int(labels.sum()); nneg = labels.size - npos
    if npos == 0 or nneg == 0:
        return None
    r = rankdata(scores)
    return (r[labels == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg)


def macro_f1_multiclass(truth, pred, classes):
    f1s = []
    for c in classes:
        tp = np.sum((pred == c) & (truth == c))
        fp = np.sum((pred == c) & (truth != c))
        fn = np.sum((pred != c) & (truth == c))
        p = tp / (tp + fp) if (tp + fp) else 0.0
        r = tp / (tp + fn) if (tp + fn) else 0.0
        f1s.append(2 * p * r / (p + r) if (p + r) else 0.0)
    return float(np.mean(f1s))


def boot_indices(n, B, rng):
    return [rng.integers(0, n, n) for _ in range(B)]


# --------------------------------------------------------------------------- #
def echo_cis(B, rng):
    path = os.path.join(HERE, "echo_ef_pairs.json")
    if not os.path.exists(path):
        return None
    d = json.load(open(path, encoding="utf-8"))
    t = np.asarray(d["true"], float); p = np.asarray(d["pred"], float)
    n = len(t)

    def mae(i): return float(np.mean(np.abs(t[i] - p[i])))
    def rmse(i): return float(np.sqrt(np.mean((t[i] - p[i]) ** 2)))
    def r2(i):
        ss_res = np.sum((t[i] - p[i]) ** 2)
        ss_tot = np.sum((t[i] - t[i].mean()) ** 2)
        return float(1 - ss_res / ss_tot) if ss_tot else float("nan")
    def red_recall(i):                      # reduced EF<50, deployed flag EF<55
        red = t[i] < 50; flag = p[i] < 55
        return float((red & flag).sum() / red.sum()) if red.sum() else float("nan")
    def red_prec(i):
        red = t[i] < 50; flag = p[i] < 55
        return float((red & flag).sum() / flag.sum()) if flag.sum() else float("nan")

    full = np.arange(n)
    idx = boot_indices(n, B, rng)
    return {
        "n": n,
        "EF MAE": (mae(full), ci([mae(i) for i in idx])),
        "EF RMSE": (rmse(full), ci([rmse(i) for i in idx])),
        "EF R2": (r2(full), ci([r2(i) for i in idx])),
        "reduced-EF recall (flag<55)": (red_recall(full), ci([red_recall(i) for i in idx])),
        "reduced-EF precision": (red_prec(full), ci([red_prec(i) for i in idx])),
    }


def mri_cis(B, rng):
    path = os.path.join(HERE, "mri_preds.json")
    if not os.path.exists(path):
        return None
    rows = json.load(open(path, encoding="utf-8"))

    def norm(s):
        s = str(s).lower().replace("_tumor", "")
        return "notumor" if s in ("no", "no_tumor", "notumor", "none") else s
    truth = np.array([norm(r["truth"]) for r in rows])
    pred = np.array([norm(r["pred"]) for r in rows])
    ntp = np.array([float(r.get("notumor_prob", 0.0)) for r in rows])
    classes = ["glioma", "meningioma", "notumor", "pituitary"]
    n = len(rows)

    def acc(i): return float(np.mean(truth[i] == pred[i]))
    def mf1(i): return macro_f1_multiclass(truth[i], pred[i], classes)
    def tumor_recall(i):                    # deployed notumor gate >= 0.99
        ti = truth[i]; pi = pred[i]; ni = ntp[i]
        is_tumor = ti != "notumor"
        cleared = (pi == "notumor") & (ni >= 0.99)   # accepted as notumor only if conf>=0.99
        detected = ~cleared
        return float(detected[is_tumor].mean()) if is_tumor.sum() else float("nan")

    full = np.arange(n)
    idx = boot_indices(n, B, rng)
    return {
        "n": n,
        "4-class accuracy": (acc(full), ci([acc(i) for i in idx])),
        "macro F1 (4-class)": (mf1(full), ci([mf1(i) for i in idx])),
        "tumour-detection recall (gate 0.99)": (tumor_recall(full), ci([tumor_recall(i) for i in idx])),
    }


def ecg_cis(B, rng):
    path = os.path.join(HERE, "ecg_scores_finetuned.json")
    if not os.path.exists(path):
        return None
    d = json.load(open(path, encoding="utf-8"))
    test = d["test"]
    scores = {k: np.asarray(v, float) for k, v in test["scores"].items()}
    truths = {k: np.asarray(v, int) for k, v in test["truths"].items()}
    paths = [p for p in ECG_RECALL_FIRST if p in scores]
    n = len(next(iter(scores.values())))

    def macro_auc(i):
        aucs = [auc_rank(scores[p][i], truths[p][i]) for p in paths]
        aucs = [a for a in aucs if a is not None]
        return float(np.mean(aucs)) if aucs else float("nan")

    def macro_recall(i):                    # at deployed recall-first thresholds
        recs = []
        for p in paths:
            y = truths[p][i]; det = scores[p][i] >= ECG_RECALL_FIRST[p]
            if y.sum():
                recs.append(float(det[y == 1].mean()))
        return float(np.mean(recs)) if recs else float("nan")

    full = np.arange(n)
    idx = boot_indices(n, B, rng)
    per_auc = {}
    for p in paths:
        a = auc_rank(scores[p], truths[p])
        per_auc[p] = (a, ci([auc_rank(scores[p][i], truths[p][i]) for i in idx]))
    return {
        "n": n,
        "macro ROC-AUC": (macro_auc(full), ci([macro_auc(i) for i in idx])),
        "macro recall (recall-first)": (macro_recall(full), ci([macro_recall(i) for i in idx])),
        "_per_auc": per_auc,
    }


def balanced_acc(truth, pred, k=6):
    recs = []
    for c in range(k):
        m = truth == c
        if m.sum():
            recs.append(float((pred[m] == c).mean()))
    return float(np.mean(recs)) if recs else 0.0


def eeg_cis(B, rng):
    path = os.path.join(HERE, "eeg_preds.json")
    if not os.path.exists(path):
        return None
    d = json.load(open(path, encoding="utf-8"))
    yt = np.asarray(d["y_true"], int); yp = np.asarray(d["y_pred"], int)
    n = len(yt)
    full = np.arange(n)
    idx = boot_indices(n, B, rng)
    point = balanced_acc(yt, yp)
    boot = [balanced_acc(yt[i], yp[i]) for i in idx]
    # permutation test vs chance: shuffle predictions, recompute balanced-acc
    perm = []
    for _ in range(B):
        perm.append(balanced_acc(yt, rng.permutation(yp)))
    perm = np.asarray(perm)
    p_value = float((np.sum(perm >= point) + 1) / (B + 1))
    return {
        "n": n,
        "balanced accuracy": (point, ci(boot)),
        "_perm": {"chance_mean": float(perm.mean()), "p_value": p_value,
                  "perm_95": float(np.percentile(perm, 95))},
    }


def main():
    ap = argparse.ArgumentParser(description="Bootstrap 95% CIs for headline metrics.")
    ap.add_argument("--boot", type=int, default=2000, help="bootstrap resamples")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)

    print(f"Bootstrap 95% CIs  (B={args.boot}, seed={args.seed})  [point [2.5, 97.5]]\n")

    echo = echo_cis(args.boot, rng)
    if echo:
        print(f"=== Echo (EchoNet, n={echo['n']} videos) ===")
        _mp, _ml = echo['EF MAE']; print(f"  EF MAE                         : {_mp:.2f}% [{_ml[0]:.2f}, {_ml[1]:.2f}]")
        _rp, _rl = echo['EF RMSE']; print(f"  EF RMSE                        : {_rp:.2f}% [{_rl[0]:.2f}, {_rl[1]:.2f}]")
        print(f"  EF R2                          : {fmt(*echo['EF R2'])}")
        print(f"  reduced-EF recall (flag<55)    : {fmt(*echo['reduced-EF recall (flag<55)'])}")
        print(f"  reduced-EF precision           : {fmt(*echo['reduced-EF precision'])}\n")

    mri = mri_cis(args.boot, rng)
    if mri:
        print(f"=== MRI (Swin classifier, n={mri['n']} images) ===")
        print(f"  4-class accuracy               : {fmt(*mri['4-class accuracy'], pct=True)}")
        print(f"  macro F1 (4-class)             : {fmt(*mri['macro F1 (4-class)'])}")
        print(f"  tumour-detection recall (0.99) : {fmt(*mri['tumour-detection recall (gate 0.99)'])}\n")

    ecg = ecg_cis(args.boot, rng)
    if ecg:
        print(f"=== ECG (ecglib x7, PTB-XL fold 10, n={ecg['n']} records) ===")
        print(f"  macro ROC-AUC                  : {fmt(*ecg['macro ROC-AUC'])}")
        print(f"  macro recall (recall-first)    : {fmt(*ecg['macro recall (recall-first)'])}")
        for p, (a, lohi) in ecg["_per_auc"].items():
            print(f"    AUC {p:<6}                   : {fmt(a, lohi)}")
        print()

    eeg = eeg_cis(args.boot, rng)
    if eeg:
        pm = eeg["_perm"]
        print(f"=== EEG (BIOT/IIIC, n={eeg['n']} windows) ===")
        print(f"  balanced accuracy              : {fmt(*eeg['balanced accuracy'])}")
        print(f"  permutation test vs chance     : chance~{pm['chance_mean']:.3f} "
              f"(95th pct {pm['perm_95']:.3f}), p = {pm['p_value']:.4f}")
        verdict = "ABOVE chance (significant)" if pm["p_value"] < 0.05 else "NOT significant"
        print(f"  -> {verdict}\n")
    else:
        print("=== EEG: tools/eeg_preds.json not found ===")
        print("  Generate it:  python tools/eval_eeg.py --limit 12000 --seed 0 --save-preds tools/eeg_preds.json")
        print("  then re-run this script.\n")


if __name__ == "__main__":
    main()
