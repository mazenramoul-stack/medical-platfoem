"""Shared helpers for the modality converters.

Each converter module exposes ``convert(input_path, **params) -> (output_path, meta)``
and stays a pure function: it reads the input file, writes the standardized
output next to it (same temp working dir, so the view can clean up with one
rmtree), and returns the output path plus a small ``meta`` dict. Converters
raise :class:`ConversionError` for *expected* bad input (unsupported format,
unreadable file, nothing to convert); the view turns that into the structured
``{status: 'failed', error, error_type}`` envelope instead of a 500.
"""

from __future__ import annotations

import os
import zipfile

import numpy as np


class ConversionError(Exception):
    """Expected, user-facing conversion failure.

    Carries an ``error_type`` so the view can surface a clean error envelope
    (mirroring the inference pipelines' result-envelope contract) rather than
    letting an exception escape into a 500.
    """

    def __init__(self, message: str, error_type: str = 'ConversionError'):
        super().__init__(message)
        self.error_type = error_type


def detected_extension(filename: str) -> str:
    """Return a lowercase extension, treating ``.nii.gz`` as one extension."""
    lower = (filename or '').lower()
    if lower.endswith('.nii.gz'):
        return '.nii.gz'
    return os.path.splitext(lower)[1]


def output_path_for(input_path: str, new_ext: str, suffix: str = '_converted') -> str:
    """Build an output path in the same dir as the input, with a new extension."""
    stem = os.path.basename(input_path)
    for ext in ('.nii.gz',):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    else:
        stem = os.path.splitext(stem)[0]
    return os.path.join(os.path.dirname(input_path), f'{stem}{suffix}{new_ext}')


def to_uint8(arr) -> np.ndarray:
    """Min-max normalise an array to an 8-bit grayscale range [0, 255]."""
    a = np.asarray(arr, dtype=np.float32)
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return np.zeros(a.shape, dtype=np.uint8)
    lo, hi = float(finite.min()), float(finite.max())
    if hi <= lo:
        return np.zeros(a.shape, dtype=np.uint8)
    a = np.nan_to_num(a, nan=lo, posinf=hi, neginf=lo)
    return ((a - lo) / (hi - lo) * 255.0).round().astype(np.uint8)


def unzip_to_dir(zip_path: str, dest_dir: str) -> str:
    """Safely extract a zip into ``dest_dir`` (guards against zip-slip)."""
    dest_real = os.path.realpath(dest_dir)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                target = os.path.realpath(os.path.join(dest_dir, member))
                if target != dest_real and not target.startswith(dest_real + os.sep):
                    raise ConversionError(
                        'Zip archive contains an unsafe path.', 'UnsafeZip')
            zf.extractall(dest_dir)
    except zipfile.BadZipFile:
        raise ConversionError('Uploaded file is not a valid .zip archive.', 'BadZip')
    return dest_dir


def find_files(root: str, extensions: set[str]) -> list[str]:
    """Recursively collect files under ``root`` whose extension is in the set."""
    out: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if detected_extension(name) in extensions:
                out.append(os.path.join(dirpath, name))
    return sorted(out)
