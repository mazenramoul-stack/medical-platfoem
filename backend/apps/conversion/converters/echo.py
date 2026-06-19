"""Echo converter: DICOM ultrasound cine (multiframe) or a video file -> .mp4.

Extracts frames (pydicom for DICOM, opencv for .mov/.mkv/... ) and re-encodes
them to an .mp4 the Echo upload page accepts. Heavy libs (pydicom, cv2) are
imported lazily.
"""

from __future__ import annotations

import os

import numpy as np

from .base import ConversionError, detected_extension, output_path_for, to_uint8

_VIDEO_EXTS = {'.mp4', '.mov', '.mkv', '.avi', '.webm'}


def convert(input_path, fps=None, **params):
    ext = detected_extension(input_path)
    if ext == '.dcm':
        frames, src_fps = _frames_from_dicom(input_path)
        source = 'dicom'
    elif ext in _VIDEO_EXTS:
        frames, src_fps = _frames_from_video(input_path)
        source = 'video'
    else:
        raise ConversionError(
            f'Unsupported echo source format: {ext or "(none)"}. Supported: a '
            f'DICOM ultrasound cine (.dcm) or a video file '
            f'({", ".join(sorted(_VIDEO_EXTS))}).',
            'UnsupportedFormat')

    if not frames:
        raise ConversionError('No frames could be extracted from the input.', 'NoFrames')

    out_fps = _parse_fps(fps) or src_fps or 30.0
    out_path = output_path_for(input_path, '.mp4')
    height, width = frames[0].shape[:2]
    _write_mp4(frames, out_path, out_fps)

    meta = {
        'content_type': 'video/mp4',
        'filename': os.path.basename(out_path),
        'modality': 'echo',
        'source_format': source,
        'n_frames': len(frames),
        'fps': out_fps,
        'width': int(width),
        'height': int(height),
    }
    return out_path, meta


# --- helpers ---------------------------------------------------------------

def _parse_fps(fps):
    if fps in (None, ''):
        return None
    try:
        v = float(fps)
        return v if v > 0 else None
    except (TypeError, ValueError):
        raise ConversionError(f'fps must be a positive number, got {fps!r}.', 'BadParam')


def _frames_from_dicom(path):
    import pydicom

    ds = pydicom.dcmread(path)
    if not hasattr(ds, 'PixelData'):
        raise ConversionError('DICOM file has no pixel data.', 'NoFrames')
    arr = ds.pixel_array
    photometric = str(getattr(ds, 'PhotometricInterpretation', '')).upper()
    if photometric.startswith('YBR'):
        try:
            from pydicom.pixel_data_handlers.util import convert_color_space
            arr = convert_color_space(arr, photometric, 'RGB')
        except Exception:
            pass  # fall through; treat as-is
    frames = _to_frame_list(arr)
    return frames, _dicom_fps(ds)


def _to_frame_list(arr):
    arr = np.asarray(arr)
    if arr.ndim == 2:
        return [arr]
    if arr.ndim == 3:
        if arr.shape[-1] in (3, 4) and arr.shape[0] not in (3, 4):
            return [arr[..., :3]]            # single colour frame
        return [arr[i] for i in range(arr.shape[0])]  # multiframe grayscale
    if arr.ndim == 4:
        return [arr[i, ..., :3] for i in range(arr.shape[0])]  # multiframe colour
    raise ConversionError(f'Unsupported echo pixel array shape: {arr.shape}.', 'BadFrames')


def _dicom_fps(ds):
    for attr in ('CineRate', 'RecommendedDisplayFrameRate'):
        v = getattr(ds, attr, None)
        if v:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    frame_time = getattr(ds, 'FrameTime', None)  # ms per frame
    if frame_time:
        try:
            return 1000.0 / float(frame_time)
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return None


def _frames_from_video(path):
    import cv2

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ConversionError('Could not open the uploaded video file.', 'BadVideo')
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frames = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))  # store RGB
    cap.release()
    if not frames:
        raise ConversionError('No frames could be read from the video.', 'NoFrames')
    return frames, (fps if fps > 0 else None)


def _to_bgr_uint8(frame):
    import cv2

    frame = np.asarray(frame)
    if frame.ndim == 2:
        return cv2.cvtColor(to_uint8(frame), cv2.COLOR_GRAY2BGR)
    rgb = frame[..., :3]
    if rgb.dtype != np.uint8:
        rgb = to_uint8(rgb)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _write_mp4(frames, out_path, fps):
    import cv2

    height, width = frames[0].shape[:2]
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(out_path, fourcc, float(fps), (int(width), int(height)), True)
    if not writer.isOpened():
        raise ConversionError(
            'Could not open an mp4 video writer (codec unavailable).', 'VideoWriter')
    try:
        for frame in frames:
            bgr = _to_bgr_uint8(frame)
            if bgr.shape[0] != height or bgr.shape[1] != width:
                bgr = cv2.resize(bgr, (int(width), int(height)))
            writer.write(bgr)
    finally:
        writer.release()
    if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise ConversionError('mp4 encoding produced no output.', 'VideoWriter')
