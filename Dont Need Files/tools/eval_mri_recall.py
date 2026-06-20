"""Tumor-detection recall for the MRI classifier (clinical screening framing).

The catastrophic false negative in brain-MRI screening is calling a patient with
a tumor "notumor" (telling a sick patient they are healthy). 4-class accuracy is
the wrong lens for that: confusing glioma with meningioma is NOT a clinical miss
(both are tumors -> the patient is still referred). What matters is the
**tumor-vs-notumor recall**: of all images that truly contain a tumor, the
fraction NOT labelled `notumor`.

This script measures that, and the effect of a safety gate: only accept a
`notumor` prediction when the model is at least GATE confident; otherwise relabel
the case "indeterminate — possible tumor, review". Raising GATE trades a few
false alarms on healthy scans for fewer missed tumors. It is a decision rule on
the existing softmax output — no retraining, no GPU.

Caches per-image (truth, argmax-pred, notumor-prob) so gate sweeps are instant.

Usage:
    python tools/eval_mri_recall.py <Testing dir> [--limit N]
    python tools/eval_mri_recall.py --from-cache tools/mri_preds.json
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
from eval_mri_classifier import CLASSES, iter_images, normalize_label, truth_from_path  # noqa: E402

CACHE = PROJECT_ROOT / "tools" / "mri_preds.json"


def predict_all(root: Path, limit: int):
    import numpy as np  # noqa: F401
    import torch
    from PIL import Image

    from apps.inference.model_loader import ModelLoader
    from apps.inference.utils import load_image_universal

    loader = ModelLoader()
    processor, vit = loader.get_mri_classifier()
    device = loader.get_device()
    print(f"Device: {device}  (Swin classifier loaded)\n")
    id2label = getattr(getattr(vit, "config", None), "id2label", None) or {}

    recs = []
    n = 0
    for path in iter_images(root):
        truth = truth_from_path(path)
        if truth is None:
            continue
        try:
            image_rgb = load_image_universal(str(path))
            inputs = processor(images=Image.fromarray(image_rgb), return_tensors="pt")
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                probs = torch.softmax(vit(**inputs).logits, dim=-1)[0]
            argmax = int(probs.argmax().item())
            raw = id2label.get(argmax) or (CLASSES[argmax] if argmax < len(CLASSES) else "notumor")
            pred = normalize_label(raw) or "notumor"
            nt_idx = CLASSES.index("notumor")
            # notumor probability via label map (robust to permuted class order)
            nt_prob = None
            for i in range(probs.numel()):
                lbl = normalize_label(id2label.get(i, CLASSES[i] if i < len(CLASSES) else ""))
                if lbl == "notumor":
                    nt_prob = float(probs[i].item())
                    break
            if nt_prob is None:
                nt_prob = float(probs[nt_idx].item())
        except Exception as e:
            print(f"  ! {path.name}: {type(e).__name__}: {e}")
            continue
        recs.append({"truth": truth, "pred": pred, "notumor_prob": nt_prob})
        n += 1
        if n % 200 == 0:
            print(f"  ...{n} images")
        if limit and n >= limit:
            break
    return recs


def report(recs, gates):
    tumors = [r for r in recs if r["truth"] != "notumor"]
    healthy = [r for r in recs if r["truth"] == "notumor"]
    n_tum, n_heal = len(tumors), len(healthy)
    print(f"\nMRI tumor-detection recall — {len(recs)} images "
          f"({n_tum} with tumor, {n_heal} healthy)\n")

    # baseline: argmax
    missed = [r for r in tumors if r["pred"] == "notumor"]
    rec0 = (n_tum - len(missed)) / n_tum if n_tum else 1.0
    fp0 = sum(1 for r in healthy if r["pred"] != "notumor")
    print("Baseline (plain argmax):")
    print(f"  tumor-detection recall : {rec0:.4f}   ({len(missed)} tumors called 'notumor')")
    print(f"  healthy correctly clear: {n_heal - fp0}/{n_heal}\n")

    print("With notumor-confidence safety gate (accept 'notumor' only if conf >= gate,")
    print("else flag 'possible tumor — review'):")
    print(f"  {'gate':>6}{'tumor recall':>14}{'missed':>8}{'healthy flagged':>17}")
    for g in gates:
        still_missed = [r for r in tumors if r["pred"] == "notumor" and r["notumor_prob"] >= g]
        rec = (n_tum - len(still_missed)) / n_tum if n_tum else 1.0
        healthy_flagged = sum(1 for r in healthy if not (r["pred"] == "notumor" and r["notumor_prob"] >= g))
        print(f"  {g:>6.2f}{rec:>14.4f}{len(still_missed):>8}{healthy_flagged:>10}/{n_heal}")
    print("\n('healthy flagged' = false alarms on truly-healthy scans — the precision cost.)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("data_dir", nargs="?")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--from-cache", default=None)
    args = ap.parse_args()

    if args.from_cache:
        recs = json.loads(Path(args.from_cache).read_text())
        print(f"Loaded {len(recs)} cached predictions from {args.from_cache}")
    else:
        if not args.data_dir:
            print("ERROR: pass a Testing dir or --from-cache.", file=sys.stderr)
            return 2
        recs = predict_all(Path(args.data_dir), args.limit)
        if not recs:
            print("No labeled images found.", file=sys.stderr)
            return 1
        CACHE.write_text(json.dumps(recs))
        print(f"\nCached {len(recs)} predictions -> {CACHE}")

    report(recs, gates=[0.50, 0.90, 0.95, 0.99, 0.995, 0.999])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
