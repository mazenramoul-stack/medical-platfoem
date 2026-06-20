"""End-to-end 12-lead ECG analysis pipeline.

Two streams:
    1. DenseNet-1D-121 x7  (ecglib, pre-trained on 500,000+ ECGs)
       -> per-pathology probabilities + primary diagnosis
    2. NeuroKit2           (HRV time-domain analysis on Lead II)
       -> mean HR, RMSSD, SDNN, pNN50 + rule-based flags

No training code: all models are pre-trained and loaded via ModelLoader.
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
from scipy.signal import butter, filtfilt

from .model_loader import ModelLoader
from .utils import load_ecg_signal, save_visualization

logger = logging.getLogger(__name__)

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..', '..'))
ECG_RESULTS_DIR = os.path.join(_BACKEND_DIR, 'media', 'ecg', 'results')

PATHOLOGY_FULL_NAMES = {
    "AFIB":  "Atrial Fibrillation",
    "1AVB":  "1st Degree AV Block",
    "STACH": "Sinus Tachycardia",
    "SBRAD": "Sinus Bradycardia",
    "RBBB":  "Right Bundle Branch Block",
    "LBBB":  "Left Bundle Branch Block",
    "PVC":   "Premature Ventricular Complex",
}

LEAD_NAMES = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']

# Per-pathology detection thresholds. A flat 0.5 massively over-flags these
# models: on PTB-XL the DenseNet-1D classifiers are excellent rankers
# (per-pathology AUC ~0.97-1.00) but output high probabilities. Two calibrated
# operating points are provided, BOTH tuned on PTB-XL fold 9 (validation) and
# verified on fold 10 (test) — no leakage. Switch with the ECG_THRESHOLD_MODE
# env var ('f1' default — balanced; set 'recall' for screening / safety-first).
#
#   RECALL_FIRST (opt-in: ECG_THRESHOLD_MODE=recall) — screening / safety-first.
#       Chosen so every pathology
#       reaches recall >= 0.95 on the held-out TEST fold (macro recall 0.98,
#       only 13 false negatives in 2,198 records). This is the clinical posture:
#       a screening tool must not MISS a positive. The cost is precision — macro
#       ~0.35 (more false alarms); the tool flags liberally for human review.
#       Reproduce: python tools/tune_ecg_recall.py --target 0.98
#
#   F1_BALANCED (default) — balanced precision/recall. Best when minimizing TOTAL
#       errors matters more than never missing. Thresholds tuned per pathology on
#       fold 9 (no test leakage). Updated 2026-06-16 for the F1 fine-tuned
#       STACH/SBRAD/1AVB/LBBB checkpoints (tools/finetune_ecg_f1.py — F1
#       objective + augmentation) layered on the earlier 1AVB/RBBB/PVC fine-tune;
#       per-class F1 verified locally 2026-06-16 (STACH 0.85, SBRAD 0.61, 1AVB
#       0.63, LBBB 0.82; macro F1 0.727 -> 0.777 on PTB-XL fold 10). Reproduce:
#       tools/eval_ecg_classifier.py --tune-fold 9 --fold 10
#
# See VALIDATION.md §1 for both operating-point tables.
RECALL_FIRST_THRESHOLDS = {
    'AFIB':  0.10,
    '1AVB':  0.12,
    'STACH': 0.26,
    'SBRAD': 0.18,
    'RBBB':  0.43,
    'LBBB':  0.66,
    'PVC':   0.49,
}
F1_BALANCED_THRESHOLDS = {
    'AFIB':  0.91,
    '1AVB':  0.90,   # F1 fine-tune (2026-06-16): F1 0.521 -> 0.632
    'STACH': 0.92,   # F1 fine-tune (2026-06-16): F1 0.684 -> 0.852
    'SBRAD': 0.89,   # F1 fine-tune (2026-06-16): F1 0.474 -> 0.613
    'RBBB':  0.95,
    'LBBB':  0.96,   # F1 fine-tune (2026-06-16): F1 0.800 -> 0.816
    'PVC':   0.96,
}
_THRESHOLD_MODE = os.environ.get('ECG_THRESHOLD_MODE', 'f1').strip().lower()
DETECTION_THRESHOLDS = (
    RECALL_FIRST_THRESHOLDS if _THRESHOLD_MODE == 'recall' else F1_BALANCED_THRESHOLDS
)
DEFAULT_DETECTION_THRESHOLD = 0.5  # fallback for any code not tuned above


# ---- helpers --------------------------------------------------------------

def classify_hr(hr: float) -> str:
    """Return 'Bradycardia' / 'Tachycardia' / 'Normal' from a mean heart rate."""
    if np.isnan(hr):
        return 'N/A'
    if hr < 60:
        return 'Bradycardia'
    if hr > 100:
        return 'Tachycardia'
    return 'Normal'


def format_pathology_table(results: dict) -> str:
    """Format the per-pathology probability dict as a multi-line table."""
    lines = []
    for code, r in sorted(results.items(), key=lambda x: -x[1]['probability']):
        flag = '[!]' if r['detected'] else '   '
        full = PATHOLOGY_FULL_NAMES.get(code, code)
        lines.append(f"  {flag} {code:6s}  {full:40s}  {r['probability']:.2%}")
    return '\n'.join(lines)


def _scalar_probability(model_output) -> float:
    """Squeeze a torch model output to a single sigmoid probability.

    ecglib models can return tensors of shape (1, 1), (1,), or () depending on
    architecture. This helper collapses to a Python float in [0, 1].
    """
    if isinstance(model_output, tuple):
        model_output = model_output[0]
    t = model_output.squeeze()
    if t.dim() > 0:
        t = t.flatten()[0]
    return float(torch.sigmoid(t).item())


def _safe_number(v):
    """Replace NaN/Inf with None so the result survives JSON serialization."""
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    return v


def _sanitize(obj):
    """Recursively walk a dict/list and replace NaN/Inf floats with None.

    Synthetic or malformed ECG inputs can cause downstream HRV / probability
    values to come back as NaN, and DRF's JSONRenderer (which uses stdlib json)
    refuses to serialize those. Clean once at the pipeline boundary so
    everything downstream — DB writes, REST responses — is safe.
    """
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return _safe_number(obj)


# ---- main pipeline --------------------------------------------------------

def analyze_ecg(file_path: str) -> dict:
    """Run the full 12-lead ECG analysis pipeline.

    Args:
        file_path: absolute path to an ECG file (.csv / .edf / .dat+.hea).
    Returns:
        Result dict with diagnosis, per-pathology probs, HR/HRV metrics,
        rule-based flags, plot path, and a human-readable report.
        On error returns {'status': 'failed', 'error': ..., 'error_type': ...}.
    """
    t_start = time.time()
    try:
        loader = ModelLoader()
        device = loader.get_device()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(ECG_RESULTS_DIR, exist_ok=True)

        # 1. Load -------------------------------------------------------------
        logger.info("analyze_ecg: loading %s", file_path)
        signal, fs, lead_quality = load_ecg_signal(file_path)  # (12, 5000) at 500 Hz
        for w in lead_quality.get('warnings', []):
            logger.warning("analyze_ecg input quality: %s", w)

        # Refuse a reduced lead set rather than emit a silently-wrong diagnosis.
        # <12 leads means load_ecg_signal broadcast lead I across all 12 channels;
        # the 12-lead pathology models would then "diagnose" 12 copies of one lead
        # and return a confident but meaningless result. (Positional / incomplete-
        # label inputs still run — they have 12 genuine channels — but are flagged
        # via reduced_lead_set + input_quality in the result.)
        if lead_quality.get('padded_from_fewer'):
            n = lead_quality.get('n_leads_detected', 0)
            logger.error("analyze_ecg: refusing reduced lead set (%d lead(s))", n)
            return {
                'status': 'failed',
                'error': (f'Reduced lead set: only {n} lead(s) detected. The 12-lead '
                          f'pathology models require a full 12-lead ECG — refusing to '
                          f'broadcast a single lead and report an unreliable diagnosis.'),
                'error_type': 'InsufficientLeads',
                'input_quality': lead_quality,
            }

        # 2. Preprocess -------------------------------------------------------
        b, a = butter(4, [0.5, 40], btype='bandpass', fs=fs)
        signal_filtered = filtfilt(b, a, signal, axis=1)
        signal_normalized = (
            (signal_filtered - signal_filtered.mean(axis=1, keepdims=True))
            / (signal_filtered.std(axis=1, keepdims=True) + 1e-8)
        )

        # 3. NeuroKit2 HRV / rate analysis on Lead II -----------------------
        logger.info("analyze_ecg: NeuroKit2 HRV on Lead II")
        import neurokit2 as nk
        lead_II = signal_normalized[1].astype(np.float64)
        cleaned = nk.ecg_clean(lead_II, sampling_rate=int(fs))
        _, peaks_info = nk.ecg_peaks(cleaned, sampling_rate=int(fs))
        try:
            hr_values = nk.ecg_rate(peaks_info, sampling_rate=int(fs), desired_length=len(cleaned))
            mean_hr = float(np.nanmean(hr_values))
        except Exception as e:
            logger.warning("HR estimation failed: %s", e)
            mean_hr = float('nan')
        try:
            hrv_time = nk.hrv_time(peaks_info, sampling_rate=int(fs))
            rmssd = float(hrv_time['HRV_RMSSD'].iloc[0]) if 'HRV_RMSSD' in hrv_time.columns else 0.0
            sdnn  = float(hrv_time['HRV_SDNN'].iloc[0])  if 'HRV_SDNN'  in hrv_time.columns else 0.0
            pnn50 = float(hrv_time['HRV_pNN50'].iloc[0]) if 'HRV_pNN50' in hrv_time.columns else 0.0
        except Exception as e:
            logger.warning("HRV time-domain failed: %s", e)
            rmssd = sdnn = pnn50 = 0.0

        # 4. Deep-learning pathology classifiers -----------------------------
        logger.info("analyze_ecg: running DenseNet-1D pathology classifiers")
        ecg_models = loader.get_ecg_models()
        input_tensor = torch.from_numpy(signal_normalized).float().unsqueeze(0).to(device)

        pathology_results = {}
        for code, model in ecg_models.items():
            try:
                with torch.no_grad():
                    out = model(input_tensor)
                prob = _scalar_probability(out)
            except Exception as e:
                logger.warning("ECG inference for %s failed: %s", code, e)
                continue
            threshold = DETECTION_THRESHOLDS.get(code, DEFAULT_DETECTION_THRESHOLD)
            pathology_results[code] = {
                'probability': prob,
                'detected': prob > threshold,
                'threshold': threshold,
            }

        if not pathology_results:
            raise RuntimeError("No ECG pathology models produced a valid prediction.")

        # 5. Primary diagnosis -----------------------------------------------
        detected_list = [(c, r['probability']) for c, r in pathology_results.items() if r['detected']]
        if detected_list:
            detected_list.sort(key=lambda x: x[1], reverse=True)
            primary_diagnosis = detected_list[0][0]
            diagnosis_confidence = detected_list[0][1]
            arrhythmia_detected = True
        else:
            primary_diagnosis = 'Normal Sinus Rhythm'
            diagnosis_confidence = 1.0 - max(r['probability'] for r in pathology_results.values())
            arrhythmia_detected = False
        diagnosis_full = PATHOLOGY_FULL_NAMES.get(primary_diagnosis, primary_diagnosis)

        # 6. Rule-based cross-validation -------------------------------------
        flags = []
        # Surface input-quality problems FIRST — a reduced/mis-ordered lead set
        # makes every pathology probability below untrustworthy, so the clinician
        # must see it prominently rather than reading a confident wrong result.
        for w in lead_quality.get('warnings', []):
            flags.append(f"Input quality: {w}")
        if not np.isnan(mean_hr):
            if mean_hr < 60:
                flags.append("Rule-based: Bradycardia (HR < 60)")
            elif mean_hr > 100:
                flags.append("Rule-based: Tachycardia (HR > 100)")
        if rmssd > 100:
            flags.append("Rule-based: High HRV variability — possible arrhythmia")

        # 7. Visualisation: 6x2 grid of leads --------------------------------
        logger.info("analyze_ecg: generating 12-lead plot")
        fig, axes = plt.subplots(6, 2, figsize=(14, 12), sharex=True)
        t_axis = np.arange(signal_normalized.shape[1]) / fs
        rpeaks = peaks_info.get('ECG_R_Peaks', np.array([], dtype=int))
        for i in range(12):
            ax = axes[i % 6, i // 6]
            ax.plot(t_axis, signal_normalized[i], linewidth=0.5)
            ax.set_ylabel(LEAD_NAMES[i], fontsize=8)
            ax.grid(True, alpha=0.3)
            if i == 1 and len(rpeaks) > 0:
                rp = np.asarray(rpeaks)
                rp = rp[rp < len(t_axis)]
                ax.plot(t_axis[rp], signal_normalized[1][rp], 'r.', markersize=4)
        axes[-1, 0].set_xlabel('Time (s)')
        axes[-1, 1].set_xlabel('Time (s)')
        fig.suptitle(f'ECG Analysis — {diagnosis_full} ({diagnosis_confidence:.1%})')
        plt.tight_layout()
        plot_path = save_visualization(fig, ECG_RESULTS_DIR, f"{timestamp}_ecg.png")
        plt.close(fig)

        # 8. Report -----------------------------------------------------------
        flags_block = '\n'.join(f'  {f}' for f in flags) if flags else '  None'
        report = f"""
════════════════════════════════════════════════════
12-LEAD ECG ANALYSIS REPORT
Generated: {timestamp}
════════════════════════════════════════════════════

PRIMARY DIAGNOSIS (DenseNet-1D, pretrained on 500k+ ECGs):
  Result: {diagnosis_full}
  Confidence: {diagnosis_confidence:.2%}
  Status: {'ABNORMAL' if arrhythmia_detected else 'NORMAL'}

DETAILED PATHOLOGY PROBABILITIES:
{format_pathology_table(pathology_results)}

HEART RATE ANALYSIS (NeuroKit2):
  Mean Heart Rate: {mean_hr:.1f} bpm
  Classification: {classify_hr(mean_hr)}

HEART RATE VARIABILITY (HRV):
  RMSSD: {rmssd:.2f} ms
  SDNN:  {sdnn:.2f} ms
  pNN50: {pnn50:.2f} %

RULE-BASED FLAGS:
{flags_block}

MODELS USED:
  - DenseNet-1D-121 x{len(ecg_models)} (ecglib, pretrained on 500,000+ ECGs)
  - NeuroKit2 (HRV time-domain analysis)

DISCLAIMER: AI-assisted diagnosis. Clinical decisions
must be made by a qualified cardiologist.
════════════════════════════════════════════════════
""".strip()

        elapsed = time.time() - t_start
        logger.info("analyze_ecg: complete in %.2fs", elapsed)

        return _sanitize({
            'status': 'success',
            'arrhythmia_detected': arrhythmia_detected,
            'diagnosis': diagnosis_full,
            'diagnosis_code': primary_diagnosis,
            'diagnosis_confidence': diagnosis_confidence,
            'all_pathology_probabilities': pathology_results,
            'heart_rate_bpm': mean_hr,
            'hr_classification': classify_hr(mean_hr),
            'hrv_metrics': {
                'RMSSD_ms': rmssd,
                'SDNN_ms': sdnn,
                'pNN50_percent': pnn50,
            },
            'additional_flags': flags,
            'input_quality': lead_quality,
            'reduced_lead_set': bool(
                lead_quality.get('padded_from_fewer')
                or lead_quality.get('positional_fallback')),
            'plot_path': plot_path,
            'report': report,
            'models_used': [
                'DenseNet-1D-121 (ecglib, Avetisyan et al. 2023)',
                'NeuroKit2 (Makowski et al. 2021)',
            ],
            'timestamp': timestamp,
            'elapsed_seconds': elapsed,
        })

    except Exception as e:
        logger.exception("analyze_ecg failed")
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__,
        }


# ---- on-demand SHAP explainability ----------------------------------------

def _render_ecg_shap_figure(signal, shap_map, fs, code, probability):
    """Build the 12-lead SHAP plot: each lead trace with its saliency shaded behind.

    Mirrors analyze_ecg's 6x2 grid; the SHAP saliency is drawn as a vertical-band
    background (hot colormap) so it reads as "where in time / which lead mattered".
    Returns an Agg Figure (the caller saves + closes it).
    """
    fig, axes = plt.subplots(6, 2, figsize=(14, 12), sharex=True)
    t_axis = np.arange(signal.shape[1]) / fs
    full = PATHOLOGY_FULL_NAMES.get(code, code)
    for i in range(12):
        ax = axes[i % 6, i // 6]
        ymin = float(np.min(signal[i]))
        ymax = float(np.max(signal[i]))
        if ymax <= ymin:
            ymax = ymin + 1.0
        ax.imshow(shap_map[i][np.newaxis, :], aspect='auto', cmap='hot', alpha=0.45,
                  extent=[float(t_axis[0]), float(t_axis[-1]), ymin, ymax],
                  origin='lower', vmin=0.0, vmax=1.0)
        ax.plot(t_axis, signal[i], linewidth=0.5, color='black')
        ax.set_ylabel(LEAD_NAMES[i], fontsize=8)
        ax.set_ylim(ymin, ymax)
        ax.grid(True, alpha=0.2)
    axes[-1, 0].set_xlabel('Time (s)')
    axes[-1, 1].set_xlabel('Time (s)')
    fig.suptitle(f'ECG SHAP saliency — {full} ({probability:.1%})')
    plt.tight_layout()
    return fig


def explain_ecg(file_path: str, pathology: str | None = None) -> dict:
    """On-demand SHAP (Captum GradientShap) saliency for the 12-lead ECG model.

    Mirrors ``explain_mri``: returns the standard inference envelope and NEVER
    raises into the DRF view (Contract 2). Attributes the PRIMARY diagnosis by
    default, or a specific one of the 7 pathologies when ``pathology`` is given.
    An invalid ``pathology`` falls back to the primary diagnosis (kept explicit
    via the returned ``pathology`` field) so a bad client value never breaks the
    envelope contract.

    THREAD-SAFETY: GradientShap backpropagates on the shared ECG model singleton;
    safe today only because inference is synchronous (see ecg_shap.py). Do not
    parallelize ECG requests without revisiting this.

    Args:
        file_path: absolute path to an ECG file (.csv / .edf / .dat+.hea).
        pathology: optional pathology code to attribute (one of AFIB, 1AVB, STACH,
            SBRAD, RBBB, LBBB, PVC); default/invalid -> primary diagnosis.

    Returns:
        On success: ``{status:'success', shap_path, pathology, pathology_full,
        probability, per_lead_importance:{lead: score}, top_leads:[...],
        requested_pathology, elapsed_seconds}``.
        On failure: ``{status:'failed', error, error_type}``.
    """
    t_start = time.time()
    try:
        from django.conf import settings
        from .explainers.ecg_shap import ecg_gradient_shap, per_lead_importance

        loader = ModelLoader()
        device = loader.get_device()

        # 1. Load + preprocess EXACTLY as analyze_ecg, so the attribution matches
        #    what the classifier actually sees during normal inference.
        signal, fs, lead_quality = load_ecg_signal(file_path)  # (12, 5000) @ 500 Hz
        if signal.shape[0] != 12 or lead_quality.get('padded_from_fewer'):
            n = lead_quality.get('n_leads_detected', int(signal.shape[0]))
            return {
                'status': 'failed',
                'error': (f'Reduced lead set: only {n} genuine lead(s) detected. SHAP '
                          f'attribution on a broadcast single lead would be meaningless '
                          f'— refusing (the 12-lead models require a full 12-lead ECG).'),
                'error_type': 'InsufficientLeads',
            }
        b, a = butter(4, [0.5, 40], btype='bandpass', fs=fs)
        signal_filtered = filtfilt(b, a, signal, axis=1)
        signal_normalized = (
            (signal_filtered - signal_filtered.mean(axis=1, keepdims=True))
            / (signal_filtered.std(axis=1, keepdims=True) + 1e-8)
        ).astype(np.float32)

        # 2. Models + per-pathology probabilities (to pick the primary diagnosis).
        ecg_models = loader.get_ecg_models()
        if not ecg_models:
            raise RuntimeError('No ECG pathology models are loaded.')
        input_tensor = torch.from_numpy(signal_normalized).float().unsqueeze(0).to(device)
        probs = {}
        for code, model in ecg_models.items():
            try:
                with torch.no_grad():
                    out = model(input_tensor)
                probs[code] = _scalar_probability(out)
            except Exception as e:
                logger.warning("explain_ecg: probability for %s failed: %s", code, e)
        if not probs:
            raise RuntimeError('No ECG pathology models produced a valid prediction.')

        # 3. Choose the target pathology: requested-if-valid, else primary (argmax).
        requested = pathology.strip().upper() if isinstance(pathology, str) and pathology.strip() else None
        if requested and requested in ecg_models:
            target_code = requested
        else:
            target_code = max(probs, key=probs.get)
        target_model = ecg_models[target_code]
        probability = float(probs.get(target_code, 0.0))

        # 4. GradientShap (OUTSIDE no_grad — it backpropagates).
        shap_map = ecg_gradient_shap(target_model, signal_normalized)  # (12, 5000) in [0,1]
        lead_imp = per_lead_importance(shap_map, LEAD_NAMES)
        top_leads = [lead for lead, _ in sorted(lead_imp.items(), key=lambda x: -x[1])[:3]]

        # 5. Render + persist the 12-lead SHAP plot. Stable name (input stem +
        #    pathology) so re-runs overwrite instead of accumulating.
        explanations_dir = os.path.join(settings.MEDIA_ROOT, 'ecg', 'explanations')
        stem = os.path.splitext(os.path.basename(file_path))[0]
        out_name = f'{stem}_{target_code}.png'
        fig = _render_ecg_shap_figure(signal_normalized, shap_map, fs, target_code, probability)
        shap_path = save_visualization(fig, explanations_dir, out_name)
        plt.close(fig)

        elapsed = time.time() - t_start
        logger.info("explain_ecg: %s complete in %.2fs", target_code, elapsed)
        return _sanitize({
            'status': 'success',
            'shap_path': shap_path,
            'pathology': target_code,
            'pathology_full': PATHOLOGY_FULL_NAMES.get(target_code, target_code),
            'probability': probability,
            'per_lead_importance': lead_imp,
            'top_leads': top_leads,
            'requested_pathology': requested,
            'elapsed_seconds': elapsed,
        })

    except Exception as e:
        logger.exception("explain_ecg failed")
        return {
            'status': 'failed',
            'error': str(e),
            'error_type': type(e).__name__,
        }
