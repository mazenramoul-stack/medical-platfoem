"""Evaluation harness for the MRI brain-tumor classifier (Swin Transformer).

Computes a confusion matrix, per-class precision/recall/F1, overall accuracy,
and mean confidence for the 4-class classifier — measured *as deployed* (the
Swin classifier run on the full image, which is what the pipeline does because
the U-Net segmentation always saturates and is suppressed).

Ground truth is resolved per image, in priority order:
    1. Parent directory name, if it is one of the 4 class names
       (works on the standard Kaggle layout: Testing/<class>/*.jpg).
    2. The `Te-/Tr-[aug-]<gl|me|pi|no>_...` filename convention
       (works on the loose samples in samples/mri/).
    3. Otherwise the image is skipped and reported as "unlabeled".

Usage (from project root, backend venv active or referenced):
    python tools/eval_mri_classifier.py                      # defaults to samples/mri
    python tools/eval_mri_classifier.py path/to/Testing      # full Kaggle test set
    python tools/eval_mri_classifier.py path/to/dir --limit 200

This script does NOT need the database. First run loads the Swin classifier
(~110 MB, cached thereafter).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path

warnings.filterwarnings("ignore")

# --- make `apps.inference` importable (backend/ on sys.path) ---------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

CLASSES = ["glioma", "meningioma", "notumor", "pituitary"]
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

# filename-convention abbreviations -> canonical class
_ABBREV = {"gl": "glioma", "me": "meningioma", "pi": "pituitary", "no": "notumor"}
_FNAME_RE = re.compile(r"(?:^|[-_])(?:aug-)?(gl|me|pi|no)(?:[-_]|\d)", re.IGNORECASE)


def normalize_label(raw: str | None) -> str | None:
    """Map any label spelling ('meningioma_tumor', 'no_tumor', 'Glioma') -> canonical."""
    if not raw:
        return None
    t = raw.lower().strip().replace(" ", "_")
    if t in ("no_tumor", "notumor"):
        return "notumor"
    if t.endswith("_tumor"):
        t = t[: -len("_tumor")]
    return t if t in CLASSES else None


def truth_from_path(path: Path) -> str | None:
    """Resolve ground-truth class from parent dir, else filename convention."""
    parent = normalize_label(path.parent.name)
    if parent:
        return parent
    m = _FNAME_RE.search(path.stem)
    if m:
        return _ABBREV[m.group(1).lower()]
    return None


def iter_images(root: Path):
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*")):
        if p.suffix.lower() in IMAGE_EXTS:
            yield p


def classify(image_path: str, loader, np, torch, Image):
    """Replicate the deployed classifier path: Swin on the full image."""
    from apps.inference.utils import load_image_universal

    processor, vit = loader.get_mri_classifier()
    device = loader.get_device()

    image_rgb = load_image_universal(image_path)
    inputs = processor(images=Image.fromarray(image_rgb), return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    with torch.no_grad():
        logits = vit(**inputs).logits
        probs = torch.softmax(logits, dim=-1)
        idx = int(probs.argmax().item())
        conf = float(probs.max().item())

    id2label = getattr(getattr(vit, "config", None), "id2label", None) or {}
    raw = id2label.get(idx) or (CLASSES[idx] if 0 <= idx < len(CLASSES) else f"class_{idx}")
    return normalize_label(raw) or "notumor", conf


def print_confusion(matrix: dict, labels: list[str]) -> None:
    width = max(11, *(len(l) for l in labels)) + 1
    header = " " * width + "".join(f"{l[:9]:>11}" for l in labels) + f"{'  total':>9}"
    print("\nConfusion matrix  (rows = truth, cols = predicted)")
    print(header)
    for t in labels:
        row = matrix[t]
        cells = "".join(f"{row.get(p, 0):>11}" for p in labels)
        print(f"{t:<{width}}{cells}{sum(row.values()):>9}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate the MRI tumor classifier.")
    ap.add_argument("data_dir", nargs="?", default=str(PROJECT_ROOT / "samples" / "mri"),
                    help="image file or directory (default: samples/mri)")
    ap.add_argument("--limit", type=int, default=0, help="max images to evaluate (0 = all)")
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
    print(f"Evaluating: {root}")
    print(f"Device: {loader.get_device()}  (first run loads the Swin classifier, ~110 MB)\n")

    matrix: dict = {t: defaultdict(int) for t in CLASSES}
    correct = total = unlabeled = 0
    conf_sum = 0.0
    mistakes: list[tuple[str, str, str, float]] = []

    for path in iter_images(root):
        truth = truth_from_path(path)
        if truth is None:
            unlabeled += 1
            continue
        try:
            pred, conf = classify(str(path), loader, np, torch, Image)
        except Exception as e:  # keep going; report at the end
            print(f"  ! failed on {path.name}: {type(e).__name__}: {e}")
            continue
        matrix[truth][pred] += 1
        total += 1
        conf_sum += conf
        if pred == truth:
            correct += 1
        else:
            mistakes.append((path.name, truth, pred, conf))
        print(f"  {path.name:<28} truth={truth:<11} pred={pred:<11} conf={conf:5.1%} "
              f"{'OK' if pred == truth else 'X'}")
        if args.limit and total >= args.limit:
            break

    if total == 0:
        print("\nNo labeled images found. Check the directory layout or filenames.")
        print(f"(skipped {unlabeled} unlabeled file(s))")
        return 1

    # include any class that appears as a truth OR a prediction, so a row's
    # mispredicted column is never hidden.
    seen = set()
    for t in CLASSES:
        if sum(matrix[t].values()) > 0:
            seen.add(t)
        seen.update(matrix[t].keys())
    present = [c for c in CLASSES if c in seen]
    print_confusion(matrix, present)

    print("\nPer-class metrics")
    print(f"{'class':<13}{'precision':>11}{'recall':>9}{'f1':>8}{'support':>9}")
    macro_f1 = 0.0
    for c in present:
        tp = matrix[c].get(c, 0)
        fn = sum(matrix[c].values()) - tp
        fp = sum(matrix[t].get(c, 0) for t in present) - tp
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        macro_f1 += f1
        print(f"{c:<13}{prec:>11.3f}{rec:>9.3f}{f1:>8.3f}{tp + fn:>9}")
    macro_f1 /= len(present)

    print("\nSummary")
    print(f"  images evaluated : {total}  ({unlabeled} unlabeled skipped)")
    print(f"  overall accuracy : {correct}/{total} = {correct / total:.1%}")
    print(f"  macro F1         : {macro_f1:.3f}")
    print(f"  mean confidence  : {conf_sum / total:.1%}")

    if mistakes:
        print(f"\nMisclassifications ({len(mistakes)}):")
        for name, t, p, c in mistakes:
            print(f"  {name:<28} truth={t:<11} -> pred={p:<11} (conf {c:.1%})")

    if total < 40:
        print("\nNOTE: small sample — treat these numbers as indicative only. For a")
        print("report-grade result, point this at the full Kaggle 'Testing' folder:")
        print("  python tools/eval_mri_classifier.py path/to/Testing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
