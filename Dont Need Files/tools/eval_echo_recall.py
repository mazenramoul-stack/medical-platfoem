"""Reduced-EF detection recall for the EchoNet EF regressor (clinical screening).

The echo model outputs a continuous ejection fraction (EF). The clinically
dangerous false negative is calling a patient with a REDUCED EF "normal". So we
reframe the regressor as a screening classifier at clinical cutoffs:

  - EF < 50 %  -> reduced LV systolic function (ASE/EACVI abnormal threshold)
  - EF < 40 %  -> HFrEF (heart failure with reduced EF)

A patient is FLAGGED for review when predicted EF < (cutoff + margin). Because
the regressor has error (MAE ~3-4 %), a safety margin lifts recall: flagging at
EF < 58 % catches almost every true EF < 50 %. This script finds, per cutoff,
the margin needed for detection recall >= TARGET, and reports the precision cost.

No retraining, no GPU — a decision rule on the existing regression output.
Caches per-video (true, pred) EF pairs so re-runs are instant.

Usage:
    python tools/eval_echo_recall.py "<EchoNet-Dynamic root>" [--limit N] [--target 0.95]
    python tools/eval_echo_recall.py --from-cache tools/echo_ef_pairs.json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

CACHE = PROJECT_ROOT / "tools" / "echo_ef_pairs.json"


def detection_metrics(true, pred, cutoff, flag_thr):
    """Positive = true EF < cutoff (truly reduced). Flag = pred EF < flag_thr."""
    tp = fp = fn = tn = 0
    for tval, pval in zip(true, pred):
        positive = tval < cutoff
        flagged = pval < flag_thr
        if positive and flagged:
            tp += 1
        elif positive and not flagged:
            fn += 1
        elif not positive and flagged:
            fp += 1
        else:
            tn += 1
    rec = tp / (tp + fn) if (tp + fn) else 1.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    return {"recall": rec, "precision": prec, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "n_pos": tp + fn}


def best_margin(true, pred, cutoff, target):
    """Smallest margin m (flag at cutoff+m) achieving recall >= target."""
    for m in range(0, 31):
        mm = detection_metrics(true, pred, cutoff, cutoff + m)
        if mm["recall"] >= target:
            return m, mm
    mm = detection_metrics(true, pred, cutoff, cutoff + 30)
    return 30, mm


def predict_pairs(root: Path, split: str, limit: int):
    import numpy as np  # noqa: F401
    from apps.inference.model_loader import ModelLoader
    from apps.inference.echo_pipeline import load_echo_video, _normalize, _predict_ef

    loader = ModelLoader()
    device = loader.get_device()
    _, ef_model = loader.get_echo_models()
    print(f"Device: {device}  (EchoNet EF model loaded)\n")

    fl = root / "FileList.csv"
    rows = [r for r in csv.DictReader(open(fl, newline=""))
            if r.get("Split", "").upper() == split.upper()]
    if limit:
        rows = rows[:limit]

    true, pred = [], []
    for i, r in enumerate(rows):
        name = r["FileName"]
        p = root / "Videos" / name
        if not p.exists() and not name.lower().endswith(".avi"):
            p = root / "Videos" / (name + ".avi")
        if not p.exists():
            continue
        try:
            ef_gt = float(r["EF"])
            frames = load_echo_video(str(p))
            ef_hat = _predict_ef(ef_model, _normalize(frames), device)
        except Exception as e:
            print(f"  ! {name}: {type(e).__name__}: {e}")
            continue
        true.append(ef_gt); pred.append(ef_hat)
        if (i + 1) % 50 == 0:
            print(f"  ...{i + 1} videos")
    return true, pred


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?", help="EchoNet-Dynamic root")
    ap.add_argument("--split", default="TEST")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--target", type=float, default=0.95)
    ap.add_argument("--from-cache", default=None, help="reuse cached EF pairs JSON")
    args = ap.parse_args()

    if args.from_cache:
        d = json.loads(Path(args.from_cache).read_text())
        true, pred = d["true"], d["pred"]
        print(f"Loaded {len(true)} cached EF pairs from {args.from_cache}\n")
    else:
        if not args.data_dir:
            print("ERROR: pass an EchoNet root or --from-cache.", file=sys.stderr)
            return 2
        true, pred = predict_pairs(Path(args.data_dir), args.split, args.limit)
        if not true:
            print("No videos evaluated.", file=sys.stderr)
            return 1
        CACHE.write_text(json.dumps({"true": true, "pred": pred}))
        print(f"\nCached {len(true)} EF pairs -> {CACHE}")

    import numpy as np
    t = np.array(true); p = np.array(pred)
    print(f"\nEchoNet EF — {len(t)} videos ({args.split} split)")
    print(f"  MAE {np.mean(np.abs(p - t)):.2f} %   RMSE {np.sqrt(np.mean((p - t) ** 2)):.2f} %")
    print()
    for cutoff in (50.0, 40.0):
        n_pos = int((t < cutoff).sum())
        naive = detection_metrics(true, pred, cutoff, cutoff)        # flag at the cutoff itself
        m, mm = best_margin(true, pred, cutoff, args.target)
        print(f"Reduced EF < {cutoff:.0f} %  ({n_pos} truly reduced of {len(t)})")
        print(f"  flag at EF<{cutoff:.0f} (no margin): recall {naive['recall']:.3f}  "
              f"precision {naive['precision']:.3f}  missed {naive['fn']}")
        print(f"  flag at EF<{cutoff + m:.0f} (+{m} margin): recall {mm['recall']:.3f}  "
              f"precision {mm['precision']:.3f}  missed {mm['fn']}  "
              f"(target recall >= {args.target:.2f})")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
