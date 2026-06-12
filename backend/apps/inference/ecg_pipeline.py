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
# env var ('recall' default, or 'f1').
#
#   RECALL_FIRST (default) — screening / safety-first. Chosen so every pathology
#       reaches recall >= 0.95 on the held-out TEST fold (macro recall 0.98,
#       only 13 false negatives in 2,198 records). This is the clinical posture:
#       a screening tool must not MISS a positive. The cost is precision — macro
#       ~0.35 (more false alarms); the tool flags liberally for human review.
#       Reproduce: python tools/tune_ecg_recall.py --target 0.98
#
#   F1_BALANCED — balanced precision/recall (macro F1 0.727, precision 0.69,
#       recall 0.78). Best when minimizing TOTAL errors matters more than never
#       missing. Re-tuned June 2026 for the fine-tuned 1AVB/RBBB/PVC checkpoints
#       (PVC 0.69 -> 0.96; stock-only values: AFIB 0.89, 1AVB 0.96, RBBB 0.94,
#       PVC 0.69). Reproduce: tools/eval_ecg_classifier.py --tune-fold 9 --fold 10
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
    '1AVB':  0.85,
    'STACH': 0.97,
    'SBRAD': 0.97,
    'RBBB':  0.95,
    'LBBB':  0.99,
    'PVC':   0.96,
}
_THRESHOLD_MODE = os.environ.get('ECG_THRESHOLD_MODE', 'recall').strip().lower()
DETECTION_THRESHOLDS = (
    F1_BALANCED_THRESHOLDS if _THRESHOLD_MODE == 'f1' else RECALL_FIRST_THRESHOLDS
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
