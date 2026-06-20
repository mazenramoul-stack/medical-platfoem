"""Evaluation harness for the EchoNet-Dynamic echo models.

Validates on the EchoNet-Dynamic dataset (Stanford AIMI):
  - **EF regression** — MAE / RMSE / R^2 vs ground-truth EF (FileList.csv)
  - **LV segmentation** — Dice on the human-traced ED/ES frames (VolumeTracings.csv)

Reuses the deployed pipeline's preprocessing + models, so the numbers reflect the
system as it runs in production.

Usage (from project root, with ECHONET weights set — see model_loader):
    python tools/eval_echo.py "<EchoNet-Dynamic root>"            # full TEST split
    python tools/eval_echo.py "<root>" --limit 100 --split TEST
The root must contain FileList.csv and a Videos/ folder (VolumeTracings.csv
optional, enables segmentation Dice).
"""

from __future__ import annotations

import argparse
import csv
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _resolve_video(root: Path, name: str) -> Path | None:
    p = root / "Videos" / name
    if p.exists():
        return p
    if not name.lower().endswith(".avi"):
        p = root / "Videos" / (name + ".avi")
        if p.exists():
            return p
    return None


def gt_mask_from_tracing(rows, np, cv2, size=112):
    """Reconstruct a filled LV mask from EchoNet VolumeTracings rows (one frame)."""
    side_a = [(float(r["X1"]), float(r["Y1"])) for r in rows]
    side_b = [(float(r["X2"]), float(r["Y2"])) for r in rows]
    poly = np.array(side_a + side_b[::-1], dtype=np.int32)
    mask = np.zeros((size, size), dtype=np.uint8)
    if len(poly) >= 3:
        cv2.fillPoly(mask, [poly], 1)
    return mask.astype(bool)


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate EchoNet EF + segmentation.")
    ap.add_argument("data_dir", help="EchoNet-Dynamic root (has FileList.csv + Videos/)")
    ap.add_argument("--split", default="TEST", help="split to evaluate (default TEST)")
    ap.add_argument("--limit", type=int, default=0, help="max videos (0 = all)")
    args = ap.parse_args()

    root = Path(args.data_dir)
    filelist = root / "FileList.csv"
    if not filelist.exists():
        print(f"ERROR: {filelist} not found.", file=sys.stderr)
        return 2

    import numpy as np
    try:
        import cv2
    except ImportError:
        print("ERROR: opencv not installed (pip install opencv-python-headless)", file=sys.stderr)
        return 2

    from apps.inference.model_loader import ModelLoader
    from apps.inference.echo_pipeline import (
        load_echo_video, _normalize, _predict_ef, _predict_segmentation,
    )

    loader = ModelLoader()
    device = loader.get_device()
    seg_model, ef_model = loader.get_echo_models()
    print(f"Device: {device}  (EchoNet models loaded)\n")

    # ground-truth EF per file
    rows = [r for r in csv.DictReader(open(filelist, newline=""))
            if r.get("Split", "").upper() == args.split.upper()]
    if args.limit:
        rows = rows[: args.limit]

    # optional segmentation traces, grouped by (file, frame)
    traces = defaultdict(lambda: defaultdict(list))
    vt = root / "VolumeTracings.csv"
    if vt.exists():
        for r in csv.DictReader(open(vt, newline="")):
            traces[r["FileName"]][r["Frame"]].append(r)

    ef_true, ef_pred = [], []
    dice_scores = []
    n = 0
    for r in rows:
        name = r["FileName"]
        path = _resolve_video(root, name)
        if path is None:
            continue
        try:
            ef_gt = float(r["EF"])
            frames = load_echo_video(str(path))
            norm = _normalize(frames)
            pred = _predict_ef(ef_model, norm, device)
        except Exception as e:
            print(f"  ! {name}: {type(e).__name__}: {e}")
            continue
        ef_true.append(ef_gt); ef_pred.append(pred)
        n += 1

        # segmentation Dice on traced frames (if available). FileList omits the
        # .avi extension while VolumeTracings includes it — try both spellings.
        key = next((c for c in (name, name + ".avi", name.replace(".avi", "")) if c in traces), None)
        if key:
            masks, _ = _predict_segmentation(seg_model, norm, device)
            for frame_str, frows in traces[key].items():
                try:
                    fi = int(float(frame_str))
                    if 0 <= fi < masks.shape[0]:
                        gt = gt_mask_from_tracing(frows, np, cv2)
                        pr = masks[fi]
                        inter = (gt & pr).sum(); s = gt.sum() + pr.sum()
                        dice_scores.append(1.0 if s == 0 else 2.0 * inter / s)
                except (ValueError, IndexError):
                    pass
        if n % 50 == 0:
            print(f"  ...{n} videos")

    if n == 0:
        print("No videos evaluated. Check the dataset path / Videos folder.")
        return 1

    t = np.array(ef_true); p = np.array(ef_pred)
    mae = float(np.mean(np.abs(p - t)))
    rmse = float(np.sqrt(np.mean((p - t) ** 2)))
    ss_res = float(np.sum((t - p) ** 2)); ss_tot = float(np.sum((t - t.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot else float("nan")
    corr = float(np.corrcoef(t, p)[0, 1]) if len(t) > 1 else float("nan")

    print(f"\nEchoNet evaluation — {n} videos ({args.split} split)\n")
    print("Ejection Fraction (regression)")
    print(f"  MAE   : {mae:.2f} %")
    print(f"  RMSE  : {rmse:.2f} %")
    print(f"  R^2   : {r2:.3f}")
    print(f"  Pearson r : {corr:.3f}")
    if dice_scores:
        print("\nLV Segmentation (traced ED/ES frames)")
        print(f"  Dice  : {np.mean(dice_scores):.3f}  (n={len(dice_scores)} traced frames)")
    elif not vt.exists():
        print("\n(LV segmentation Dice skipped — VolumeTracings.csv not found)")
    else:
        print("\n(LV segmentation Dice skipped — no traced frames matched the evaluated videos)")
    if n < 50:
        print("\nNOTE: small sample — for report-grade numbers run the full TEST split (no --limit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
