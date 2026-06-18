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
