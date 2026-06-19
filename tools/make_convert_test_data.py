"""Generate raw clinical sample files for testing the Technician conversion tool.

Writes 5 valid "raw clinic file" inputs per modality into ``convert test/`` at the
repo root (one folder per modality), then runs every file through the matching
converter to prove it converts. A mix of REAL bundled clinical samples (pydicom's
public test data — genuine scanner DICOMs fetched from the pydicom-data repo) and
synthetic-but-valid files for format/parameter variety.

Run from the repo root with the backend venv:

    backend/venv/Scripts/python.exe tools/make_convert_test_data.py

Re-runnable: it overwrites the folder's contents each time. The converter outputs
are written to a temp dir during verification and discarded, so ``convert test/``
holds only the raw inputs (which is what you re-upload through the Convert page).
"""

from __future__ import annotations

import io
import os
import shutil
import sys
import tempfile
import zipfile

import numpy as np

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO_ROOT, 'backend')
OUT_ROOT = os.path.join(REPO_ROOT, 'convert test')
sys.path.insert(0, BACKEND)

CANON_LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']


# --- DICOM builders --------------------------------------------------------

def _mr_dicom_bytes(rows=64, cols=64, seed=0):
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.4'  # MR Image Storage
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.Modality = 'MR'
    ds.Rows, ds.Columns = rows, cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.InstanceNumber = 1
    yy, xx = np.mgrid[0:rows, 0:cols]
    rng = np.random.RandomState(seed)
    blob = np.exp(-((yy - rows / 2) ** 2 + (xx - cols / 2) ** 2) / (2 * (rows / 4) ** 2))
    px = (blob * 3000 + rng.rand(rows, cols) * 200).astype(np.uint16)
    ds.PixelData = px.tobytes()
    ds.is_little_endian, ds.is_implicit_VR = True, False
    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _multiframe_dicom_bytes(frames=16, rows=48, cols=64, rgb=False, modality='US', seed=0):
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.3.1'  # US Multiframe
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.Modality = modality
    ds.Rows, ds.Columns = rows, cols
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.NumberOfFrames = frames
    ds.CineRate = 30
    ds.FrameTime = 1000.0 / 30
    rng = np.random.RandomState(seed)
    yy, xx = np.mgrid[0:rows, 0:cols]
    stack = []
    for f in range(frames):
        r = (rows / 5) * (1 + 0.4 * np.sin(2 * np.pi * f / frames))
        disk = (((yy - rows / 2) ** 2 + (xx - cols / 2) ** 2) < r ** 2) * 200
        frame = (disk + rng.rand(rows, cols) * 40).astype(np.uint8)
        stack.append(frame)
    arr = np.stack(stack, 0)
    if rgb:
        ds.SamplesPerPixel = 3
        ds.PhotometricInterpretation = 'RGB'
        ds.PlanarConfiguration = 0
        arr = np.stack([arr, np.roll(arr, 3, 1), np.roll(arr, 6, 2)], axis=-1)
    else:
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.PixelData = arr.astype(np.uint8).tobytes()
    ds.is_little_endian, ds.is_implicit_VR = True, False
    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _ecg_dicom_bytes(leads, n=2000, fs=500):
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
    ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.9.1.1'  # 12-lead ECG
    ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
    ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
    ds.Modality = 'ECG'
    wf = Dataset()
    wf.WaveformOriginality = 'ORIGINAL'
    wf.NumberOfWaveformChannels = len(leads)
    wf.NumberOfWaveformSamples = n
    wf.SamplingFrequency = fs
    wf.WaveformBitsAllocated = 16
    wf.WaveformSampleInterpretation = 'SS'
    t = np.arange(n) / fs
    # crude but ECG-ish: a periodic R-spike train per lead, scaled per lead.
    beat = np.zeros(n)
    period = int(fs * 0.8)  # ~75 bpm
    beat[:: period] = 1.0
    qrs = np.convolve(beat, np.hanning(max(3, int(fs * 0.06))), mode='same')
    chans, data = [], np.zeros((n, len(leads)), dtype=np.int16)
    for i, name in enumerate(leads):
        ch = Dataset()
        ch.ChannelSensitivity = 1.0
        ch.ChannelSensitivityCorrectionFactor = 1.0
        ch.ChannelBaseline = 0.0
        unit = Dataset()
        unit.CodeValue, unit.CodingSchemeDesignator, unit.CodeMeaning = 'uV', 'UCUM', 'microvolt'
        ch.ChannelSensitivityUnitsSequence = [unit]
        src = Dataset()
        src.CodeValue, src.CodingSchemeDesignator = str(i + 1), 'MDC'
        src.CodeMeaning = 'Lead %s' % name
        ch.ChannelSourceSequence = [src]
        ch.WaveformBitsStored = 16
        chans.append(ch)
        wave = qrs * (800 + 120 * i) + np.sin(2 * np.pi * 1.0 * t) * 40
        data[:, i] = np.clip(wave, -32000, 32000).astype(np.int16)
    wf.ChannelDefinitionSequence = chans
    wf.WaveformData = data.tobytes()
    ds.WaveformSequence = [wf]
    ds.is_little_endian, ds.is_implicit_VR = True, False
    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _dicom_series_zip(n=8, rows=48, cols=48):
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w') as zf:
        for i in range(n):
            ds = Dataset()
            ds.file_meta = FileMetaDataset()
            ds.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
            ds.file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.4'
            ds.file_meta.MediaStorageSOPInstanceUID = generate_uid()
            ds.SOPClassUID = ds.file_meta.MediaStorageSOPClassUID
            ds.SOPInstanceUID = ds.file_meta.MediaStorageSOPInstanceUID
            ds.Modality = 'MR'
            ds.Rows, ds.Columns = rows, cols
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = 'MONOCHROME2'
            ds.BitsAllocated = ds.BitsStored = 16
            ds.HighBit = 15
            ds.PixelRepresentation = 0
            ds.InstanceNumber = i + 1
            yy, xx = np.mgrid[0:rows, 0:cols]
            blob = np.exp(-((yy - rows / 2) ** 2 + (xx - cols / 2) ** 2) / (2 * (6 + i) ** 2))
            ds.PixelData = (blob * 3500).astype(np.uint16).tobytes()
            ds.is_little_endian, ds.is_implicit_VR = True, False
            b = io.BytesIO()
            ds.save_as(b, write_like_original=False)
            zf.writestr('slice_%03d.dcm' % (i + 1), b.getvalue())
    return zbuf.getvalue()


# --- NIfTI -----------------------------------------------------------------

def _nifti_bytes(shape=(48, 48, 20), gz=True):
    import nibabel as nib
    yy, xx, zz = np.mgrid[0:shape[0], 0:shape[1], 0:shape[2]]
    c = np.array(shape) / 2
    blob = np.exp(-((yy - c[0]) ** 2 + (xx - c[1]) ** 2 + (zz - c[2]) ** 2) / (2 * (shape[0] / 4) ** 2))
    vol = (blob * 1000).astype(np.int16)
    img = nib.Nifti1Image(vol, np.eye(4))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'vol.nii.gz' if gz else 'vol.nii')
        nib.save(img, p)
        with open(p, 'rb') as fh:
            return fh.read()


# --- EEG builders ----------------------------------------------------------

def _brainvision_zip_bytes(labels, n_samp=2000, sfreq=250.0, base='eeg'):
    interval_us = int(round(1_000_000 / sfreq))
    ch_lines = '\n'.join('Ch%d=%s,,1,µV' % (i + 1, l) for i, l in enumerate(labels))
    vhdr = (
        'Brain Vision Data Exchange Header File Version 1.0\n\n[Common Infos]\n'
        'Codepage=UTF-8\nDataFile=%s.eeg\nMarkerFile=%s.vmrk\nDataFormat=BINARY\n'
        'DataOrientation=MULTIPLEXED\nNumberOfChannels=%d\nSamplingInterval=%d\n\n'
        '[Binary Infos]\nBinaryFormat=IEEE_FLOAT_32\n\n[Channel Infos]\n%s\n'
        % (base, base, len(labels), interval_us, ch_lines))
    vmrk = (
        'Brain Vision Data Exchange Marker File, Version 1.0\n\n[Common Infos]\n'
        'Codepage=UTF-8\nDataFile=%s.eeg\n\n[Marker Infos]\n'
        'Mk1=New Segment,,1,1,0,00000000000000000000\n' % base)
    t = np.arange(n_samp) / sfreq
    data = np.vstack([np.sin(2 * np.pi * (1 + i % 6) * t) * 20 + np.random.RandomState(i).randn(n_samp)
                      for i in range(len(labels))])
    multiplexed = data.T.astype('<f4').tobytes()
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w') as zf:
        zf.writestr('%s.vhdr' % base, vhdr.encode('utf-8'))
        zf.writestr('%s.vmrk' % base, vmrk.encode('utf-8'))
        zf.writestr('%s.eeg' % base, multiplexed)
    return zbuf.getvalue()


def _eeglab_set_path(path, labels, n=1500, sfreq=256.0):
    import scipy.io as sio
    nch = len(labels)
    t = np.arange(n) / sfreq
    data = np.vstack([np.sin(2 * np.pi * (1 + i % 5) * t) * 25 for i in range(nch)]).astype(np.float32)
    chanlocs = np.zeros((nch,), dtype=[('labels', 'O')])
    for i in range(nch):
        chanlocs[i]['labels'] = labels[i]
    EEG = dict(setname='synthetic', nbchan=nch, pnts=n, trials=1, srate=sfreq,
               xmin=0.0, xmax=(n - 1) / sfreq, data=data, chanlocs=chanlocs,
               icawinv=[], icasphere=[], icaweights=[], ref='common', event=[], epoch=[])
    sio.savemat(path, {'EEG': EEG})


def _write_bdf(path, labels, n_sec=4, sfreq=256.0):
    nch = len(labels)
    sps = int(sfreq)
    nrec = n_sec
    nsamp = nrec * sps
    t = np.arange(nsamp) / sfreq
    data_uv = np.vstack([np.sin(2 * np.pi * (1 + i) * t) * 30 for i in range(nch)])
    pmin, pmax, dmin, dmax = -32768.0, 32767.0, -8388608, 8388607

    def fld(s, w):
        return ('%-*s' % (w, s))[:w].encode('latin-1')

    hdr = b'\xffBIOSEMI'
    hdr += fld('X X X X', 80) + fld('Startdate 01-JAN-2020 X X X', 80)
    hdr += fld('01.01.20', 8) + fld('00.00.00', 8)
    hdr += fld(str(256 + nch * 256), 8) + fld('24BIT', 44)
    hdr += fld(str(nrec), 8) + fld('1', 8) + fld(str(nch), 4)
    hdr += b''.join(fld(l, 16) for l in labels)
    hdr += b''.join(fld('AgAgCl', 80) for _ in range(nch))
    hdr += b''.join(fld('uV', 8) for _ in range(nch))
    hdr += b''.join(fld('%g' % pmin, 8) for _ in range(nch))
    hdr += b''.join(fld('%g' % pmax, 8) for _ in range(nch))
    hdr += b''.join(fld(str(dmin), 8) for _ in range(nch))
    hdr += b''.join(fld(str(dmax), 8) for _ in range(nch))
    hdr += b''.join(fld('', 80) for _ in range(nch))
    hdr += b''.join(fld(str(sps), 8) for _ in range(nch))
    hdr += b''.join(fld('', 32) for _ in range(nch))
    dig = np.clip(np.round((data_uv - pmin) / (pmax - pmin) * (dmax - dmin) + dmin),
                  dmin, dmax).astype(np.int64)
    out = bytearray(hdr)
    for r in range(nrec):
        for c in range(nch):
            for v in dig[c, r * sps:(r + 1) * sps]:
                out += int(v).to_bytes(3, 'little', signed=True)
    with open(path, 'wb') as fh:
        fh.write(out)


# --- video builders --------------------------------------------------------

def _write_video(path, fourcc, frames=24, rows=120, cols=160, fps=20):
    import cv2
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*fourcc), fps, (cols, rows), True)
    if not writer.isOpened():
        raise RuntimeError('VideoWriter failed for %s (%s)' % (path, fourcc))
    yy, xx = np.mgrid[0:rows, 0:cols]
    for f in range(frames):
        r = (rows / 4) * (1 + 0.4 * np.sin(2 * np.pi * f / frames))
        disk = (((yy - rows / 2) ** 2 + (xx - cols / 2) ** 2) < r ** 2).astype(np.uint8) * 220
        bgr = cv2.cvtColor(disk, cv2.COLOR_GRAY2BGR)
        writer.write(bgr)
    writer.release()


# --- real bundled samples --------------------------------------------------

def _copy_real(name, dest):
    from pydicom.data import get_testdata_file
    src = get_testdata_file(name)
    shutil.copyfile(src, dest)


# --- orchestration ---------------------------------------------------------

def _w(path, data):
    with open(path, 'wb') as fh:
        fh.write(data)


def build():
    if os.path.isdir(OUT_ROOT):
        shutil.rmtree(OUT_ROOT)
    plan = {}  # modality -> [(filename, params)]
    for mod in ('mri', 'ecg', 'echo', 'eeg'):
        os.makedirs(os.path.join(OUT_ROOT, mod), exist_ok=True)

    # MRI
    d = os.path.join(OUT_ROOT, 'mri')
    _copy_real('MR_small.dcm', os.path.join(d, 'mri_01_MR_small_REAL.dcm'))
    _copy_real('emri_small.dcm', os.path.join(d, 'mri_02_emri_multiframe_REAL.dcm'))
    _w(os.path.join(d, 'mri_03_synthetic.nii.gz'), _nifti_bytes(gz=True))
    _w(os.path.join(d, 'mri_04_synthetic.nii'), _nifti_bytes(gz=False))
    _w(os.path.join(d, 'mri_05_dicom_series.zip'), _dicom_series_zip(n=8))
    plan['mri'] = [('mri_01_MR_small_REAL.dcm', {}),
                   ('mri_02_emri_multiframe_REAL.dcm', {}),
                   ('mri_03_synthetic.nii.gz', {}),
                   ('mri_04_synthetic.nii', {'slice_index': '5'}),
                   ('mri_05_dicom_series.zip', {'slice_index': '0'})]

    # ECG (DICOM waveform only)
    d = os.path.join(OUT_ROOT, 'ecg')
    _copy_real('waveform_ecg.dcm', os.path.join(d, 'ecg_01_waveform_REAL.dcm'))
    _w(os.path.join(d, 'ecg_02_12lead_500hz.dcm'), _ecg_dicom_bytes(CANON_LEADS, n=2500, fs=500))
    _w(os.path.join(d, 'ecg_03_12lead_250hz.dcm'), _ecg_dicom_bytes(CANON_LEADS, n=1250, fs=250))
    _w(os.path.join(d, 'ecg_04_8lead_derive.dcm'),
       _ecg_dicom_bytes(['I', 'II', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6'], n=2500, fs=500))
    _w(os.path.join(d, 'ecg_05_12lead_1000hz.dcm'), _ecg_dicom_bytes(CANON_LEADS, n=5000, fs=1000))
    plan['ecg'] = [(f, {}) for f in ('ecg_01_waveform_REAL.dcm', 'ecg_02_12lead_500hz.dcm',
                                     'ecg_03_12lead_250hz.dcm', 'ecg_04_8lead_derive.dcm',
                                     'ecg_05_12lead_1000hz.dcm')]

    # Echo
    d = os.path.join(OUT_ROOT, 'echo')
    _copy_real('US1_UNCR.dcm', os.path.join(d, 'echo_01_ultrasound_REAL.dcm'))
    _w(os.path.join(d, 'echo_02_cine_mono.dcm'), _multiframe_dicom_bytes(frames=20, rgb=False))
    _w(os.path.join(d, 'echo_03_cine_rgb.dcm'), _multiframe_dicom_bytes(frames=16, rgb=True))
    _write_video(os.path.join(d, 'echo_04_clip.mp4'), 'mp4v', frames=24)
    _write_video(os.path.join(d, 'echo_05_clip.avi'), 'MJPG', frames=24)
    plan['echo'] = [(f, {}) for f in ('echo_01_ultrasound_REAL.dcm', 'echo_02_cine_mono.dcm',
                                      'echo_03_cine_rgb.dcm', 'echo_04_clip.mp4', 'echo_05_clip.avi')]

    # EEG
    d = os.path.join(OUT_ROOT, 'eeg')
    montage19 = ['Fp1', 'Fp2', 'F7', 'F3', 'Fz', 'F4', 'F8', 'T7', 'C3', 'Cz',
                 'C4', 'T8', 'P7', 'P3', 'Pz', 'P4', 'P8', 'O1', 'O2']
    _w(os.path.join(d, 'eeg_01_brainvision_19ch.zip'),
       _brainvision_zip_bytes(montage19, n_samp=2500, sfreq=250.0, base='eeg19'))
    _w(os.path.join(d, 'eeg_02_brainvision_2ch.zip'),
       _brainvision_zip_bytes(['Fp1', 'Fp2'], n_samp=2500, sfreq=500.0, base='eeg2'))
    _eeglab_set_path(os.path.join(d, 'eeg_03_eeglab.set'),
                     ['Fz', 'Cz', 'Pz', 'Oz', 'C3', 'C4'], n=1536, sfreq=256.0)
    _write_bdf(os.path.join(d, 'eeg_04_biosemi.bdf'),
               ['Fp1', 'Fp2', 'C3', 'C4', 'O1', 'O2'], n_sec=6, sfreq=256.0)
    _w(os.path.join(d, 'eeg_05_brainvision_8ch.zip'),
       _brainvision_zip_bytes(['F3', 'F4', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2'],
                              n_samp=2048, sfreq=256.0, base='eeg8'))
    plan['eeg'] = [(f, {}) for f in ('eeg_01_brainvision_19ch.zip', 'eeg_02_brainvision_2ch.zip',
                                     'eeg_03_eeglab.set', 'eeg_04_biosemi.bdf',
                                     'eeg_05_brainvision_8ch.zip')]
    return plan


def verify(plan):
    from apps.conversion.converters import CONVERTERS

    print('\n%-8s %-34s %10s  %-8s %10s  %s' % ('MODALITY', 'FILE', 'IN', 'OUT', 'OUT SIZE', 'STATUS'))
    print('-' * 96)
    ok = 0
    total = 0
    for mod, files in plan.items():
        convert = CONVERTERS[mod]
        for fname, params in files:
            total += 1
            src = os.path.join(OUT_ROOT, mod, fname)
            in_kb = '%.1f KB' % (os.path.getsize(src) / 1024)
            with tempfile.TemporaryDirectory() as work:
                dst = os.path.join(work, fname)
                shutil.copyfile(src, dst)
                try:
                    out_path, meta = convert(dst, **params)
                    out_kb = '%.1f KB' % (os.path.getsize(out_path) / 1024)
                    out_ext = os.path.splitext(out_path)[1]
                    status = 'OK'
                    ok += 1
                except Exception as e:  # noqa: BLE001
                    out_kb, out_ext, status = '-', '-', 'FAIL: %s: %s' % (type(e).__name__, e)
            print('%-8s %-34s %10s  %-8s %10s  %s' % (mod, fname, in_kb, out_ext, out_kb, status))
    print('-' * 96)
    print('%d/%d files converted successfully' % (ok, total))
    return ok == total


if __name__ == '__main__':
    plan = build()
    print('Wrote raw test files to: %s' % OUT_ROOT)
    all_ok = verify(plan)
    sys.exit(0 if all_ok else 1)
