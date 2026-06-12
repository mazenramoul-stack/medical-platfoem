"""Input-loading and visualization helpers shared by both pipelines."""

from __future__ import annotations

import datetime
import logging
import os

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


# -- Image loading ---------------------------------------------------------

def load_image_universal(file_path: str) -> np.ndarray:
    """Load a medical image into an (H, W, 3) uint8 RGB array.

    Supported formats:
        * Standard: .png, .jpg, .jpeg, .bmp, .tif, .tiff (via PIL)
        * DICOM:    .dcm (via pydicom; intensities min-max normalised to 0-255)
        * NIfTI:    .nii / .nii.gz (via nibabel; middle axial slice taken)

    Single-channel inputs are broadcast to 3 channels so that ImageNet-style
    networks (U-Net, ViT) can consume them without further changes.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if file_path.lower().endswith('.nii.gz'):
        ext = '.nii.gz'

    if ext in ('.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff'):
        img = Image.open(file_path).convert('RGB')
        return np.array(img, dtype=np.uint8)

    if ext == '.dcm':
        import pydicom
        ds = pydicom.dcmread(file_path)
        arr = ds.pixel_array.astype(np.float32)
        arr = (arr - arr.min()) / (arr.max() - arr.min() + 1e-8) * 255.0
        arr = arr.astype(np.uint8)
        if arr.ndim == 2:
            arr = np.stack([arr] * 3, axis=-1)
        elif arr.ndim == 3 and arr.shape[-1] != 3:
            # Multi-slice DICOM: take middle slice
            mid = arr.shape[0] // 2
            arr = np.stack([arr[mid]] * 3, axis=-1)
        return arr

    if ext in ('.nii', '.nii.gz'):
        import nibabel as nib
        nii = nib.load(file_path)
        data = nii.get_fdata()
        if data.ndim == 3:
            slc = data[:, :, data.shape[2] // 2]
        elif data.ndim == 4:
            slc = data[:, :, data.shape[2] // 2, 0]
        else:
            slc = data
        slc = (slc - slc.min()) / (slc.max() - slc.min() + 1e-8) * 255.0
        slc = slc.astype(np.uint8)
        return np.stack([slc] * 3, axis=-1)

    raise ValueError(f"Unsupported image format: {ext} ({file_path})")


# -- ECG loading -----------------------------------------------------------

# Canonical 12-lead order the ecglib DenseNet-1D models expect (positional).
_CANONICAL_LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF',
                    'V1', 'V2', 'V3', 'V4', 'V5', 'V6']


def _canon_lead(name) -> str:
    """Normalise an ECG channel label to a canonical lead token, or '' if unknown.

    Handles 'Lead II', 'II', 'AVR', 'aVR', 'V1', 'ECG V6', 'MLII'->'II', etc.
    """
    s = str(name).upper()
    s = s.replace('LEAD', '').replace('ECG', '')
    s = ''.join(ch for ch in s if ch.isalnum())
    if not s:
        return ''
    aliases = {'MLII': 'II', 'MLI': 'I', 'AVR': 'aVR', 'AVL': 'aVL', 'AVF': 'aVF'}
    if s in aliases:
        return aliases[s]
    for lead in _CANONICAL_LEADS:
        if s == lead.upper():
            return lead
    return ''


def _reorder_to_canonical(sig: np.ndarray, labels) -> tuple[np.ndarray, bool, bool]:
    """Reorder rows of `sig` to canonical 12-lead order using `labels`.

    Returns (reordered_signal, did_reorder, all_leads_recognized). If labels are
    missing/unrecognised the signal is returned unchanged (positional fallback).
    """
    if not labels or len(labels) != sig.shape[0]:
        return sig, False, False
    canon = [_canon_lead(l) for l in labels]
    found = {c: i for i, c in enumerate(canon) if c}
    recognized = [lead for lead in _CANONICAL_LEADS if lead in found]
    if len(recognized) < 8:
        # Too few recognisable labels to trust a remap — keep positional order.
        return sig, False, False
    rows = [sig[found[lead]] if lead in found else np.zeros(sig.shape[1], dtype=sig.dtype)
            for lead in _CANONICAL_LEADS]
    all_recognized = len(recognized) == 12
    return np.asarray(rows, dtype=sig.dtype), True, all_recognized


def load_ecg_signal(file_path: str) -> tuple[np.ndarray, float, dict]:
    """Load a 12-lead ECG into a (12, 5000) float32 array at 500 Hz.

    Supported formats:
        * .csv         numeric columns interpreted as leads (pandas)
        * .edf         (pyedflib.highlevel.read_edf)
        * .dat / .hea  WFDB record (wfdb.rdrecord on the base name)

    When channel labels are present (CSV headers, EDF/WFDB signal names) the leads
    are reordered to the canonical I, II, III, aVR…V6 order the models expect. When
    labels are absent the channels are consumed POSITIONALLY (the historical
    behaviour) and that fact is reported back so the caller can flag it.

    Returns ``(signal, fs, quality)`` where ``quality`` is a dict describing how
    trustworthy the lead mapping is:
        n_leads_detected     int   — genuine channels found in the file
        reordered_by_label   bool  — rows were remapped to canonical order
        all_leads_recognized bool  — all 12 standard leads were identified by name
        positional_fallback  bool  — labels unusable; channels used by position
        padded_from_fewer    bool  — <12 leads present; lead I broadcast to fill
        truncated            bool  — >12 channels present; extras dropped
        warnings             list[str]
    """
    target_fs = 500
    target_samples = 5000
    ext = os.path.splitext(file_path)[1].lower()
    labels = None

    if ext == '.csv':
        import pandas as pd
        df = pd.read_csv(file_path)
        numeric = df.select_dtypes(include=[np.number])
        sig = numeric.values.T  # (channels, N)
        labels = list(numeric.columns)
        fs = float(target_fs)

    elif ext == '.edf':
        from pyedflib import highlevel
        sigs, sig_headers, _ = highlevel.read_edf(file_path)
        sig = np.array(sigs)
        labels = [h.get('label', '') for h in sig_headers]
        fs = float(sig_headers[0]['sample_rate'])

    elif ext in ('.dat', '.hea'):
        import wfdb
        base = os.path.splitext(file_path)[0]
        record = wfdb.rdrecord(base)
        sig = record.p_signal.T
        labels = list(record.sig_name) if record.sig_name else None
        fs = float(record.fs)

    else:
        raise ValueError(f"Unsupported ECG format: {ext} ({file_path})")

    n_detected = int(sig.shape[0])
    quality = {
        'n_leads_detected': n_detected,
        'reordered_by_label': False,
        'all_leads_recognized': False,
        'positional_fallback': False,
        'padded_from_fewer': False,
        'truncated': False,
        'warnings': [],
    }

    # Lead-order normalisation by label, with positional fallback ----------------
    try:
        sig, did_reorder, all_ok = _reorder_to_canonical(sig, labels)
    except Exception as e:  # never let label parsing break the load
        logger.warning("ECG lead reorder failed (%s) — using positional order", e)
        did_reorder, all_ok = False, False
    quality['reordered_by_label'] = did_reorder
    quality['all_leads_recognized'] = all_ok
    if not did_reorder:
        quality['positional_fallback'] = True
        quality['warnings'].append(
            'ECG channels consumed by position (no usable lead labels); a wrong '
            'source lead order would yield incorrect pathology predictions.')
    elif not all_ok:
        quality['warnings'].append(
            'Some standard leads were not identified by name; missing leads were '
            'zero-filled.')

    # Channel count normalisation -------------------------------------------------
    if sig.shape[0] < 12:
        quality['padded_from_fewer'] = True
        quality['warnings'].append(
            f'Only {n_detected} lead(s) present; lead I broadcast to 12 — this is a '
            f'REDUCED lead set and pathology results are unreliable.')
        logger.warning("ECG has %d lead(s); broadcasting lead I to 12", n_detected)
        sig = np.tile(sig[:1], (12, 1))
    elif sig.shape[0] > 12:
        quality['truncated'] = True
        sig = sig[:12]

    # Resampling -----------------------------------------------------------------
    if abs(fs - target_fs) > 1e-3:
        from scipy.signal import resample
        new_n = int(round(sig.shape[1] * target_fs / fs))
        sig = resample(sig, new_n, axis=1)
        fs = float(target_fs)

    # Length normalisation -------------------------------------------------------
    n = sig.shape[1]
    if n < target_samples:
        sig = np.pad(sig, ((0, 0), (0, target_samples - n)), mode='constant')
    elif n > target_samples:
        sig = sig[:, :target_samples]

    return sig.astype(np.float32), fs, quality


# -- Visualisation helpers -------------------------------------------------

def generate_unique_filename(original_name: str, suffix: str = "") -> str:
    """Build a timestamped filename like '20251215_143022_brain_overlay.png'."""
    base = os.path.splitext(os.path.basename(original_name))[0]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{base}_{suffix}.png" if suffix else f"{ts}_{base}.png"


def save_visualization(figure, output_dir: str, filename: str) -> str:
    """Save a matplotlib figure to {output_dir}/{filename} and return the path."""
    os.makedirs(output_dir, exist_ok=True)
    full_path = os.path.join(output_dir, filename)
    figure.savefig(full_path, dpi=100, bbox_inches='tight')
    logger.info("Saved visualisation: %s", full_path)
    return full_path
