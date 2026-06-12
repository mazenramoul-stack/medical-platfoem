"""Evaluation harness for the fine-tuned BIOT IIIC 6-class head on Kaggle-HMS.

Runs the deployed classifier on a *patient-disjoint* held-out split of HMS and
reports the metrics that matter under IIIC's heavy class imbalance:
  balanced accuracy, Cohen's kappa, macro & weighted F1, per-class precision/
  recall/F1, the 6x6 confusion matrix, and — since HMS labels are expert *vote*
  distributions (soft labels) — the mean KL divergence (the standard HMS metric).

Reuses the pipeline preprocessing + model, so numbers reflect production behaviour.

Usage (from project root, after training a head):
    python tools/eval_eeg.py --hms-dir data/hms
    python tools/eval_eeg.py --hms-dir data/hms --weights backend/models_weights/biot/biot_iiic.pt --limit 2000
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

DEFAULT_WEIGHTS = BACKEND_DIR / "models_weights" / "biot" / "biot_iiic.pt"
DEFAULT_ENCODER = BACKEND_DIR / "models_weights" / "biot" / "EEG-PREST-16-channels.ckpt"


def _confusion(y_true, y_pred, k=6):
    c = np.zeros((k, k), dtype=np.int64)
    for t, p in zip(y_true, y_pred):
        c[t, p] += 1
    return c


def _metrics_from_confusion(c):
    k = c.shape[0]
    n = c.sum()
    tp = np.diag(c).astype(np.float64)
    col = c.sum(axis=0).astype(np.float64)   # predicted per class
    row = c.sum(axis=1).astype(np.float64)   # true support per class
    precision = np.divide(tp, col, out=np.zeros(k), where=col > 0)
    recall = np.divide(tp, row, out=np.zeros(k), where=row > 0)
    f1 = np.divide(2 * precision * recall, precision + recall,
                   out=np.zeros(k), where=(precision + recall) > 0)
    present = row > 0
    balanced_acc = float(recall[present].mean()) if present.any() else 0.0
    macro_f1 = float(f1[present].mean()) if present.any() else 0.0
    weighted_f1 = float((f1 * row).sum() / n) if n else 0.0
    po = tp.sum() / n if n else 0.0
    pe = (row * col).sum() / (n * n) if n else 0.0
    kappa = (po - pe) / (1 - pe) if (1 - pe) else 0.0
    accuracy = float(po)
    return {
        "accuracy": accuracy, "balanced_acc": balanced_acc, "kappa": float(kappa),
        "macro_f1": macro_f1, "weighted_f1": weighted_f1,
        "precision": precision, "recall": recall, "f1": f1, "support": row.astype(int),
    }


def _kl_divergence(vote_dists, pred_probs):
    """Mean KL(true || pred) over samples; both rows sum to 1."""
    eps = 1e-7
    p = np.clip(np.asarray(vote_dists), eps, 1.0)
    q = np.clip(np.asarray(pred_probs), eps, 1.0)
    p = p / p.sum(axis=1, keepdims=True)
    q = q / q.sum(axis=1, keepdims=True)
    return float(np.mean(np.sum(p * np.log(p / q), axis=1)))


def main() -> int:
    import torch

    from apps.inference.biot import BIOTClassifier
    from apps.inference.eeg_preprocess import IIIC_CLASSES
    from eeg_hms import iter_segments, load_index, patient_split  # noqa: E402

    ap = argparse.ArgumentParser(description="Evaluate the BIOT IIIC head on HMS.")
    ap.add_argument("--hms-dir", required=True, help="local HMS dir (train.csv + train_eegs/)")
    ap.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="fine-tuned classifier ckpt")
    ap.add_argument("--encoder", default=str(DEFAULT_ENCODER))
    ap.add_argument("--limit", type=int, default=4000, help="max windows indexed (match training)")
    ap.add_argument("--test-frac", type=float, default=0.2, help="patient-level test fraction (match training)")
    ap.add_argument("--seed", type=int, default=0, help="split seed (match training)")
    args = ap.parse_args()

    if not Path(args.weights).exists():
        print(f"ERROR: fine-tuned head not found at {args.weights}\n"
              f"Train one first: python tools/train_eeg_head.py --hms-dir {args.hms_dir}",
              file=sys.stderr)
        return 2

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = BIOTClassifier(n_classes=6, n_channels=16, n_fft=200, hop_length=100)
    state = torch.load(args.weights, map_location=device)
    state = state.get("state_dict", state) if isinstance(state, dict) else state
    model.load_state_dict(state)
    model.eval().to(device)
    print(f"Device: {device}  (BIOT IIIC classifier loaded from {Path(args.weights).name})\n")

    # reproduce the SAME patient-disjoint held-out split the trainer used
    samples = load_index(args.hms_dir, limit=args.limit, balanced=True, seed=args.seed)
    _, test_s = patient_split(samples, test_frac=args.test_frac, seed=args.seed)
    if not test_s:
        print("No test windows. Check --hms-dir / --limit / parquet availability.", file=sys.stderr)
        return 1

    y_true, y_pred, votes, probs = [], [], [], []
    with torch.no_grad():
        for s, seg in iter_segments(args.hms_dir, test_s):
            x = torch.from_numpy(seg[None].astype(np.float32)).to(device)
            p = torch.softmax(model(x), dim=1).cpu().numpy()[0]
            y_true.append(s["label"]); y_pred.append(int(p.argmax()))
            votes.append(s["votes"]); probs.append(p)
    n = len(y_true)
    if n == 0:
        print("No test windows could be loaded (parquet files missing?).", file=sys.stderr)
        return 1

    c = _confusion(np.array(y_true), np.array(y_pred))
    m = _metrics_from_confusion(c)
    kl = _kl_divergence(votes, probs)

    print(f"BIOT / IIIC evaluation — {n} windows (patient-disjoint held-out split)\n")
    print("Headline (imbalance-aware):")
    print(f"  Balanced accuracy : {m['balanced_acc']:.3f}")
    print(f"  Cohen's kappa     : {m['kappa']:.3f}")
    print(f"  Macro F1          : {m['macro_f1']:.3f}")
    print(f"  Weighted F1       : {m['weighted_f1']:.3f}")
    print(f"  KL divergence     : {kl:.3f}   (true votes || predicted, lower is better)")
    print(f"  Raw accuracy      : {m['accuracy']:.3f}   (reported last — misleading under imbalance)\n")

    print("Per-class:")
    print(f"  {'class':<7}{'prec':>7}{'rec':>7}{'f1':>7}{'support':>9}")
    for i, name in enumerate(IIIC_CLASSES):
        print(f"  {name:<7}{m['precision'][i]:>7.3f}{m['recall'][i]:>7.3f}"
              f"{m['f1'][i]:>7.3f}{m['support'][i]:>9d}")

    print("\nConfusion matrix (rows = true, cols = predicted):")
    print("        " + "".join(f"{n2:>7}" for n2 in IIIC_CLASSES))
    for i, name in enumerate(IIIC_CLASSES):
        print(f"  {name:<6}" + "".join(f"{c[i, j]:>7d}" for j in range(6)))

    # --- binary screening reframe: harmful pattern (any of 5) vs Other -------
    # For a SCREEN, the clinically critical metric is "did a window with harmful
    # activity get FLAGGED for review", not which exact pattern was named. IIIC
    # type-confusion (e.g. seizure vs GPD) is an inter-rater-ambiguous labelling
    # problem; type-vs-Other is what actually routes a patient to a neurologist.
    OTHER = IIIC_CLASSES.index("Other") if "Other" in IIIC_CLASSES else 5
    yt = np.array(y_true); yp = np.array(y_pred)
    abn_true, abn_pred = yt != OTHER, yp != OTHER
    tp = int((abn_true & abn_pred).sum()); fn = int((abn_true & ~abn_pred).sum())
    fp = int((~abn_true & abn_pred).sum()); tn = int((~abn_true & ~abn_pred).sum())
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    SZ = IIIC_CLASSES.index("SZ") if "SZ" in IIIC_CLASSES else 0
    sz_mask = yt == SZ
    sz_caught, sz_n = int((sz_mask & abn_pred).sum()), int(sz_mask.sum())
    print("\nBinary screen — harmful pattern (any of the 5) vs Other:")
    print(f"  abnormal-detection RECALL    : {rec:.3f}   ({fn} harmful windows missed as 'Other')")
    print(f"  abnormal-detection precision : {prec:.3f}")
    print(f"  specificity (Other correct)  : {spec:.3f}")
    print(f"  seizure flagged as harmful   : {sz_caught}/{sz_n} = "
          f"{(sz_caught / sz_n if sz_n else 0):.3f}  (routed for review, even if mislabelled)")
    print("  NOTE: 6-way TYPE accuracy stays modest (IIIC is inter-rater-ambiguous);")
    print("  this screen must not be used to RULE OUT a seizure by type — only to route.")

    if n < 200:
        print("\nNOTE: small sample — for report-grade numbers evaluate the full split (larger --limit).")
    print("\nReproduce:")
    print(f"  python tools/eval_eeg.py --hms-dir {args.hms_dir} --weights {args.weights} "
          f"--limit {args.limit} --seed {args.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
