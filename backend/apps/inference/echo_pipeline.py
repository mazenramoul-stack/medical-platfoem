"""End-to-end echocardiography analysis pipeline (EchoNet-Dynamic).

Two pretrained models (Ouyang et al., Nature 2020 — github.com/echonet/dynamic):
    1. DeepLabV3 (ResNet-50)   -> per-frame left-ventricle segmentation
    2. R(2+1)D-18 (video)      -> ejection-fraction (EF) regression

No training code: both models are pretrained and loaded via ModelLoader.
Input is an echo *video* (.avi / .mp4); EF is averaged over sampled clips and
segmentation locates end-diastole (max LV area) / end-systole (min LV area).
"""

from __future__ import annotations

import datetime
import logging
import os
import time

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import torch

from .model_loader import ModelLoader
from .utils import save_visualization

logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..', '..'))
ECHO_RESULTS_DIR = os.path.join(_BACKEND_DIR, 'media', 'echo', 'results')

# EchoNet-Dynamic training normalisation (0-255 scale, grayscale → 3 channels).
ECHONET_MEAN = np.array([33.741, 33.877, 33.749], dtype=np.float32)
ECHONET_STD = np.array([51.131, 51.069, 51.099], dtype=np.float32)

FRAME_SIZE = 112
CLIP_LEN = 32        # frames per EF clip
CLIP_PERIOD = 2      # sampling stride within a clip
MAX_CLIPS = 4        # clips averaged for the EF estimate


def _ef_category(ef: float) -> str:
    """Map an EF percentage to a clinical category (simplified ASE bands)."""
    if ef < 40:
        return 'Reduced (HFrEF)'
    if ef < 50:
        return 'Mildly reduced'
    return 'Normal'


# Reduced-EF screen. Default flags at the clinical EF < 50 % cutoff (standard
# operating point). The EF regressor has ~4-5 % error (RMSE 5.3 % on EchoNet
# TEST); a safety-margin variant (flag EF < 55 %, +5 % margin) lifts reduced-EF
# detection recall 0.783 -> 0.952 at a precision cost — opt in by setting the
# REDUCED_EF_SCREEN_CUTOFF env var to 55. See tools/eval_echo_recall.py.
REDUCED_EF_SCREEN_CUTOFF = float(os.environ.get('REDUCED_EF_SCREEN_CUTOFF', 50.0))


def _reduced_ef_screen(ef: float) -> bool:
    """True if EF is at or below the safety-margin screening cutoff (review)."""
    return ef < REDUCED_EF_SCREEN_CUTOFF


def load_echo_video(file_path: str, size: int = FRAME_SIZE) -> np.ndarray:
    """Decode an echo video to an (F, size, size, 3) float32 array in [0,255].

    Uses OpenCV (matching EchoNet's own loader). Frames are converted to RGB and
    resized to size×size. Raises if the file cannot be opened or has no frames.
    """
    import cv2

    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        raise ValueError(f'Could not open video: {file_path}')
    frames = []
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if frame.shape[0] != size or frame.shape[1] != size:
                frame = cv2.resize(frame, (size, size), interpolation=cv2.INTER_AREA)
            frames.append(frame)
    finally:
        cap.release()

    if not frames:
        raise ValueError(f'No frames decoded from video: {file_path}')
    return np.asarray(frames, dtype=np.float32)


def _normalize(frames: np.ndarray) -> np.ndarray:
    """(F,H,W,3) 0-255 → normalised (F,3,H,W) per EchoNet stats."""
    x = (frames - ECHONET_MEAN) / ECHONET_STD
    return np.transpose(x, (0, 3, 1, 2))  # F,C,H,W


def _predict_ef(ef_model, norm_fchw: np.ndarray, device: str) -> float:
    """Average EF (%) over up to MAX_CLIPS clips of CLIP_LEN frames (stride CLIP_PERIOD)."""
    f = norm_fchw.shape[0]
    span = CLIP_LEN * CLIP_PERIOD
    # if the video is shorter than one clip span, loop it
    if f < span:
        reps = int(np.ceil(span / f))
        norm_fchw = np.tile(norm_fchw, (reps, 1, 1, 1))
        f = norm_fchw.shape[0]

    starts = np.linspace(0, f - span, num=min(MAX_CLIPS, max(1, f - span + 1)), dtype=int)
    preds = []
    for s in np.unique(starts):
        clip = norm_fchw[s:s + span:CLIP_PERIOD]            # (CLIP_LEN, 3, H, W)
        clip = np.transpose(clip, (1, 0, 2, 3))             # (3, T, H, W)
        t = torch.from_numpy(clip).unsqueeze(0).float().to(device)
        with torch.no_grad():
            preds.append(float(ef_model(t).item()))
    return float(np.mean(preds))


def _predict_segmentation(seg_model, norm_fchw: np.ndarray, device: str, batch: int = 16):
    """Run DeepLabV3 per frame → (masks (F,H,W) bool, areas (F,) int)."""
    f = norm_fchw.shape[0]
    masks = np.zeros((f, FRAME_SIZE, FRAME_SIZE), dtype=bool)
    for i in range(0, f, batch):
        chunk = torch.from_numpy(norm_fchw[i:i + batch]).float().to(device)
        with torch.no_grad():
            out = seg_model(chunk)['out']                   # (n,1,H,W) logits
            prob = torch.sigmoid(out)[:, 0]
            m = (prob > 0.5).cpu().numpy()
        masks[i:i + chunk.shape[0]] = m
    areas = masks.reshape(f, -1).sum(axis=1).astype(int)
    return masks, areas


def analyze_echo(file_path: str) -> dict:
    """Run the full echocardiography pipeline. Returns a result envelope dict."""
    t_start = time.time()
    try:
        loader = ModelLoader()
        device = loader.get_device()
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs(ECHO_RESULTS_DIR, exist_ok=True)

        logger.info('analyze_echo: loading %s', file_path)
        frames = load_echo_video(file_path)                 # (F,H,W,3)
        norm = _normalize(frames)                           # (F,3,H,W)

        seg_model, ef_model = loader.get_echo_models()

        logger.info('analyze_echo: predicting EF')
        ef = _predict_ef(ef_model, norm, device)
        ef = float(max(0.0, min(100.0, ef)))                # clamp to a sane range

        logger.info('analyze_echo: segmenting LV')
        masks, areas = _predict_segmentation(seg_model, norm, device)
        ed_idx = int(np.argmax(areas))                      # end-diastole = largest LV
        nonzero = np.where(areas > 0)[0]
        es_idx = int(nonzero[np.argmin(areas[nonzero])]) if len(nonzero) else int(np.argmin(areas))
        ed_area, es_area = int(areas[ed_idx]), int(areas[es_idx])

        # overlay on the end-diastole frame
        ed_frame = frames[ed_idx].astype(np.uint8)
        ed_mask = masks[ed_idx]
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        axes[0].imshow(ed_frame);                       axes[0].set_title('End-diastole'); axes[0].axis('off')
        axes[1].imshow(ed_mask, cmap='gray');           axes[1].set_title('LV segmentation'); axes[1].axis('off')
        axes[2].imshow(ed_frame)
        red = np.zeros((*ed_mask.shape, 4)); red[..., 0] = 1.0; red[..., 3] = ed_mask * 0.4
        axes[2].imshow(red);                            axes[2].set_title('Overlay'); axes[2].axis('off')
        fig.suptitle(f'Echo — EF {ef:.1f}% ({_ef_category(ef)})')
        overlay_path = save_visualization(fig, ECHO_RESULTS_DIR, f'{timestamp}_echo.png')
        plt.close(fig)

        category = _ef_category(ef)
        reduced_ef_screen = _reduced_ef_screen(ef)
        report = f"""
====================================================
ECHOCARDIOGRAPHY ANALYSIS REPORT
Generated: {timestamp}
====================================================

EJECTION FRACTION (R(2+1)D-18, EchoNet-Dynamic):
  Estimated EF: {ef:.1f}%
  Category: {category}
  Reduced-EF screen (EF < {REDUCED_EF_SCREEN_CUTOFF:.0f}%): {'FLAG — review' if reduced_ef_screen else 'clear'}

LEFT-VENTRICLE SEGMENTATION (DeepLabV3, EchoNet-Dynamic):
  End-diastolic LV area: {ed_area} px (frame {ed_idx})
  End-systolic  LV area: {es_area} px (frame {es_idx})
  Frames analysed: {len(frames)}

MODELS USED:
  - DeepLabV3-ResNet50  (EchoNet-Dynamic segmentation)
  - R(2+1)D-18          (EchoNet-Dynamic EF regression)

DISCLAIMER: AI-assisted analysis. Clinical decisions must be
made by a qualified physician.
====================================================
""".strip()

        elapsed = time.time() - t_start
        logger.info('analyze_echo: complete in %.2fs (EF=%.1f%%)', elapsed, ef)

        return {
            'status': 'success',
            'ejection_fraction': ef,
            'ef_category': category,
            'reduced_ef_screen': reduced_ef_screen,
            'ed_area_px': ed_area,
            'es_area_px': es_area,
            'ed_frame': ed_idx,
            'es_frame': es_idx,
            'frames_analyzed': len(frames),
            'overlay_path': overlay_path,
            'original_video_path': file_path,
            'report': report,
            'models_used': [
                'DeepLabV3-ResNet50 (EchoNet-Dynamic)',
                'R(2+1)D-18 (EchoNet-Dynamic)',
            ],
            'timestamp': timestamp,
            'elapsed_seconds': elapsed,
        }

    except Exception as e:
        logger.exception('analyze_echo failed')
        return {'status': 'failed', 'error': str(e), 'error_type': type(e).__name__}


# ---- on-demand SHAP explainability ----------------------------------------

def _build_ef_clip(norm_fchw: np.ndarray, start: int = 0):
    """Build ONE EF clip (3, CLIP_LEN, H, W) the same way ``_predict_ef`` does.

    Loops the video if it is shorter than one clip span, then samples CLIP_LEN
    frames at stride CLIP_PERIOD starting at ``start``. Returns the (3, T, H, W)
    clip plus the looped source (so the caller can fetch aligned display frames).
    """
    span = CLIP_LEN * CLIP_PERIOD
    src = norm_fchw
    if src.shape[0] < span:
        reps = int(np.ceil(span / src.shape[0]))
        src = np.tile(src, (reps, 1, 1, 1))
    clip = src[start:start + span:CLIP_PERIOD]          # (CLIP_LEN, 3, H, W)
    clip_3thw = np.transpose(clip, (1, 0, 2, 3))        # (3, T, H, W)
    return clip_3thw, src


def _render_echo_shap_figure(disp_frames, saliency, t_imp, ef, sel_idx, top_idx,
                             clip_period):
    """Build the Echo SHAP figure: saliency overlay montage + temporal curve.

    Top row: ``sel_idx`` representative clip frames (the most salient ones, in
    temporal order) with the SHAP saliency heat-overlaid on the 2D echo plane.
    Bottom: the per-frame importance curve over the analysed clip, with the top
    frames marked. Returns an Agg Figure (the caller saves + closes it).
    """
    k = len(sel_idx)
    fig = plt.figure(figsize=(3.2 * max(k, 2), 6.5))
    gs = fig.add_gridspec(2, max(k, 2), height_ratios=[3, 2])
    for j, idx in enumerate(sel_idx):
        ax = fig.add_subplot(gs[0, j])
        ax.imshow(disp_frames[idx].astype(np.uint8))
        ax.imshow(saliency[idx], cmap='hot', alpha=0.45, vmin=0.0, vmax=1.0)
        ax.set_title(f'frame {idx * clip_period}', fontsize=9)
        ax.axis('off')
    axc = fig.add_subplot(gs[1, :])
    x = np.arange(len(t_imp))
    axc.plot(x, t_imp, color='#d62728', linewidth=1.5)
    axc.fill_between(x, t_imp, color='#d62728', alpha=0.15)
    if top_idx:
        axc.scatter(top_idx, [t_imp[i] for i in top_idx], color='black', zorder=3, s=18)
    axc.set_xlabel('Clip frame (≈ time)')
    axc.set_ylabel('Frame importance')
    axc.set_ylim(0.0, 1.05)
    axc.grid(True, alpha=0.2)
    fig.suptitle(f'Echo EF SHAP saliency — EF {ef:.1f}% ({_ef_category(ef)})')
    plt.tight_layout()
    return fig


def explain_echo(file_path: str, n_samples: int = 8) -> dict:
    """On-demand SHAP (Captum GradientShap) saliency for the EchoNet EF model.

    Mirrors ``explain_ecg``: returns the standard inference envelope and NEVER
    raises into the DRF view (Contract 2). Attributes the SINGLE EF regression
    output (``target=0``) over ONE representative clip — "which frames and which
    regions of the 2D view drove the EF estimate".

    HONESTY: this is pixel/temporal saliency over a single 2D ultrasound plane —
    NOT regional wall-motion analysis (EchoNet gives a GLOBAL EF) and NOT a
    clinical rationale. (Attributing the LV segmentation model is left as a
    documented hook for a future v2 — EF is the clinically primary output.)

    THREAD-SAFETY: GradientShap backpropagates on the shared EF model singleton;
    safe today only because echo inference is synchronous (see echo_shap.py). Do
    not parallelize echo requests without revisiting this. R(2+1)D-18 over a clip
    is heavy on CPU, so the default ``n_samples`` is small; a GPU host (CUDA) makes
    a larger value affordable.

    Args:
        file_path: absolute path to an echo video (.avi / .mp4 / ...).
        n_samples: GradientShap samples (more = smoother, slower).

    Returns:
        On success: ``{status:'success', shap_path, ef, target:'ef',
        frame_importance:[...], top_frames:[{clip_index, video_frame, importance}],
        n_frames, elapsed_seconds}``.
        On failure: ``{status:'failed', error, error_type}``.
    """
    t_start = time.time()
    try:
        from django.conf import settings
        from .explainers.echo_shap import echo_gradient_shap, frame_importance

        loader = ModelLoader()
        device = loader.get_device()

        # 1. Load + normalise EXACTLY as analyze_echo, so the attribution matches
        #    what the EF model actually sees during normal inference.
        frames = load_echo_video(file_path)                 # (F,H,W,3) 0-255
        norm = _normalize(frames)                           # (F,3,H,W)

        seg_model, ef_model = loader.get_echo_models()      # raises if not bundled

        # 2. Build ONE representative clip (first clip, _predict_ef construction).
        clip_3thw, _ = _build_ef_clip(norm, start=0)        # (3, T, H, W)
        # Aligned display frames (looped the same way) for the overlay montage.
        disp_clip, _ = _build_ef_clip(np.transpose(frames, (0, 3, 1, 2)), start=0)
        disp_frames = np.transpose(disp_clip, (1, 2, 3, 0))  # (T, H, W, 3)

        # 3. EF for context (under no_grad — display only).
        with torch.no_grad():
            ctx = torch.from_numpy(clip_3thw).unsqueeze(0).float().to(device)
            ef = float(ef_model(ctx).item())
        ef = float(max(0.0, min(100.0, ef)))

        # 4. GradientShap (OUTSIDE no_grad — it backpropagates).
        saliency = echo_gradient_shap(ef_model, clip_3thw, n_samples=n_samples)  # (T,H,W)
        t_imp = frame_importance(saliency)                  # (T,) in [0,1]
        n_frames = int(saliency.shape[0])

        # 5. Top-3 frames by importance; selection for the montage = those frames
        #    in temporal order (left-to-right reads as time).
        order = [int(i) for i in np.argsort(t_imp)[::-1]]
        top_idx = order[:3]
        sel_idx = sorted(top_idx)
        top_frames = [
            {'clip_index': i, 'video_frame': int(i * CLIP_PERIOD),
             'importance': float(t_imp[i])}
            for i in top_idx
        ]

        # 6. Render + persist the SHAP montage + temporal curve. Stable name
        #    (input stem) so re-runs overwrite instead of accumulating.
        explanations_dir = os.path.join(settings.MEDIA_ROOT, 'echo', 'explanations')
        stem = os.path.splitext(os.path.basename(file_path))[0]
        out_name = f'{stem}_ef.png'
        fig = _render_echo_shap_figure(
            disp_frames, saliency, t_imp, ef, sel_idx, top_idx, CLIP_PERIOD)
        shap_path = save_visualization(fig, explanations_dir, out_name)
        plt.close(fig)

        elapsed = time.time() - t_start
        logger.info('explain_echo: complete in %.2fs (EF=%.1f%%)', elapsed, ef)
        return {
            'status': 'success',
            'shap_path': shap_path,
            'ef': ef,
            'target': 'ef',
            'frame_importance': [float(v) for v in t_imp],
            'top_frames': top_frames,
            'n_frames': n_frames,
            'elapsed_seconds': elapsed,
        }

    except Exception as e:
        logger.exception('explain_echo failed')
        return {'status': 'failed', 'error': str(e), 'error_type': type(e).__name__}
