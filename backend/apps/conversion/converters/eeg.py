"""EEG converter: non-EDF clinical formats -> .edf.

Reads BrainVision (.vhdr+.eeg[+.vmrk]), BioSemi (.bdf) or EEGLAB (.set) via
mne.io.read_raw_* and exports an EDF (the EEG upload page accepts .edf) through
mne's edfio-backed exporter. Multi-file formats (BrainVision, an EEGLAB
.set/.fdt pair) arrive as a single uploaded .zip. Heavy libs (mne) are imported
lazily.
"""

from __future__ import annotations

import os

from .base import ConversionError, detected_extension, find_files, output_path_for, unzip_to_dir


def convert(input_path, **params):
    ext = detected_extension(input_path)

    if ext == '.zip':
        extract_dir = os.path.join(os.path.dirname(input_path), '_eeg_extract')
        os.makedirs(extract_dir, exist_ok=True)
        unzip_to_dir(input_path, extract_dir)
        raw, source = _read_any_eeg(extract_dir)
    elif ext == '.bdf':
        raw, source = _read('bdf', input_path), 'bdf'
    elif ext == '.vhdr':
        raw, source = _read('brainvision', input_path), 'brainvision'
    elif ext == '.set':
        raw, source = _read('eeglab', input_path), 'eeglab'
    else:
        raise ConversionError(
            f'Unsupported EEG source format: {ext or "(none)"}. Supported: '
            f'BrainVision (.vhdr+.eeg, as .zip), BioSemi (.bdf), EEGLAB (.set), '
            f'or their multi-file sets uploaded as a .zip.',
            'UnsupportedFormat')

    out_path = output_path_for(input_path, '.edf')
    try:
        raw.export(out_path, fmt='edf', overwrite=True, verbose='ERROR')
    except Exception as e:
        raise ConversionError(f'Could not export EDF: {e}', 'EdfExport')

    n_times = int(getattr(raw, 'n_times', 0) or 0)
    meta = {
        'content_type': 'application/octet-stream',
        'filename': os.path.basename(out_path),
        'modality': 'eeg',
        'source_format': source,
        'n_channels': len(raw.ch_names),
        'sfreq': float(raw.info['sfreq']),
        'duration_s': float(n_times / raw.info['sfreq']) if raw.info['sfreq'] else 0.0,
    }
    return out_path, meta


# --- helpers ---------------------------------------------------------------

def _read(kind, path):
    import mne

    readers = {
        'bdf': mne.io.read_raw_bdf,
        'brainvision': mne.io.read_raw_brainvision,
        'eeglab': mne.io.read_raw_eeglab,
    }
    try:
        return readers[kind](path, preload=True, verbose='ERROR')
    except ConversionError:
        raise
    except Exception as e:
        raise ConversionError(f'Could not read the {kind} file: {e}', 'UnreadableInput')


def _read_any_eeg(root):
    vhdr = find_files(root, {'.vhdr'})
    if vhdr:
        return _read('brainvision', vhdr[0]), 'brainvision'
    bdf = find_files(root, {'.bdf'})
    if bdf:
        return _read('bdf', bdf[0]), 'bdf'
    sett = find_files(root, {'.set'})
    if sett:
        return _read('eeglab', sett[0]), 'eeglab'
    raise ConversionError(
        'No BrainVision (.vhdr), BioSemi (.bdf) or EEGLAB (.set) file found in '
        'the archive.', 'NoEEG')
