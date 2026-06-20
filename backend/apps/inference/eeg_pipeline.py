"""End-to-end EEG analysis pipeline (BIOT, IIIC 6-class harmful-brain-activity).

Model: BIOT — Biosignal Transformer (Yang et al., NeurIPS 2023,
github.com/ycq091044/BIOT). The encoder is BIOT's *released* pretrained checkpoint;
the 6-class IIIC head is fine-tuned on the Kaggle HMS dataset (see
``tools/train_eeg_head.py``). The six classes are the Ictal-Interictal-Injury
Continuum patterns: Seizure (SZ), Lateralized/Generalized Periodic Discharges
(LPD/GPD), Lateralized/Generalized Rhythmic Delta Activity (LRDA/GRDA), and Other.

SCOPE / HONESTY: this is *functional* screening for harmful brain activity, the
complement to the *structural* MRI tumour analysis. It never diagnoses a tumour —
it flags harmful electrical patterns (e.g. tumour-related seizures / focal periodic
discharges) that a tumour is one of several acute causes of. IIIC is critical-care
EEG, trained on a general critically-ill cohort, not a tumour cohort.

A whole EDF recording is split into consecutive 10 s segments; BIOT classifies each
segment and the pipeline aggregates to per-class proportions over time, a dominant
pattern, and a harmful-activity flag (any SZ/LPD/GPD).
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

from .eeg_preprocess import (
    BIPOLAR_CHANNEL_NAMES,
    HARMFUL_CLASSES,
    IIIC_CLASS_NAMES,
    IIIC_CLASSES,
    SEGMENT_SECONDS,
    TARGET_RATE,
    edf_to_bipolar,
    segment_recording,
    stack_segments,
)
from .model_loader import ModelLoader
from .utils import save_visualization

logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..', '..'))
EEG_RESULTS_DIR = os.path.join(_BACKEND_DIR, 'media', 'eeg', 'results')

# Violet accent matching the frontend EEG theme; harmful classes drawn in red.
_BAR_COLOR = '#a855f7'
_HARMFUL_COLOR = '#ef4444'
_BATCH = 16


def _predict_segments(model, x: torch.Tensor, device: str) -> np.ndarray:
    """Run BIOT over a (n, 16, 2000) batch -> (n, 6) softmax probabilities."""
    probs = []
    with torch.no_grad():
        for i in range(0, x.shape[0], _BATCH):
            chunk = x[i:i + _BATCH].to(device)
            logits = model(chunk)
            probs.append(torch.softmax(logits, dim=1).cpu().numpy())
    return np.concatenate(probs, axis=0)


def _build_visualization(distribution, seg_labels, seg_conf, timestamp) -> str:
    """Two-panel figure: class-distribution bar chart + per-segment timeline."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5))

    colors = [_HARMFUL_COLOR if c in HARMFUL_CLASSES else _BAR_COLOR for c in IIIC_CLASSES]
    pct = [distribution[c] * 100.0 for c in IIIC_CLASSES]
    ax1.bar(IIIC_CLASSES, pct, color=colors)
    ax1.set_ylabel('% of recording')
    ax1.set_title('IIIC class distribution')
    ax1.set_ylim(0, 100)
    for i, v in enumerate(pct):
        ax1.text(i, v + 1, f'{v:.0f}%', ha='center', va='bottom', fontsize=8)

    # timeline: one point per 10 s segment, y = class index, red if harmful
    xs = np.arange(len(seg_labels)) * 10  # seconds
    ys = [IIIC_CLASSES.index(c) for c in seg_labels]
    tl_colors = [_HARMFUL_COLOR if c in HARMFUL_CLASSES else _BAR_COLOR for c in seg_labels]
    ax2.scatter(xs, ys, c=tl_colors, s=28)
    ax2.set_yticks(range(len(IIIC_CLASSES)))
    ax2.set_yticklabels(IIIC_CLASSES)
    ax2.set_xlabel('Time (s)')
    ax2.set_title('Dominant pattern over time')
    ax2.set_ylim(-0.5, len(IIIC_CLASSES) - 0.5)
    ax2.grid(True, axis='x', alpha=0.3)

    fig.suptitle('EEG — BIOT IIIC harmful-brain-activity screening')
    fig.tight_layout()
    path = save_visualization(fig, EEG_RESULTS_DIR, f'{timestamp}_eeg.png')
    plt.close(fig)
    return path


def analyze_eeg(file_path: str) -> dict:
    """Run the full EEG pipeline on an .edf file. Returns a result-envelope dict."""
    t_start = time.time()
    try:
        loader = ModelLoader()
        device = loader.get_device()
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        os.makedirs(EEG_RESULTS_DIR, exist_ok=True)

        logger.info('analyze_eeg: loading %s', file_path)
        bipolar = edf_to_bipolar(file_path)                 # (16, T) @ 200 Hz
        segments = segment_recording(bipolar)               # list of (16, 2000)
        x = stack_segments(segments)                        # (n, 16, 2000)

        model = loader.get_eeg_model()                      # raises if head not trained
        probs = _predict_segments(model, x, device)         # (n, 6)

        seg_idx = probs.argmax(axis=1)
        seg_labels = [IIIC_CLASSES[i] for i in seg_idx]
        seg_conf = probs.max(axis=1)
        n_seg = len(seg_labels)

        # per-class proportion of the recording (fraction of 10 s segments)
        counts = {c: 0 for c in IIIC_CLASSES}
        for c in seg_labels:
            counts[c] += 1
        distribution = {c: counts[c] / n_seg for c in IIIC_CLASSES}
        # mean softmax probability per class (a softer view of the same thing)
        mean_prob = {c: float(probs[:, i].mean()) for i, c in enumerate(IIIC_CLASSES)}

        dominant = max(IIIC_CLASSES, key=lambda c: distribution[c])
        harmful_segments = int(sum(1 for c in seg_labels if c in HARMFUL_CLASSES))
        harmful = harmful_segments > 0
        harmful_proportion = harmful_segments / n_seg

        # High-recall screening signal: ANY IIIC pattern present (vs benign
        # 'Other'). Report-grade HMS held-out split (n=1883): abnormal-detection
        # recall 0.93, and SEIZURE windows flagged as *some* IIIC pattern 0.966
        # of the time (VALIDATION.md §5) — the most critical miss is covered even
        # though the general screen sits just under 0.95. This is the routing
        # signal ("send for neurologist review"), deliberately broader than
        # `harmful` (SZ/LPD/GPD); the 6-way TYPE label is unreliable and must not
        # be used to rule a seizure in or out — only to route. The model has near-
        # zero benign specificity, so it errs toward flagging (the safe direction).
        iiic_segments = int(sum(1 for c in seg_labels if c != 'Other'))
        screen_positive = iiic_segments > 0
        iiic_proportion = iiic_segments / n_seg

        plot_path = _build_visualization(distribution, seg_labels, seg_conf, timestamp)

        dist_lines = '\n'.join(
            f'  {c:<5} ({IIIC_CLASS_NAMES[c]:<42}): {distribution[c] * 100:5.1f}%'
            f'  [mean p={mean_prob[c]:.2f}]'
            for c in IIIC_CLASSES
        )
        report = f"""
====================================================
EEG HARMFUL-BRAIN-ACTIVITY SCREENING REPORT
Generated: {timestamp}
====================================================

MODEL: BIOT (Biosignal Transformer), IIIC 6-class head
  Pretrained encoder + head fine-tuned on Kaggle HMS.

RECORDING:
  Segments analysed: {n_seg} x 10 s  ({n_seg * 10} s total)
  Channels: 16-lead longitudinal-bipolar montage @ 200 Hz

DOMINANT PATTERN: {dominant} ({IIIC_CLASS_NAMES[dominant]})

SCREEN (any IIIC pattern -> review): {'POSITIVE' if screen_positive else 'negative'}
  IIIC segments: {iiic_segments}/{n_seg} ({iiic_proportion * 100:.1f}% of recording)
  Routing signal — abnormal-detection recall 0.93; catches 96.6% of seizures as
  *some* IIIC pattern. Sensitive by design (low benign specificity) — confirm type clinically.

HARMFUL ACTIVITY (SZ / LPD / GPD): {'YES' if harmful else 'no'}
  Harmful segments: {harmful_segments}/{n_seg} ({harmful_proportion * 100:.1f}% of recording)

IIIC CLASS DISTRIBUTION (proportion of recording):
{dist_lines}

SCOPE: Functional screening for harmful brain activity — the complement to the
structural MRI tumour analysis. This does NOT diagnose a tumour; it flags harmful
electrical patterns (which a tumour is one acute cause of). IIIC is critical-care
EEG from a general critically-ill cohort, not a tumour cohort.

DISCLAIMER: AI-assisted analysis. Clinical decisions must be made by a qualified
physician.
====================================================
""".strip()

        elapsed = time.time() - t_start
        logger.info('analyze_eeg: complete in %.2fs (dominant=%s, harmful=%s)',
                    elapsed, dominant, harmful)

        return {
            'status': 'success',
            'dominant_pattern': dominant,
            'dominant_pattern_name': IIIC_CLASS_NAMES[dominant],
            'harmful': harmful,
            'harmful_proportion': harmful_proportion,
            'screen_positive': screen_positive,
            'iiic_proportion': iiic_proportion,
            'class_distribution': distribution,
            'mean_probabilities': mean_prob,
            'segment_labels': seg_labels,
            'segment_confidence': [float(v) for v in seg_conf],
            'segments_analyzed': n_seg,
            'plot_path': plot_path,
            'original_file_path': file_path,
            'report': report,
            'models_used': ['BIOT encoder (EEG-PREST-16)', 'BIOT IIIC 6-class head (HMS-finetuned)'],
            'timestamp': timestamp,
            'elapsed_seconds': elapsed,
        }

    except Exception as e:
        logger.exception('analyze_eeg failed')
        return {'status': 'failed', 'error': str(e), 'error_type': type(e).__name__}


# ---- on-demand SHAP explainability ----------------------------------------

def _resolve_target_class(value) -> int | None:
    """Map a requested target class to an IIIC index, or None if invalid.

    Accepts a canonical class name ('SZ', 'Other', case-insensitive) or an index
    (int or numeric string, 0..5). Anything else -> None (caller falls back to the
    predicted class). Mirrors ``explain_ecg``'s invalid-pathology handling.
    """
    if value is None or isinstance(value, bool):  # bool is an int subclass — exclude
        return None
    if isinstance(value, int):
        return value if 0 <= value < len(IIIC_CLASSES) else None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        upper = s.upper()
        for i, c in enumerate(IIIC_CLASSES):
            if c.upper() == upper:
                return i
        if s.isdigit():
            idx = int(s)
            return idx if 0 <= idx < len(IIIC_CLASSES) else None
    return None


def _render_eeg_shap_figure(segment, shap_map, channel_names, fs, code, class_name,
                            probability):
    """Build the 16-channel SHAP plot: each bipolar trace with its saliency shaded.

    Mirrors ``_render_ecg_shap_figure`` (one row per channel; the SHAP saliency is
    drawn as a hot-colormap background band so it reads as "where in time / which
    channel mattered"). Returns an Agg Figure (the caller saves + closes it).
    """
    n = segment.shape[0]
    fig, axes = plt.subplots(n, 1, figsize=(12, 14), sharex=True)
    t_axis = np.arange(segment.shape[1]) / fs
    for i in range(n):
        ax = axes[i]
        ymin = float(np.min(segment[i]))
        ymax = float(np.max(segment[i]))
        if ymax <= ymin:
            ymax = ymin + 1.0
        ax.imshow(shap_map[i][np.newaxis, :], aspect='auto', cmap='hot', alpha=0.45,
                  extent=[float(t_axis[0]), float(t_axis[-1]), ymin, ymax],
                  origin='lower', vmin=0.0, vmax=1.0)
        ax.plot(t_axis, segment[i], linewidth=0.5, color='black')
        ax.set_ylabel(channel_names[i], fontsize=7, rotation=0, ha='right', va='center')
        ax.set_ylim(ymin, ymax)
        ax.set_yticks([])
        ax.grid(True, axis='x', alpha=0.2)
    axes[-1].set_xlabel('Time (s)')
    fig.suptitle(f'EEG SHAP saliency — {code} ({class_name}) {probability:.1%}')
    plt.tight_layout()
    return fig


def explain_eeg(file_path: str, target_class=None) -> dict:
    """On-demand SHAP (Captum GradientShap) saliency for the BIOT IIIC EEG model.

    Mirrors ``explain_ecg`` / ``explain_mri``: returns the standard inference
    envelope and NEVER raises into the DRF view (Contract 2). BIOT is multi-class,
    so — like the Swin MRI classifier — it attributes the PREDICTED class (argmax of
    the mean 6-class softmax) by default, or a specific one of the 6 IIIC classes
    when ``target_class`` is given (by canonical name or index). An invalid value
    falls back to the predicted class (kept explicit via the returned fields) so a
    bad client value never breaks the envelope contract.

    A whole recording is many 10 s segments; SHAP attributes the single segment that
    most strongly expresses the target class (its highest-probability segment) — the
    most representative window to explain — and reports that segment's index/time.

    THREAD-SAFETY: GradientShap backpropagates on the shared BIOT model singleton;
    safe today only because inference is synchronous (see eeg_shap.py). Do not
    parallelize EEG requests without revisiting this.

    Args:
        file_path: absolute path to a referential 10-20 EDF recording.
        target_class: optional IIIC class to attribute — canonical name
            ('SZ'/'LPD'/'GPD'/'LRDA'/'GRDA'/'Other') or index 0..5; default/invalid
            -> predicted class.

    Returns:
        On success: ``{status:'success', shap_path, predicted_class, target_class,
        class_probabilities, probability, per_channel_importance:{channel: score},
        top_channels:[...], segment_index, segment_seconds, ...}``.
        On failure: ``{status:'failed', error, error_type}``.
    """
    t_start = time.time()
    try:
        from django.conf import settings
        from .explainers.eeg_shap import eeg_gradient_shap, per_channel_importance

        loader = ModelLoader()
        device = loader.get_device()

        # 1. Load + preprocess EXACTLY as analyze_eeg, so the attribution matches
        #    what the classifier actually sees during normal inference.
        bipolar = edf_to_bipolar(file_path)            # (16, T) @ 200 Hz
        segments = segment_recording(bipolar)          # list of (16, 2000)
        x = stack_segments(segments)                   # (n, 16, 2000)

        model = loader.get_eeg_model()                 # raises if head not trained
        probs = _predict_segments(model, x, device)    # (n, 6) softmax

        # 2. Mean softmax per class -> class_probabilities + predicted (argmax).
        mean_prob = {c: float(probs[:, i].mean()) for i, c in enumerate(IIIC_CLASSES)}
        predicted_idx = int(np.argmax([mean_prob[c] for c in IIIC_CLASSES]))
        predicted_class = IIIC_CLASSES[predicted_idx]

        # 3. Resolve the target class: requested-if-valid, else predicted.
        target_idx = _resolve_target_class(target_class)
        if target_idx is None:
            target_idx = predicted_idx
        target_code = IIIC_CLASSES[target_idx]

        # 4. Attribute the segment that most strongly expresses the target class.
        seg_idx = int(np.argmax(probs[:, target_idx]))
        segment = np.asarray(segments[seg_idx], dtype=np.float32)  # (16, 2000)

        # 5. GradientShap (OUTSIDE no_grad — it backpropagates).
        shap_map = eeg_gradient_shap(model, segment, target_class=target_idx)  # (16, 2000)
        chan_imp = per_channel_importance(shap_map, BIPOLAR_CHANNEL_NAMES)
        top_channels = [ch for ch, _ in sorted(chan_imp.items(), key=lambda kv: -kv[1])[:3]]

        # 6. Render + persist. Stable name (input stem + class) so re-runs overwrite.
        explanations_dir = os.path.join(settings.MEDIA_ROOT, 'eeg', 'explanations')
        stem = os.path.splitext(os.path.basename(file_path))[0]
        out_name = f'{stem}_{target_code}.png'
        fig = _render_eeg_shap_figure(
            segment, shap_map, BIPOLAR_CHANNEL_NAMES, TARGET_RATE,
            target_code, IIIC_CLASS_NAMES[target_code], mean_prob[target_code])
        shap_path = save_visualization(fig, explanations_dir, out_name)
        plt.close(fig)

        elapsed = time.time() - t_start
        logger.info('explain_eeg: %s complete in %.2fs', target_code, elapsed)
        return {
            'status': 'success',
            'shap_path': shap_path,
            'predicted_class': predicted_class,
            'predicted_class_name': IIIC_CLASS_NAMES[predicted_class],
            'target_class': target_code,
            'target_class_name': IIIC_CLASS_NAMES[target_code],
            'requested_class': target_class if isinstance(target_class, (str, int)) else None,
            'probability': mean_prob[target_code],
            'class_probabilities': mean_prob,
            'per_channel_importance': chan_imp,
            'top_channels': top_channels,
            'segment_index': seg_idx,
            'segment_seconds': seg_idx * SEGMENT_SECONDS,
            'segments_analyzed': len(segments),
            'elapsed_seconds': elapsed,
        }

    except Exception as e:
        logger.exception('explain_eeg failed')
        return {'status': 'failed', 'error': str(e), 'error_type': type(e).__name__}
