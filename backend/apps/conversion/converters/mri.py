"""MRI converter: DICOM (single / series .zip) or NIfTI volume -> 8-bit PNG.

Selects a 2D slice (middle by default, or the ``slice_index`` param), min-max
normalises it to 8-bit grayscale, and writes a .png the MRI upload page accepts.
Heavy libs (pydicom, nibabel, PIL) are imported lazily so the app loads without
them at Django startup.
"""

from __future__ import annotations

import os

import numpy as np

from .base import (
    ConversionError,
    detected_extension,
    find_files,
    output_path_for,
    to_uint8,
    unzip_to_dir,
)


def convert(input_path, slice_index=None, **params):
    ext = detected_extension(input_path)
    si = _parse_slice_index(slice_index)

    if ext in ('.nii', '.nii.gz'):
        slice2d, n_slices, used = _slice_from_nifti(input_path, si)
        source = 'nifti'
    elif ext == '.dcm':
        slice2d, n_slices, used = _slice_from_dicom_file(input_path, si)
        source = 'dicom'
    elif ext == '.zip':
        slice2d, n_slices, used = _slice_from_dicom_zip(input_path, si)
        source = 'dicom-series'
    else:
        raise ConversionError(
            f'Unsupported MRI source format: {ext or "(none)"}. Supported: '
            f'DICOM (.dcm or a .zip of a DICOM series) and NIfTI (.nii/.nii.gz).',
            'UnsupportedFormat')

    from PIL import Image
    img8 = to_uint8(slice2d)
    if img8.ndim != 2:
        img8 = img8[..., 0] if img8.ndim == 3 else img8.reshape(img8.shape[:2])
    out_path = output_path_for(input_path, '.png')
    Image.fromarray(img8, mode='L').save(out_path, format='PNG')

    meta = {
        'content_type': 'image/png',
        'filename': os.path.basename(out_path),
        'modality': 'mri',
        'source_format': source,
        'slice_index': used,
        'n_slices': n_slices,
    }
    return out_path, meta


# --- helpers ---------------------------------------------------------------

def _parse_slice_index(slice_index):
    if slice_index is None or slice_index == '':
        return None
    try:
        return int(slice_index)
    except (TypeError, ValueError):
        raise ConversionError(f'slice_index must be an integer, got {slice_index!r}.',
                              'BadParam')


def _select(n, si):
    idx = n // 2 if si is None else si
    if not (0 <= idx < n):
        raise ConversionError(
            f'slice_index {idx} is out of range [0, {n - 1}].', 'SliceOutOfRange')
    return idx


def _apply_rescale(ds, arr):
    slope = float(getattr(ds, 'RescaleSlope', 1) or 1)
    intercept = float(getattr(ds, 'RescaleIntercept', 0) or 0)
    return arr * slope + intercept


def _slice_from_nifti(path, si):
    import nibabel as nib

    data = np.asarray(nib.load(path).get_fdata())
    if data.ndim == 4:
        data = data[..., 0]
    if data.ndim == 2:
        return data, 1, 0
    if data.ndim != 3:
        raise ConversionError(
            f'Unsupported NIfTI dimensionality: {data.ndim}D.', 'BadVolume')
    n = data.shape[2]
    idx = _select(n, si)
    return data[:, :, idx], n, idx


def _slice_from_dicom_file(path, si):
    import pydicom

    ds = pydicom.dcmread(path)
    if not hasattr(ds, 'PixelData'):
        raise ConversionError('DICOM file has no pixel data.', 'NoSlices')
    arr = _apply_rescale(ds, ds.pixel_array.astype(np.float32))
    if arr.ndim == 2:
        return arr, 1, 0
    if arr.ndim == 3:
        # (H, W, 3/4) single colour frame vs (frames, H, W) grayscale stack.
        if arr.shape[-1] in (3, 4) and arr.shape[0] not in (3, 4):
            return arr[..., :3].mean(axis=-1), 1, 0
        n = arr.shape[0]
        idx = _select(n, si)
        return arr[idx], n, idx
    raise ConversionError(
        f'Unsupported DICOM pixel array shape: {arr.shape}.', 'BadVolume')


def _slice_from_dicom_zip(path, si):
    import pydicom

    extract_dir = os.path.join(os.path.dirname(path), '_mri_extract')
    os.makedirs(extract_dir, exist_ok=True)
    unzip_to_dir(path, extract_dir)
    candidates = find_files(extract_dir, {'.dcm'})
    if not candidates:
        # Some PACS exports drop the .dcm extension — try every file.
        candidates = find_files(extract_dir, {''}) + [
            os.path.join(dp, f)
            for dp, _d, fs in os.walk(extract_dir) for f in fs
        ]
        candidates = sorted(set(candidates))

    slices = []  # (sort_key, 2d array)
    for p in candidates:
        try:
            ds = pydicom.dcmread(p, force=True)
            if not hasattr(ds, 'PixelData'):
                continue
            arr = _apply_rescale(ds, ds.pixel_array.astype(np.float32))
        except Exception:
            continue
        inst = getattr(ds, 'InstanceNumber', None)
        if arr.ndim == 2:
            slices.append((inst, arr))
        elif arr.ndim == 3 and not (arr.shape[-1] in (3, 4) and arr.shape[0] not in (3, 4)):
            for j, frame in enumerate(arr):
                slices.append((j, frame))

    if not slices:
        raise ConversionError('No DICOM image slices found in the archive.', 'NoSlices')
    if all(s[0] is not None for s in slices):
        slices.sort(key=lambda t: t[0])
    arrays = [a for _key, a in slices]
    n = len(arrays)
    idx = _select(n, si)
    return arrays[idx], n, idx
