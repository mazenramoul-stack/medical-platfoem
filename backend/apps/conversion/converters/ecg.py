"""ECG converter:
    * DICOM ECG waveform (.dcm) -> 12-lead .csv at 500 Hz, OR
    * smartwatch ECG export (.pdf) -> single-lead (Lead I) .csv at 500 Hz.

DICOM path: extracts the 12-lead samples from a DICOM ``WaveformSequence``, maps
channels to the canonical lead order (deriving III/aVR/aVL/aVF from I & II when an
8-lead acquisition omits them), resamples to the model's 500 Hz, and writes a .csv
the ECG upload page accepts (canonical lead-name headers, which
``apps.inference.utils.load_ecg_signal`` recognises).

PDF path: consumer-watch ECGs (Apple Watch / Samsung / Withings / KardiaMobile)
are a SINGLE lead drawn as a raster image. ``smartwatch_ecg.digitize`` recovers
the Lead I waveform by computer vision; we write it as a one-column ('I') CSV.
This is genuinely single-lead — it can NOT become a 12-lead CSV (the watch only
ever measured one electrical view), so it is a data export, not something the
12-lead pathology models will accept (they correctly refuse a reduced lead set).

Any other input returns a clean, friendly error. Heavy libs (pydicom, pandas,
scipy, PyMuPDF) are imported lazily.
"""

from __future__ import annotations

import os

import numpy as np

from apps.inference import smartwatch_ecg
from apps.inference.smartwatch_ecg import SmartwatchDigitizeError

from .base import ConversionError, detected_extension, output_path_for

LEAD_NAMES = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
TARGET_FS = 500  # the ecglib DenseNet-1D models expect 500 Hz


def convert(input_path, **params):
    ext = detected_extension(input_path)
    if ext == '.pdf':
        return _convert_smartwatch_pdf(input_path)
    if ext != '.dcm':
        raise ConversionError(
            'Unsupported ECG source format: DICOM ECG waveforms (.dcm) and '
            'single-lead smartwatch ECG exports (.pdf) are supported. Vendor '
            'XML/SCP exports and scanned 12-lead paper printouts are not.',
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


def _convert_smartwatch_pdf(input_path):
    """Digitize a single-lead smartwatch ECG PDF into a one-column ('I') CSV.

    Unlike the file-only conversions, this also runs a single-lead rate/rhythm
    screening and a trace preview, surfaced inline on the Convert page (the view
    returns JSON when ``inline_result`` is set, instead of a bare file download).
    """
    try:
        signal, fs, dig_meta = smartwatch_ecg.digitize(input_path)
    except SmartwatchDigitizeError as e:
        # Map the inference-layer error to the conversion envelope (clean 422).
        raise ConversionError(str(e), e.error_type)

    import pandas as pd
    df = pd.DataFrame({smartwatch_ecg.LEAD_NAME: signal})
    out_path = output_path_for(input_path, '.csv', suffix='_leadI')
    df.to_csv(out_path, index=False)

    meta = {
        'content_type': 'text/csv',
        'filename': os.path.basename(out_path),
        'modality': 'ecg',
        'source_format': 'smartwatch_pdf',
        'output_sampling_hz': fs,
        'n_samples': int(signal.shape[0]),
        'leads_present': [dig_meta['lead']],
        'single_lead': True,
        'lead': dig_meta['lead'],
        'n_strips': dig_meta['n_strips'],
        'duration_s': dig_meta['duration_s'],
        # Inline result: the view returns JSON (screening + preview + CSV text)
        # rather than a file download, so the Convert page can show a result.
        'inline_result': True,
        'screening': smartwatch_ecg.screen(signal, fs),
        'signal_preview': smartwatch_ecg.preview(signal),
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
