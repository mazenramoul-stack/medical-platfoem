"""Faithfulness harness for the MRI Grad-CAM + SHAP explanations.

Reports, over a set of MRI images:
  1. Grad-CAM <-> SHAP AGREEMENT (Spearman rank-corr + top-k IoU) — method robustness.
     Always computed; needs no masks (runs on data/brain-tumor-mri).
  2. LOCALIZATION (--localize): does the Grad-CAM peak land inside the tumour mask?
     Mask source = the U-Net PREDICTED mask by default (works on present data), OR the
     LGG GROUND-TRUTH masks if --lgg-root <dir> is given. Restricted to tumour-positive
     slices. NOTE: data/brain-tumor-mri has NO masks; GT-mask localization needs the
     mateuszbuda/lgg-mri-segmentation dataset (the folder containing kaggle_3m/).
  3. DELETION sanity check (--deletion): zeroing the top-attributed region should drop
     the predicted-class confidence (attribution is causal, not decorative).

Caches per-image records to tools/mri_explainer.json (reload with --from-cache).
Deterministic full-set pass (no --seed), mirroring the other tools/eval_mri_*.py harnesses.

Usage (from project root):
    python tools/eval_mri_explainer.py data/brain-tumor-mri/Testing --limit 50
    python tools/eval_mri_explainer.py data/brain-tumor-mri/Testing --limit 50 --localize --deletion
    python tools/eval_mri_explainer.py data/brain-tumor-mri/Testing --localize --lgg-root <lgg_root>
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
for _p in (str(BACKEND_DIR), str(PROJECT_ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

CACHE = PROJECT_ROOT / "tools" / "mri_explainer.json"


def _seg_predict_mask(unet, image_rgb, device):
    """Run the U-Net; return a boolean predicted-tumour mask (256x256).

    Mirrors tools/eval_mri_segmentation.py preprocessing: RGB 256x256, per-channel
    z-score, and the U-Net output is ALREADY a sigmoid probability (no extra sigmoid).
    """
    import torch
    from PIL import Image
    im = Image.fromarray(image_rgb).convert("RGB").resize((256, 256))
    x = np.asarray(im, dtype=np.float32)
    for c in range(3):
        ch = x[..., c]
        x[..., c] = (ch - ch.mean()) / (ch.std() + 1e-8)
    t = torch.from_numpy(x).permute(2, 0, 1).unsqueeze(0).to(device)
    with torch.no_grad():
        prob = unet(t)[0, 0].cpu().numpy()
    return prob > 0.5


def _deletion_drop(processor, vit, pil, cam, idx, conf):
    """Zero the top-10% Grad-CAM region in the input; return the confidence drop."""
    import torch
    from apps.inference.explainers.base import resize_to
    px = processor(images=pil, return_tensors="pt")["pixel_values"]
    h, w = px.shape[-2:]
    cam_up = resize_to(cam, (h, w))
    keep = torch.from_numpy((cam_up >= float(np.quantile(cam_up, 0.90))))
    px2 = px.clone()
    px2[0, :, keep] = 0.0
    with torch.no_grad():
        p2 = torch.softmax(vit(pixel_values=px2).logits, dim=-1)[0, idx].item()
    return float(conf - p2)


def _summarize(recs, localize=False, deletion=False):
    sp = np.array([r["spearman"] for r in recs if "spearman" in r], dtype=float)
    iou = np.array([r["topk_iou"] for r in recs if "topk_iou" in r], dtype=float)
    print("\n=== MRI explainer faithfulness ===")
    print(f"images: {len(recs)}")
    if sp.size:
        print(f"Grad-CAM<->SHAP agreement: spearman mean={sp.mean():.3f}  top-k IoU mean={iou.mean():.3f}")
    if localize:
        pim = [r["peak_in_mask"] for r in recs if "peak_in_mask" in r]
        if pim:
            print(f"localization (peak-in-mask, tumour slices n={len(pim)}): {np.mean(pim):.3f}")
        else:
            print("localization: no tumour-positive slices found")
    if deletion:
        cd = np.array([r["conf_drop"] for r in recs if "conf_drop" in r], dtype=float)
        if cd.size:
            print(f"deletion confidence-drop: mean={cd.mean():.3f}  (higher = more causal)")


def main() -> int:
    from PIL import Image

    from apps.inference.model_loader import ModelLoader
    from apps.inference.utils import load_image_universal
    from apps.inference.explainers.gradcam import swin_gradcam
    from apps.inference.explainers.shap_attr import swin_gradient_shap
    from apps.inference.explainers.base import attribution_agreement, resize_to
    from eval_mri_classifier import iter_images, normalize_label, truth_from_path  # noqa: E402

    ap = argparse.ArgumentParser(description="Faithfulness harness for MRI Grad-CAM + SHAP.")
    ap.add_argument("data_dir", nargs="?",
                    default=str(PROJECT_ROOT / "data" / "brain-tumor-mri" / "Testing"),
                    help="dir of classifier MRI images (default: data/brain-tumor-mri/Testing)")
    ap.add_argument("--limit", type=int, default=50, help="max images (0 = all)")
    ap.add_argument("--localize", action="store_true",
                    help="measure Grad-CAM-peak-in-mask (U-Net predicted mask, or LGG GT if --lgg-root)")
    ap.add_argument("--lgg-root", default=None,
                    help="LGG dataset root (folder containing kaggle_3m/) for GROUND-TRUTH-mask localization")
    ap.add_argument("--deletion", action="store_true",
                    help="measure the deletion confidence-drop sanity check")
    ap.add_argument("--from-cache", default=None,
                    help="recompute the summary from a cached json (no model needed)")
    args = ap.parse_args()

    if args.from_cache:
        recs = json.loads(Path(args.from_cache).read_text())
        _summarize(recs, localize=any("peak_in_mask" in r for r in recs),
                   deletion=any("conf_drop" in r for r in recs))
        return 0

    loader = ModelLoader()
    device = loader.get_device()
    processor, vit = loader.get_mri_classifier()
    unet = loader.get_mri_segmentation_model() if (args.localize and not args.lgg_root) else None

    # Build the (image, mask-or-None) work list.
    if args.lgg_root:
        from eval_mri_segmentation import find_pairs  # noqa: E402
        pairs = list(find_pairs(Path(args.lgg_root)))
        if not pairs:
            print(f"ERROR: no (image, *_mask.tif) pairs under {args.lgg_root}. GT-mask localization "
                  f"needs the LGG dataset (kaggle_3m/); data/brain-tumor-mri has NO masks.", file=sys.stderr)
            return 2
        items = [(str(img), str(mask)) for img, mask in pairs]
    else:
        imgs = list(iter_images(Path(args.data_dir)))
        if not imgs:
            print(f"ERROR: no images under {args.data_dir}", file=sys.stderr)
            return 2
        items = [(str(p), None) for p in imgs]

    if args.limit:
        items = items[: args.limit]

    recs = []
    for i, (img_path, mask_path) in enumerate(items, 1):
        try:
            image_rgb = load_image_universal(img_path)
            pil = Image.fromarray(image_rgb)
            cam, idx, conf, _peak = swin_gradcam(processor, vit, pil)
            shap_map = swin_gradient_shap(processor, vit, pil, target_class=idx)
            agr = attribution_agreement(cam, shap_map)
            rec = {"name": Path(img_path).name, "pred_idx": int(idx),
                   "spearman": agr["spearman"], "topk_iou": agr["topk_iou"]}
            try:
                rec["pred"] = normalize_label(vit.config.id2label[idx])
            except Exception:
                pass
            truth = truth_from_path(Path(img_path))
            if truth:
                rec["truth"] = truth

            if args.localize:
                if mask_path:
                    gt = np.array(Image.open(mask_path).convert("L")) > 127
                else:
                    gt = _seg_predict_mask(unet, image_rgb, device)
                if gt.sum() > 0:  # tumour-positive slice only
                    cam_m = resize_to(cam, gt.shape)
                    py, px = np.unravel_index(int(cam_m.argmax()), cam_m.shape)
                    rec["peak_in_mask"] = bool(gt[py, px])
                    rec["mask_pixels"] = int(gt.sum())

            if args.deletion:
                rec["conf_drop"] = _deletion_drop(processor, vit, pil, cam, idx, conf)

            recs.append(rec)
        except Exception as e:  # noqa: BLE001 — keep going; report the skip
            print(f"  skip {Path(img_path).name}: {e}", file=sys.stderr)
        if i % 25 == 0:
            print(f"  ...{i}/{len(items)}")

    if not recs:
        print("ERROR: 0 images produced explanations (all skipped).", file=sys.stderr)
        return 1
    CACHE.write_text(json.dumps(recs, indent=2))
    print(f"Wrote {len(recs)} records -> {CACHE}")
    _summarize(recs, localize=args.localize, deletion=args.deletion)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
