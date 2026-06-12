"""End-to-end MRI brain analysis pipeline.

Two-stage:
    1. U-Net (segmentation)     -> tumor mask + area + segmentation confidence
    2. ViT  (4-class classifier) -> tumor type + classification confidence

No training code: both models are pre-trained and loaded via ModelLoader.
"""

from __future__ import annotations

import datetime
import logging
import os
import time

import matplotlib
matplotlib.use('Agg')  # headless backend; safe for server/CI
import matplotlib.pyplot as plt
import numpy as np
import torch
from PIL import Image

from .model_loader import ModelLoader
from .utils import load_image_universal, save_visualization

logger = logging.getLogger(__name__)

# media/mri/results/ relative to backend/
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..', '..'))
MRI_RESULTS_DIR = os.path.join(_BACKEND_DIR, 'media', 'mri', 'results')


# ---- helpers --------------------------------------------------------------

def extract_bounding_box_crop(image_rgb: np.ndarray, binary_mask) -> np.ndarray:
    """Crop image_rgb to the bounding box of the tumor mask, with 10-px padding.

    Args:
        image_rgb:   (H, W, 3) uint8 array, the original (unresized) image.
        binary_mask: torch tensor (1, 1, h, w) or ndarray with values in {0, 1}.
                     The mask is at the U-Net resolution; we rescale to image_rgb.
    Returns:
        Cropped (H', W', 3) array. If the mask is empty, the original image is
        returned unchanged.
    """
    if isinstance(binary_mask, torch.Tensor):
        mask = binary_mask.squeeze().detach().cpu().numpy()
    else:
        mask = np.asarray(binary_mask).squeeze()

    H, W = image_rgb.shape[:2]
    mask_img = Image.fromarray((mask * 255).astype(np.uint8)).resize((W, H), Image.NEAREST)
    mask_arr = np.array(mask_img) > 127

    ys, xs = np.where(mask_arr)
    if len(ys) == 0:
        return image_rgb
    y1, y2 = max(0, ys.min() - 10), min(H, ys.max() + 10)
    x1, x2 = max(0, xs.min() - 10), min(W, xs.max() + 10)
    return image_rgb[y1:y2, x1:x2]


def _normalize_tumor_label(tumor_type: str) -> str:
    """Strip the '_tumor' suffix that HuggingFace classifiers use in their labels.

    Maps 'meningioma_tumor' → 'meningioma', 'glioma_tumor' → 'glioma',
    'pituitary_tumor' → 'pituitary'. Preserves 'no_tumor' / 'notumor' as-is.
    """
    if not tumor_type:
        return ''
    t = tumor_type.lower().strip()
    if t in ('no_tumor', 'notumor'):
        return t
    return t[:-len('_tumor')] if t.endswith('_tumor') else t


def generate_clinical_note(tumor_type: str, detected: bool, cls_conf: float | None = None) -> str:
    """Build a clinical recommendation that fuses U-Net + ViT verdicts.

    Logic table:
      | U-Net | ViT (with conf ≥ 0.70) | output                                |
      | YES   | tumor type             | confirmed (both agree)                |
      | YES   | no_tumor               | ambiguous — radiologist review         |
      | NO    | tumor type             | classifier-only finding (likely tumor) |
      | NO    | no_tumor / low-conf    | no tumor                              |

    Args:
        tumor_type: Predicted class from the ViT (e.g. 'meningioma_tumor').
        detected:   True if U-Net flagged a tumor after the saturation guard.
        cls_conf:   ViT classification confidence in [0, 1]; None if unknown.
    """
    normalized = _normalize_tumor_label(tumor_type)
    is_no_tumor = normalized in ('no_tumor', 'notumor', '')
    confident_tumor_class = (
        cls_conf is not None and cls_conf >= 0.70 and not is_no_tumor
    )

    by_type = {
        'glioma':     'glioma — recommend neurosurgical consultation and follow-up contrast MRI',
        'meningioma': 'meningioma — typically slow-growing; consider neurosurgical evaluation and serial imaging',
        'pituitary':  'pituitary adenoma — recommend endocrinology workup and dedicated sellar MRI',
    }
    type_phrase = by_type.get(normalized, f'{normalized or tumor_type} — specialist review')
    conf_str = f'{cls_conf * 100:.1f}%' if cls_conf is not None else 'n/a'

    if detected and not is_no_tumor:
        return (f'Tumor confirmed by both segmentation and classifier (classifier confidence {conf_str}). '
                f'Diagnosis: {type_phrase}.')

    if detected and is_no_tumor:
        return ('Ambiguous: segmentation flagged tissue but the classifier rejected it. '
                'Recommend manual radiologist review before any further workup.')

    if not detected and confident_tumor_class:
        return (f'Likely {type_phrase} (classifier confidence {conf_str}). '
                'Segmentation was inconclusive on this image — recommend manual radiologist '
                'review of the localization.')

    return 'No tumor detected. Recommend routine follow-up only if clinically indicated.'


def compute_model_agreement(tumor_detected: bool, tumor_type: str,
                            cls_conf: float | None = None) -> tuple[bool, str]:
    """Compare the U-Net and ViT verdicts and flag cross-model disagreement.

    The two models are trained on different datasets (TCGA-LGG vs. the Kaggle
    brain-tumor set) and can disagree. The verdict is 'uncertain' when:
      * segmentation detects a tumor but the classifier predicts no_tumor, or
      * segmentation finds nothing but the classifier confidently
        (confidence >= 0.70) predicts a tumor class.
    A low-confidence tumor class with no segmentation finding is treated as
    classifier noise, matching `generate_clinical_note`'s decision table.

    Args:
        tumor_detected: True if U-Net flagged a tumor (after the saturation guard).
        tumor_type: Predicted class from the ViT (e.g. 'glioma', 'no_tumor').
        cls_conf: ViT classification confidence in [0, 1]; None if unknown.

    Returns:
        Tuple (models_agree, overall_verdict) where overall_verdict is
        'consistent' or 'uncertain'.
    """
    normalized = _normalize_tumor_label(tumor_type)
    is_no_tumor = normalized in ('no_tumor', 'notumor', '')
    confident_tumor_class = (
        cls_conf is not None and cls_conf >= 0.70 and not is_no_tumor
    )

    disagree = (
        (tumor_detected and is_no_tumor)
        or (not tumor_detected and confident_tumor_class)
    )
    return (not disagree, 'uncertain' if disagree else 'consistent')


# ---- main pipeline --------------------------------------------------------

VALID_MRI_MODES = ('full', 'classify', 'segment')


def analyze_mri(file_path: str, mode: str = 'full') -> dict:
    """Run the MRI brain analysis pipeline with one or both models.

    The platform ships two independent MRI models — a U-Net tumour
    *segmentation* network and a Swin/ViT 4-class *classifier*. Which one runs
    is chosen by the frontend from the uploaded image type:

        mode='classify'  — Swin 4-class classifier ONLY. Intended for a plain
                           black/white (grayscale) raw scan: name the tumour
                           type (glioma / meningioma / notumor / pituitary).
                           Runs on the full image (no segmentation, no crop);
                           produces no mask/overlay.
        mode='segment'   — U-Net segmentation ONLY. Intended for a colored /
                           pre-masked image: locate and outline the tumour
                           tissue; produces a mask + overlay, no tumour type.
        mode='full'      — both models (default; backward-compatible). U-Net
                           first, then crop-then-classify, plus the cross-model
                           verdict.

    Args:
        file_path: absolute path to an MRI image (PNG, JPG, DICOM, NIfTI, etc.).
        mode: one of 'full', 'classify', 'segment' (case-insensitive; anything
            else falls back to 'full').
    Returns:
        A result dict with status, the requested model's outputs, file paths to
        saved visualisations, and a human-readable report. Fields not produced
        by the selected mode are present but set to None.
        On error, returns {'status': 'failed', 'error': ..., 'error_type': ...}.
    """
    t_start = time.time()
    try:
        mode = (mode or 'full').strip().lower()
        if mode not in VALID_MRI_MODES:
            logger.warning("analyze_mri: unknown mode %r, falling back to 'full'", mode)
            mode = 'full'
        run_seg = mode in ('full', 'segment')
        run_cls = mode in ('full', 'classify')

        loader = ModelLoader()
        device = loader.get_device()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(MRI_RESULTS_DIR, exist_ok=True)

        # 1. Load -------------------------------------------------------------
        logger.info("analyze_mri: loading %s (mode=%s)", file_path, mode)
        image_rgb = load_image_universal(file_path)

        # Mode-agnostic defaults so the result envelope always has every key.
        tumor_detected = False
        tumor_area_pixels = 0
        seg_conf = 0.0
        binary_mask = None
        mask_resized = None
        tumor_type = None
        cls_conf = 0.0
        screening_flag = None
        models_agree = None
        overall_verdict = None
        mask_path = None
        overlay_path = None

        # 2-3. Segmentation (U-Net) ------------------------------------------
        if run_seg:
            # Preprocess for U-Net (256x256, RGB, per-channel z-score).
            # The mateuszbuda/brain-segmentation-pytorch U-Net was trained on
            # 3-channel slices where each channel is a different MRI sequence
            # (pre-contrast T1, FLAIR, post-contrast T1c). Normalization is
            # per-channel z-score, not global — each sequence has its own
            # intensity distribution. See `normalize_sample` upstream.
            img_resized = Image.fromarray(image_rgb).resize((256, 256))
            img_arr = np.array(img_resized, dtype=np.float32)
            channel_mean = img_arr.mean(axis=(0, 1), keepdims=True)
            channel_std  = img_arr.std(axis=(0, 1), keepdims=True) + 1e-8
            img_norm = (img_arr - channel_mean) / channel_std
            tensor = torch.from_numpy(img_norm).permute(2, 0, 1).unsqueeze(0).to(device)

            logger.info("analyze_mri: running U-Net segmentation")
            unet = loader.get_mri_segmentation_model()
            with torch.no_grad():
                # This U-Net applies sigmoid INSIDE its forward(), so its output
                # is already a probability map in [0, 1]. Do NOT apply sigmoid
                # again: a second sigmoid squashes [0,1] into [0.5, 0.73],
                # pushing every pixel past the 0.5 threshold and saturating the
                # mask — the long-standing "marks ~100% of the image" bug.
                # Verified on LGG: using the output directly yields Dice ~0.85.
                prob_map = unet(tensor)
                binary_mask = (prob_map > 0.5).float()

            tumor_area_pixels = int(binary_mask.sum().item())
            total_pixels = int(binary_mask.numel())
            saturation = tumor_area_pixels / total_pixels if total_pixels else 0.0

            # Saturation guard: a mask covering >75% of the image is degenerate
            # (model failure / far out-of-distribution) — treat as no detection.
            if saturation > 0.75:
                logger.warning(
                    "MRI mask is saturated (%.0f%% of image, %d px) — treating as no detection",
                    saturation * 100, tumor_area_pixels,
                )
                tumor_detected = False
                seg_conf = 0.0
            elif tumor_area_pixels > 50:  # small-blob noise threshold
                tumor_detected = True
                seg_conf = float(prob_map[binary_mask > 0].mean().item())
            else:
                tumor_detected = False
                seg_conf = float(prob_map.max().item())

            mask_np = binary_mask.squeeze().detach().cpu().numpy()
            mask_resized = np.array(
                Image.fromarray((mask_np * 255).astype(np.uint8))
                     .resize((image_rgb.shape[1], image_rgb.shape[0]), Image.NEAREST)
            )

        # 4. Classification (Swin/ViT) ---------------------------------------
        if run_cls:
            logger.info("analyze_mri: running classifier")
            processor, vit = loader.get_mri_classifier()
            # Crop to the tumour bounding box only when segmentation actually
            # ran and found tissue; otherwise classify the full image.
            crop_arr = (
                extract_bounding_box_crop(image_rgb, binary_mask)
                if (run_seg and tumor_detected and binary_mask is not None)
                else image_rgb
            )
            crop_pil = Image.fromarray(crop_arr)
            inputs = processor(images=crop_pil, return_tensors='pt')
            inputs = {k: v.to(device) for k, v in inputs.items()}
            with torch.no_grad():
                cls_out = vit(**inputs)
                probs = torch.softmax(cls_out.logits, dim=-1)
                pred_idx = int(probs.argmax().item())
                cls_conf = float(probs.max().item())

            fallback_labels = ['glioma', 'meningioma', 'notumor', 'pituitary']
            id2label = getattr(getattr(vit, 'config', None), 'id2label', None) or {}
            tumor_type = id2label.get(pred_idx) or (
                fallback_labels[pred_idx] if 0 <= pred_idx < len(fallback_labels) else f'class_{pred_idx}'
            )

            # Safety gate (screening posture): NEVER silently clear a tumour.
            # Accept a 'notumor' verdict only when the classifier is highly
            # confident AND (when available) the U-Net found no tissue; else
            # route 'possible tumour — review'. On the Kaggle Testing split the
            # classifier-confidence gate alone lifts tumour-detection recall
            # 0.983 -> 0.998 (tools/eval_mri_recall.py). Raise to 1.0 for zero
            # misses at ~4 %/scan over-flag.
            NOTUMOR_MIN_CONFIDENCE = 0.99
            _norm_type = (tumor_type or '').lower().replace('_tumor', '')
            predicted_notumor = _norm_type in ('notumor', 'no')
            if run_seg:
                screening_flag = (
                    'possible_tumor_review'
                    if predicted_notumor and (tumor_detected or cls_conf < NOTUMOR_MIN_CONFIDENCE)
                    else None
                )
            else:
                # classify-only: no U-Net signal, so the gate is confidence-only.
                screening_flag = (
                    'possible_tumor_review'
                    if predicted_notumor and cls_conf < NOTUMOR_MIN_CONFIDENCE
                    else None
                )
                # Derive a detection flag from the classifier alone.
                tumor_detected = not predicted_notumor

        # Cross-model verdict only when BOTH models ran.
        if run_seg and run_cls:
            models_agree, overall_verdict = compute_model_agreement(
                tumor_detected, tumor_type, cls_conf,
            )

        # 5. Visualisations ---------------------------------------------------
        logger.info("analyze_mri: generating visualisations (mode=%s)", mode)
        red = None
        if run_seg and mask_resized is not None:
            red = np.zeros((*mask_resized.shape, 4))
            red[..., 0] = 1.0
            red[..., 3] = (mask_resized > 127) * 0.4

            # Mask alone
            fig_m, ax_m = plt.subplots(figsize=(5, 5))
            ax_m.imshow(mask_resized, cmap='gray'); ax_m.axis('off')
            mask_path = save_visualization(fig_m, MRI_RESULTS_DIR, f"{timestamp}_mask.png")
            plt.close(fig_m)

            # Overlay alone
            fig_o, ax_o = plt.subplots(figsize=(5, 5))
            ax_o.imshow(image_rgb); ax_o.imshow(red); ax_o.axis('off')
            overlay_path = save_visualization(fig_o, MRI_RESULTS_DIR, f"{timestamp}_overlay.png")
            plt.close(fig_o)

        # Mode-aware combined analysis figure
        if mode == 'classify':
            fig, ax = plt.subplots(figsize=(6, 6))
            ax.imshow(image_rgb); ax.axis('off')
            fig.suptitle(f'MRI Classification — {tumor_type} ({cls_conf:.1%})')
        elif mode == 'segment':
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            axes[0].imshow(image_rgb);                 axes[0].set_title('Original');          axes[0].axis('off')
            axes[1].imshow(mask_resized, cmap='gray'); axes[1].set_title('Segmentation Mask'); axes[1].axis('off')
            axes[2].imshow(image_rgb); axes[2].imshow(red); axes[2].set_title('Overlay');      axes[2].axis('off')
            fig.suptitle(
                f"MRI Segmentation — tumour {'detected' if tumor_detected else 'not detected'} "
                f"({tumor_area_pixels} px)"
            )
        else:  # full
            fig, axes = plt.subplots(1, 3, figsize=(15, 5))
            axes[0].imshow(image_rgb);                 axes[0].set_title('Original');          axes[0].axis('off')
            axes[1].imshow(mask_resized, cmap='gray'); axes[1].set_title('Segmentation Mask'); axes[1].axis('off')
            axes[2].imshow(image_rgb); axes[2].imshow(red); axes[2].set_title('Overlay');      axes[2].axis('off')
            fig.suptitle(f'MRI Analysis — {tumor_type} ({cls_conf:.1%})')
        analysis_path = save_visualization(fig, MRI_RESULTS_DIR, f"{timestamp}_analysis.png")
        plt.close(fig)

        # 6. Report (mode-aware) ---------------------------------------------
        seg_block = (
            "SEGMENTATION RESULTS (U-Net, TCGA-LGG pretrained):\n"
            f"  Tumor Detected: {'YES' if tumor_detected else 'NO'}\n"
            f"  Tumor Area: {tumor_area_pixels} pixels\n"
            f"  Segmentation Confidence: {seg_conf:.2%}\n"
        ) if run_seg else ""
        cls_block = (
            "CLASSIFICATION RESULTS (Swin/ViT, 4-class):\n"
            f"  Predicted Type: {tumor_type}\n"
            f"  Classification Confidence: {cls_conf:.2%}\n"
        ) if run_cls else ""
        verdict_block = (
            "CROSS-MODEL VERDICT:\n"
            f"  Models Agree: {'YES' if models_agree else 'NO'}\n"
            f"  Overall Verdict: {overall_verdict}\n"
        ) if (run_seg and run_cls) else ""
        flag_block = (
            "  SAFETY FLAG: possible tumour — recommend radiologist review (the\n"
            "    classifier returned no-tumour without high confidence"
            f"{', or the U-Net found tissue' if run_seg else ''}).\n"
        ) if screening_flag else ""
        interp_block = (
            "CLINICAL INTERPRETATION:\n"
            f"  {generate_clinical_note(tumor_type, tumor_detected, cls_conf)}\n"
        ) if run_cls else ""
        models_used = []
        if run_seg:
            models_used.append('U-Net (mateuszbuda/brain-segmentation-pytorch)')
        if run_cls:
            models_used.append('Swin/ViT (Devarshi/Brain_Tumor_Classification)')
        models_block = "MODELS USED:\n" + "".join(f"  - {m}\n" for m in models_used)

        mode_label = {'classify': 'CLASSIFICATION ONLY (grayscale scan)',
                      'segment': 'SEGMENTATION ONLY (colored / masked image)',
                      'full': 'SEGMENTATION + CLASSIFICATION'}[mode]
        bar = "════════════════════════════════════════════════════"
        # Join only the non-empty blocks for the selected mode (no backslashes
        # inside f-string expressions — unsupported on Python 3.10/3.11).
        body = "\n".join(
            b.rstrip("\n") for b in (
                seg_block, cls_block, verdict_block, flag_block, interp_block, models_block,
            ) if b
        )
        report = (
            f"{bar}\n"
            "BRAIN MRI ANALYSIS REPORT\n"
            f"Generated: {timestamp}\n"
            f"Mode: {mode_label}\n"
            f"{bar}\n\n"
            f"{body}\n\n"
            "DISCLAIMER: AI-assisted diagnosis. Clinical decisions\n"
            "must be made by a qualified physician.\n"
            f"{bar}"
        ).strip()

        elapsed = time.time() - t_start
        logger.info("analyze_mri: complete in %.2fs (mode=%s)", elapsed, mode)

        return {
            'status': 'success',
            'mode': mode,
            'tumor_detected': tumor_detected,
            'tumor_type': tumor_type,
            'tumor_type_confidence': cls_conf if run_cls else None,
            'tumor_area_pixels': tumor_area_pixels if run_seg else None,
            'segmentation_confidence': seg_conf if run_seg else None,
            'models_agree': models_agree,
            'overall_verdict': overall_verdict,
            'screening_flag': screening_flag,
            'segmentation_note': (
                'U-Net was trained on 3 distinct MRI sequences (T1/FLAIR/T1c); this '
                'single uploaded image is broadcast to 3 identical channels, so '
                'segmentation is most reliable on FLAIR-like inputs.') if run_seg else None,
            'original_image_path': file_path,
            'analysis_path': analysis_path,
            'mask_path': mask_path,
            'overlay_path': overlay_path,
            'report': report,
            'models_used': models_used,
            'timestamp': timestamp,
            'elapsed_seconds': elapsed,
        }

    except Exception as e:
        logger.exception("analyze_mri failed")
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__,
        }
