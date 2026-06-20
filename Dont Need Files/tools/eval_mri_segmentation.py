"""Evaluation harness for the MRI tumor segmentation U-Net.

Validates the segmentation model on the LGG MRI Segmentation dataset
(mateuszbuda/lgg-mri-segmentation) — the dataset the U-Net was trained on, which
ships ground-truth masks. Computes Dice and IoU, the standard segmentation
metrics.

Each slice is a 256x256x3 TIFF; its mask is `<name>_mask.tif` (0/255). Most
slices contain no tumor (empty mask), so we report Dice/IoU three ways:
  - over ALL slices,
  - over TUMOR-POSITIVE slices only (the meaningful clinical number),
  - empty-slice handling: both-empty counts as a perfect match (Dice 1).

Usage (from project root):
    python tools/eval_mri_segmentation.py "<LGG root>"          # full
    python tools/eval_mri_segmentation.py "<LGG root>" --limit 300
The root is the folder that contains kaggle_3m/ (or kaggle_3m itself).
No database needed; first run loads the U-Net (~30 MB, cached).
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def find_pairs(root: Path):
    """Yield (image_path, mask_path) for every slice that has a mask."""
    base = root / "kaggle_3m" if (root / "kaggle_3m").is_dir() else root
    for mask in sorted(base.rglob("*_mask.tif")):
        img = mask.with_name(mask.name.replace("_mask.tif", ".tif"))
        if img.exists():
            yield img, mask


def dice_iou(pred, gt, np):
    """Dice & IoU for two binary masks. Both-empty -> (1, 1)."""
    p = pred.astype(bool); g = gt.astype(bool)
    inter = (p & g).sum()
    psum = p.sum() + g.sum()
    union = (p | g).sum()
    if psum == 0:                      # both empty: perfect agreement
        return 1.0, 1.0
    dice = 2.0 * inter / psum
    iou = inter / union if union else 1.0
    return float(dice), float(iou)


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the MRI segmentation U-Net (Dice/IoU).")
    ap.add_argument("data_dir", help="LGG dataset root (folder containing kaggle_3m/)")
    ap.add_argument("--limit", type=int, default=0, help="max slices (0 = all)")
    ap.add_argument("--save-bad", default=None,
                    help="optional: write the N worst tumor-slice names to this file")
    args = ap.parse_args()

    root = Path(args.data_dir)
    if not root.exists():
        print(f"ERROR: path not found: {root}", file=sys.stderr)
        return 2

    import numpy as np
    import torch
    from PIL import Image

    from apps.inference.model_loader import ModelLoader

    loader = ModelLoader()
    device = loader.get_device()
    unet = loader.get_mri_segmentation_model()
    print(f"Device: {device}  (U-Net loaded)\n")

    all_dice, all_iou = [], []
    pos_dice, pos_iou = [], []          # tumor-positive slices only
    sat_count = 0                        # saturated predictions (>75% of image)
    total = 0
    worst = []                           # (dice, name) for tumor slices

    for img_path, mask_path in find_pairs(root):
        img = np.array(Image.open(img_path).convert("RGB"), dtype=np.float32)   # 256x256x3
        gt = np.array(Image.open(mask_path).convert("L")) > 127                 # 256x256 bool

        # preprocessing: per-channel z-score (as in mri_pipeline)
        mean = img.mean(axis=(0, 1), keepdims=True)
        std = img.std(axis=(0, 1), keepdims=True) + 1e-8
        x = (img - mean) / std
        t = torch.from_numpy(x).permute(2, 0, 1).unsqueeze(0).to(device)
        with torch.no_grad():
            # U-Net already applies sigmoid in forward() -> output is a [0,1]
            # probability map; do NOT sigmoid again (that saturates the mask).
            prob = unet(t)[0, 0].cpu().numpy()
        pred = prob > 0.5

        if pred.mean() > 0.75:
            sat_count += 1

        d, i = dice_iou(pred, gt, np)
        all_dice.append(d); all_iou.append(i)
        total += 1
        if gt.sum() > 0:                 # slice actually contains tumor
            pos_dice.append(d); pos_iou.append(i)
            worst.append((d, img_path.name))
        if args.limit and total >= args.limit:
            break

    if total == 0:
        print("No image/mask pairs found. Check the path (expects kaggle_3m/).")
        return 1

    mean = lambda xs: float(np.mean(xs)) if xs else float("nan")
    print(f"Slices evaluated : {total}  (tumor-positive: {len(pos_dice)}, "
          f"empty: {total - len(pos_dice)})")
    print(f"Saturated preds  : {sat_count}  ({100 * sat_count / total:.1f}%)  "
          f"<- high = model still broken on this data\n")
    print(f"{'metric':<22}{'all slices':>14}{'tumor slices':>16}")
    print(f"{'Dice':<22}{mean(all_dice):>14.3f}{mean(pos_dice):>16.3f}")
    print(f"{'IoU (Jaccard)':<22}{mean(all_iou):>14.3f}{mean(pos_iou):>16.3f}")
    print("\nInterpretation: Dice on tumor slices is the headline segmentation")
    print("metric (1.0 = perfect overlap). Saturated% near 0 means the model is")
    print("actually segmenting; near 100 means it is still marking the whole image.")

    if args.save_bad and worst:
        worst.sort()
        with open(args.save_bad, "w") as f:
            for d, name in worst[:50]:
                f.write(f"{d:.3f}  {name}\n")
        print(f"\nWorst tumor slices -> {args.save_bad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
