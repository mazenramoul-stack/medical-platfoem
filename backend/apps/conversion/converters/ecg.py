"""ECG converter: DICOM ECG waveform (.dcm) -> 12-lead .csv at 500 Hz.

Extracts the 12-lead samples from a DICOM ``WaveformSequence``, maps channels to
the canonical lead order (deriving III/aVR/aVL/aVF from I & II when an 8-lead
acquisition omits them), resamples to the model's 500 Hz, and writes a .csv the
ECG upload page accepts (column headers are the canonical lead names, which
``apps.inference.utils.load_ecg_signal`` recognises).

DICOM is the only supported source today. The module is structured so a vendor
XML / SCP parser can be added later (a new ``_read_*`` branch), but any other
input returns a clean, friendly error — scanned paper-printout digitisation is
explicitly out of scope. Heavy libs (pydicom, pandas, scipy) are imported lazily.
"""

from __future__ import annotations

import os

import numpy as np

from .base import ConversionError, detected_extension, output_path_for

LEAD_NAMES = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
TARGET_FS = 500  # the ecglib DenseNet-1D models expect 500 Hz


def convert(input_path, **params):
    ext = detected_extension(input_path)
    if ext != '.dcm':
        raise ConversionError(
            'Unsupported ECG source format: only DICOM ECG waveforms (.dcm) are '
            'supported. Vendor XML/SCP exports and scanned paper printouts are '
            'not yet supported.',
            'UnsupportedFormat')

    leads, fs = _read_dicom_ecg(input_path)
    table, n_samples = _assemble_12_lead(leads, fs)

    import pandas as pd
    df = pd.DataFrame({name: table[name] for name in LEAD_NAMES})
    out_path = output_path_for(input_path, '.csv')
    df.to_csv(out_path, index=False)

    meta = {
        'content_type': 'text/csv',
        'filename': os.path.basename(out_path),
        'modality': 'ecg',
        'source_format': 'dicom',
        'source_sampling_hz': fs,
        'output_sampling_hz': TARGET_FS,
        'n_samples': n_samples,
        'leads_present': sorted(leads.keys()),
    }
    return out_path, meta


# --- helpers ---------------------------------------------------------------

def _canon_lead(name) -> str:
    """Normalise an ECG channel label to a canonical lead token, or '' if unknown.

    Handles 'Lead II', 'II', 'AVR'->'aVR', 'V1', 'ECG V6', 'MLII'->'II', etc.
    Mirrors apps.inference.utils._canon_lead so the CSV round-trips.
    """
    s = str(name).upper()
    s = s.replace('LEAD', '').replace('ECG', '')
    s = ''.join(ch for ch in s if ch.isalnum())
    if not s:
        return ''
    aliases = {'MLII': 'II', 'MLI': 'I', 'AVR': 'aVR', 'AVL': 'aVL', 'AVF': 'aVF'}
    if s in aliases:
        return aliases[s]
    for lead in LEAD_NAMES:
        if s == lead.upper():
            return lead
    return ''


def _channel_labels(wf):
    labels = []
    for ch in getattr(wf, 'ChannelDefinitionSequence', []):
        label = ''
        src = getattr(ch, 'ChannelSourceSequence', None)
        if src and len(src) > 0:
            label = getattr(src[0], 'CodeMeaning', '') or ''
        if not label:
            label = getattr(ch, 'ChannelLabel', '') or ''
        labels.append(label)
    return labels


def _read_dicom_ecg(path):
    import pydicom

    ds = pydicom.dcmread(path)
    if 'WaveformSequence' not in ds or len(ds.WaveformSequence) == 0:
        raise ConversionError(
            'DICOM file has no WaveformSequence — it is not an ECG waveform '
            '(an ECG image/screenshot DICOM cannot be digitised here).',
            'NoWaveform')
    wf = ds.WaveformSequence[0]
    fs = float(getattr(wf, 'SamplingFrequency', 0) or 0)
    if fs <= 0:
        raise ConversionError('ECG waveform has no SamplingFrequency.', 'NoSamplingFrequency')

    try:
        arr = ds.waveform_array(0)  # (samples, channels), scaling applied
    except Exception as e:
        raise ConversionError(f'Could not decode the ECG waveform data: {e}',
                              'UnreadableWaveform')
    arr = np.asarray(arr, dtype=np.float64)
    if arr.ndim != 2:
        raise ConversionError(f'Unexpected waveform shape: {arr.shape}.', 'BadWaveform')

    labels = _channel_labels(wf)
    leads = {}
    for i in range(arr.shape[1]):
        label = labels[i] if i < len(labels) else ''
        canon = _canon_lead(label)
        if canon and canon not in leads:
            leads[canon] = arr[:, i]

    if not leads:
        # No usable labels — fall back to positional canonical order.
        for i in range(min(arr.shape[1], 12)):
            leads[LEAD_NAMES[i]] = arr[:, i]
    return leads, fs


def _assemble_12_lead(leads, fs):
    leads = dict(leads)

    # Derive the limb/augmented leads from I & II when an 8-lead acquisition
    # omits them (standard ECG arithmetic; the precordials + I + II are the
    # independent leads).
    if 'I' in leads and 'II' in leads:
        lead_i, lead_ii = leads['I'], leads['II']
        lead_iii = lead_ii - lead_i
        derived = {
            'III': lead_iii,
            'aVR': -(lead_i + lead_ii) / 2.0,
            'aVL': (lead_i - lead_iii) / 2.0,
            'aVF': (lead_ii + lead_iii) / 2.0,
        }
        for name, signal in derived.items():
            leads.setdefault(name, signal)

    n_native = max(len(v) for v in leads.values())
    if abs(fs - TARGET_FS) > 1e-6:
        new_n = int(round(n_native * TARGET_FS / fs))
        from scipy.signal import resample
        def _to_target(sig):
            return resample(sig, new_n)
    else:
        new_n = n_native
        def _to_target(sig):
            return sig

    out = {}
    for name in LEAD_NAMES:
        sig = leads.get(name)
        if sig is None:
            out[name] = np.zeros(new_n, dtype=np.float64)
        else:
            sig = np.asarray(sig, dtype=np.float64)
            out[name] = sig if len(sig) == new_n else _to_target(sig)
    return out, new_n
