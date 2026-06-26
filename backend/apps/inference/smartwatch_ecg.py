"""Smartwatch single-lead ECG: digitize a PDF trace + screen it (Lead I only).

Consumer-watch ECG exports (Apple Watch, Samsung, Withings, KardiaMobile) record
a SINGLE lead (Lead I) and render it as a flat raster image inside a PDF — no
text layer, no vector waveform. This module recovers the Lead I waveform by
computer vision (isolate the red trace, find the horizontal strips, follow the
trace per column, concatenate to one 500 Hz signal) and runs a single-lead
rate/rhythm screening (NeuroKit2).

It is deliberately ONE lead. There is NO 12-lead pathology classification here —
one lead cannot support it, and broadcasting it into 12 fake leads would only
produce confident, meaningless output (exactly what ecg_pipeline.analyze_ecg
refuses). ``analyze_smartwatch_ecg`` returns the SAME result envelope shape as
``analyze_ecg`` (minus pathology probabilities) so the ECG upload/list/detail/
report chain can store and show it unchanged.

Two consumers:
    * apps.conversion ECG converter — .pdf -> single-lead CSV + inline result.
    * apps.ecg upload — .pdf -> a saved single-lead ECGAnalysis.

Heavy libs (PyMuPDF, Pillow, neurokit2, matplotlib) are imported lazily.
Validated against the watch's own printed HR: the digitized HR matched the
printed 76 bpm to ~0.1 bpm on the reference sample.
"""

from __future__ import annotations

import datetime
import io
import logging
import os
import time

import numpy as np

logger = logging.getLogger(__name__)

TARGET_FS = 500           # Hz the ECG tooling expects
STRIP_SECONDS = 10.0      # each printed strip spans 10 s
LEAD_NAME = "I"

# Red-trace segmentation thresholds (red waveform on a light grid).
_RED_DOMINANCE = 40
_RED_MIN = 110
_DENSE_ROW_FRAC = 0.05
_MIN_TRACE_FRAC = 0.0005

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.abspath(os.path.join(_THIS_DIR, '..', '..'))
ECG_RESULTS_DIR = os.path.join(_BACKEND_DIR, 'media', 'ecg', 'results')


class SmartwatchDigitizeError(ValueError):
    """Expected, user-facing digitization failure (carries an ``error_type``).

    A plain ValueError subclass so callers that don't know about it still treat
    it as bad input; the conversion app maps it to its ConversionError envelope,
    and analyze_smartwatch_ecg turns it into the failed-result envelope.
    """

    def __init__(self, message: str, error_type: str = 'DigitizeError'):
        super().__init__(message)
        self.error_type = error_type


# ---- computer-vision digitization -----------------------------------------

def _extract_page_image(input_path: str) -> np.ndarray:
    """Return the first PDF page's largest embedded raster as an RGB array."""
    try:
        import fitz  # PyMuPDF
        from PIL import Image
    except Exception as e:  # pragma: no cover - dependency guard
        raise SmartwatchDigitizeError(
            f'Smartwatch PDF support requires PyMuPDF/Pillow ({e}).', 'MissingDependency')

    try:
        doc = fitz.open(input_path)
    except Exception as e:
        raise SmartwatchDigitizeError(f'Could not open the PDF: {e}', 'UnreadablePDF')
    try:
        if doc.page_count == 0:
            raise SmartwatchDigitizeError('PDF has no pages.', 'EmptyPDF')
        page = doc[0]
        images = page.get_images(full=True)
        if images:
            xref = max(images, key=lambda im: im[2] * im[3])[0]
            img_bytes = doc.extract_image(xref)["image"]
            return np.asarray(Image.open(io.BytesIO(img_bytes)).convert("RGB"))
        pix = page.get_pixmap(dpi=300)
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        return arr[:, :, :3].copy()
    finally:
        doc.close()


def _red_mask(rgb: np.ndarray) -> np.ndarray:
    R = rgb[:, :, 0].astype(int)
    G = rgb[:, :, 1].astype(int)
    B = rgb[:, :, 2].astype(int)
    return ((R - (G + B) // 2) > _RED_DOMINANCE) & (R > _RED_MIN)


def _find_strip_bands(mask: np.ndarray) -> list[tuple[int, int]]:
    """Locate each ECG strip as a (y0, y1) window centred on its baseline.

    Dense baseline rows (red across most of the width) mark each strip; stray
    slivers are dropped by red-pixel MASS relative to the strongest strip, and
    each survivor is expanded to a symmetric window sized from the inter-strip
    spacing so the full deflection is captured without bleeding into neighbours.
    """
    H, W = mask.shape
    active = mask.sum(axis=1) > (_DENSE_ROW_FRAC * W)

    runs = []
    start = None
    for y, a in enumerate(active):
        if a and start is None:
            start = y
        elif not a and start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, H))
    if not runs:
        return []

    masses = [(int(mask[s:e].sum()), (s + e) // 2) for s, e in runs]
    max_mass = max(m for m, _ in masses)
    centers = sorted(c for m, c in masses if m >= 0.3 * max_mass)
    if not centers:
        return []

    spacing = int(np.median(np.diff(centers))) if len(centers) > 1 else H // 3
    half = max(8, int(0.42 * spacing))
    return [(max(0, c - half), min(H, c + half)) for c in centers]


def _trace_band(mask: np.ndarray, y0: int, y1: int) -> np.ndarray:
    """Per column, the red-pixel centroid (timing-faithful); gaps interpolated."""
    sub = mask[y0:y1]
    W = sub.shape[1]
    ys_index = np.arange(sub.shape[0])
    sig = np.full(W, np.nan)
    for x in range(W):
        col = sub[:, x]
        if col.any():
            sig[x] = ys_index[col].mean()

    valid = np.where(~np.isnan(sig))[0]
    if valid.size == 0:
        return np.array([])
    seg = sig[valid[0]:valid[-1] + 1]
    idx = np.arange(seg.size)
    good = ~np.isnan(seg)
    seg = np.interp(idx, idx[good], seg[good])
    return -(seg - seg.mean())  # invert: image y grows downward; ECG up = positive


def _resample(seg: np.ndarray, n: int) -> np.ndarray:
    if seg.size == 0:
        return np.zeros(n)
    return np.interp(np.linspace(0, 1, n), np.linspace(0, 1, seg.size), seg)


def digitize(input_path: str):
    """Recover the Lead I waveform from a smartwatch ECG PDF.

    Returns ``(signal, fs, meta)`` with ``meta`` carrying ``n_strips``,
    ``duration_s``, ``lead``. Raises :class:`SmartwatchDigitizeError` on
    expected bad input (no trace / no strips).
    """
    rgb = _extract_page_image(input_path)
    mask = _red_mask(rgb)
    if mask.sum() < _MIN_TRACE_FRAC * mask.size:
        raise SmartwatchDigitizeError(
            'No red ECG trace found in the PDF. This expects a single-lead '
            'smartwatch ECG export (a red waveform on a light grid).',
            'NoTraceFound')

    bands = _find_strip_bands(mask)
    if not bands:
        raise SmartwatchDigitizeError('Could not locate the ECG strips in the image.',
                                      'NoStripsFound')

    per_strip = int(TARGET_FS * STRIP_SECONDS)
    segments = [_trace_band(mask, y0, y1) for (y0, y1) in bands]
    signal = np.concatenate([_resample(s, per_strip) for s in segments])
    meta = {
        'n_strips': len(bands),
        'duration_s': float(len(bands) * STRIP_SECONDS),
        'lead': LEAD_NAME,
    }
    return signal.astype(float), TARGET_FS, meta


def preview(signal: np.ndarray, max_points: int = 1200) -> list[float]:
    """Downsample the signal to a light list for a frontend trace sparkline."""
    sig = np.asarray(signal, dtype=float)
    step = max(1, sig.size // max_points)
    return [round(float(v), 4) for v in sig[::step]]


# ---- single-lead rate/rhythm screening ------------------------------------

def _compute(signal: np.ndarray, fs: int) -> dict:
    """Rate/rhythm/HRV from the single lead (NeuroKit2). Never raises."""
    out = {'hr': None, 'cls': 'N/A', 'rhythm': 'Undetermined', 'n_beats': 0,
           'rmssd': None, 'sdnn': None, 'pnn50': None,
           'rpeaks': np.array([], dtype=int)}
    try:
        import neurokit2 as nk
        clean = nk.ecg_clean(np.asarray(signal, dtype=float), sampling_rate=fs)
        _, info = nk.ecg_peaks(clean, sampling_rate=fs)
        rp = np.asarray(info.get('ECG_R_Peaks', []), dtype=int)
        out['rpeaks'] = rp
        out['n_beats'] = int(rp.size)
        if rp.size > 2:
            rr = np.diff(rp) / fs            # seconds
            hr = float(np.mean(60.0 / rr))
            out['hr'] = round(hr, 1)
            out['cls'] = ('Bradycardia' if hr < 60 else
                          'Tachycardia' if hr > 100 else 'Normal')
            rr_ms = rr * 1000.0
            out['rmssd'] = round(float(np.sqrt(np.mean(np.diff(rr_ms) ** 2))), 1)
            out['sdnn'] = round(float(np.std(rr_ms)), 1)
            out['pnn50'] = round(float(np.mean(np.abs(np.diff(rr_ms)) > 50) * 100), 1)
            cv = float(np.std(rr) / np.mean(rr)) if np.mean(rr) else 0.0
            out['rhythm'] = 'Irregular' if cv > 0.15 else 'Regular'
    except Exception as e:  # screening is best-effort
        logger.warning("smartwatch screening failed: %s", e)
    return out


def screen(signal: np.ndarray, fs: int) -> dict:
    """Convert-page-shaped screening dict (HR + rhythm + RMSSD/SDNN)."""
    c = _compute(signal, fs)
    return {
        'mean_hr_bpm': c['hr'],
        'hr_classification': c['cls'],
        'rhythm': c['rhythm'],
        'n_beats': c['n_beats'],
        'hrv_rmssd_ms': c['rmssd'],
        'hrv_sdnn_ms': c['sdnn'],
    }


# ---- full saved-analysis pipeline (matches analyze_ecg's envelope) ---------

def _render_lead_plot(signal, fs, rpeaks, title):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(14, 3.5))
    t_axis = np.arange(signal.shape[0]) / fs
    ax.plot(t_axis, signal, linewidth=0.6, color='crimson')
    rp = np.asarray(rpeaks)
    rp = rp[rp < signal.shape[0]]
    if rp.size:
        ax.plot(t_axis[rp], signal[rp], 'k.', markersize=5)
    ax.set_ylabel('Lead I')
    ax.set_xlabel('Time (s)')
    ax.grid(True, alpha=0.3)
    fig.suptitle(title)
    fig.tight_layout()
    return fig


def analyze_smartwatch_ecg(file_path: str) -> dict:
    """Digitize + screen a smartwatch ECG PDF into the standard ECG envelope.

    Returns ``{status:'success', ...}`` shaped like analyze_ecg (heart_rate_bpm,
    hr_classification, hrv_metrics, additional_flags, plot_path, report,
    models_used) but with ``all_pathology_probabilities=None`` — single lead,
    rate/rhythm screening only. On error returns the failed envelope; never
    raises into the view (Contract 2).
    """
    from .utils import save_visualization

    t0 = time.time()
    try:
        signal, fs, dig = digitize(file_path)
        c = _compute(signal, fs)

        hr = c['hr']
        rhythm = c['rhythm']
        irregular = rhythm == 'Irregular'
        diagnosis = f'Single-lead screening — {rhythm} rhythm'
        if hr is not None:
            diagnosis += f', {hr:.0f} bpm'

        flags = ['Single-lead (Lead I) smartwatch ECG — rate/rhythm screening only; '
                 'NOT a 12-lead diagnosis.']
        if irregular:
            flags.append('Irregular rhythm on single lead — confirm with a 12-lead ECG.')
        if c['cls'] == 'Bradycardia':
            flags.append('Rule-based: Bradycardia (HR < 60).')
        elif c['cls'] == 'Tachycardia':
            flags.append('Rule-based: Tachycardia (HR > 100).')

        os.makedirs(ECG_RESULTS_DIR, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fig = _render_lead_plot(signal, fs, c['rpeaks'],
                                f'Smartwatch Lead I — {diagnosis}')
        plot_path = save_visualization(fig, ECG_RESULTS_DIR, f"{timestamp}_smartwatch.png")
        import matplotlib.pyplot as plt
        plt.close(fig)

        report = f"""
SINGLE-LEAD (LEAD I) SMARTWATCH ECG — SCREENING
Generated: {timestamp}

This is a CONSUMER smartwatch ECG: one lead (Lead I), digitized from the PDF
trace. It supports heart-rate and rhythm screening ONLY — not a 12-lead
diagnosis. No pathology classification (RBBB/LBBB/AFIB/...) is performed, because
a single lead cannot support it.

RHYTHM (single-lead): {rhythm}
HEART RATE: {('%.0f bpm (%s)' % (hr, c['cls'])) if hr is not None else 'N/A'}
BEATS DETECTED: {c['n_beats']}

HEART RATE VARIABILITY:
  RMSSD: {c['rmssd']} ms
  SDNN:  {c['sdnn']} ms
  pNN50: {c['pnn50']} %

NOTES:
{chr(10).join('  - ' + f for f in flags)}

DISCLAIMER: AI-assisted single-lead screening. For any diagnosis, acquire a
clinical 12-lead ECG. Clinical decisions must be made by a qualified cardiologist.
""".strip()

        elapsed = time.time() - t0
        return {
            'status': 'success',
            'arrhythmia_detected': bool(irregular),
            'diagnosis': diagnosis,
            'diagnosis_confidence': None,
            'all_pathology_probabilities': None,
            'heart_rate_bpm': hr,
            'hr_classification': c['cls'],
            'hrv_metrics': {
                'RMSSD_ms': c['rmssd'],
                'SDNN_ms': c['sdnn'],
                'pNN50_percent': c['pnn50'],
                'rhythm': rhythm,
                'single_lead': True,
                'lead': LEAD_NAME,
            },
            'additional_flags': flags,
            'single_lead': True,
            'plot_path': plot_path,
            'report': report,
            'models_used': ['Smartwatch single-lead (Lead I) — NeuroKit2 rate/rhythm'],
            'timestamp': timestamp,
            'elapsed_seconds': elapsed,
        }
    except Exception as e:
        logger.exception("analyze_smartwatch_ecg failed")
        error_type = getattr(e, 'error_type', type(e).__name__)
        return {'status': 'failed', 'error': str(e), 'error_type': error_type}
