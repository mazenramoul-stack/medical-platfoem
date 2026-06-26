"""End-to-end converter smoke tests (need the heavy libs: pydicom, nibabel,
mne, opencv). Each builds a tiny synthetic fixture, posts it to
/api/convert/<modality>/ as a technician, and asserts the standardized file
comes back with the right content type — and that it re-parses as a valid file.

CI does not run these (it skips the heavy-lib suites); run locally with
`python manage.py test apps.conversion`.
"""

import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

import numpy as np
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APITestCase

User = get_user_model()

# Optional real smartwatch ECG sample (gitignored under media/; present locally
# after a manual drop). When present, it backs the HR-vs-printed-bpm ground-truth
# check; otherwise that one test skips, like the inference-pipeline sample tests.
BACKEND_DIR = Path(__file__).resolve().parents[3]
SMARTWATCH_SAMPLE = BACKEND_DIR / "media" / "ecg" / "test_smartwatch.pdf"


# --- fixture builders ------------------------------------------------------

def _mri_dicom_bytes(rows=32, cols=32, frames=1, modality='MR'):
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
    ds.Modality = modality
    ds.Rows = rows
    ds.Columns = cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = 16
    ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.InstanceNumber = 1
    rng = np.random.RandomState(0)
    if frames > 1:
        ds.NumberOfFrames = frames
        px = rng.randint(0, 4096, (frames, rows, cols)).astype(np.uint16)
    else:
        px = rng.randint(0, 4096, (rows, cols)).astype(np.uint16)
    ds.PixelData = px.tobytes()
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _mri_dicom_series_zip(n=3, rows=16, cols=16):
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
            ds.PixelData = (np.full((rows, cols), i * 100, dtype=np.uint16)).tobytes()
            ds.is_little_endian = True
            ds.is_implicit_VR = False
            b = io.BytesIO()
            ds.save_as(b, write_like_original=False)
            zf.writestr(f'slice_{i:03d}.dcm', b.getvalue())
    return zbuf.getvalue()


def _nifti_bytes(shape=(16, 16, 8)):
    import nibabel as nib
    vol = (np.random.RandomState(1).rand(*shape) * 1000).astype(np.int16)
    img = nib.Nifti1Image(vol, np.eye(4))
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'vol.nii.gz')
        nib.save(img, p)
        with open(p, 'rb') as fh:
            return fh.read()


def _echo_multiframe_dicom_bytes(frames=5, rows=24, cols=24):
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
    ds.Modality = 'US'
    ds.Rows, ds.Columns = rows, cols
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = 'MONOCHROME2'
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    ds.NumberOfFrames = frames
    ds.CineRate = 30
    px = np.random.RandomState(2).randint(0, 256, (frames, rows, cols)).astype(np.uint8)
    ds.PixelData = px.tobytes()
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _brainvision_zip_bytes(n_ch=2, n_samp=1000, sfreq=500.0):
    """Hand-built BrainVision (vhdr + vmrk + binary eeg), zipped — mne reads it
    without pybv/eeglabio (which are not installed)."""
    base = 'eeg_demo'
    interval_us = int(round(1_000_000 / sfreq))
    ch_lines = '\n'.join(f'Ch{i+1}=EEG{i+1},,1,µV' for i in range(n_ch))
    vhdr = (
        'Brain Vision Data Exchange Header File Version 1.0\n\n'
        '[Common Infos]\n'
        'Codepage=UTF-8\n'
        f'DataFile={base}.eeg\n'
        f'MarkerFile={base}.vmrk\n'
        'DataFormat=BINARY\n'
        'DataOrientation=MULTIPLEXED\n'
        f'NumberOfChannels={n_ch}\n'
        f'SamplingInterval={interval_us}\n\n'
        '[Binary Infos]\n'
        'BinaryFormat=IEEE_FLOAT_32\n\n'
        '[Channel Infos]\n'
        f'{ch_lines}\n'
    )
    vmrk = (
        'Brain Vision Data Exchange Marker File, Version 1.0\n\n'
        '[Common Infos]\n'
        'Codepage=UTF-8\n'
        f'DataFile={base}.eeg\n\n'
        '[Marker Infos]\n'
        'Mk1=New Segment,,1,1,0,00000000000000000000\n'
    )
    t = np.arange(n_samp) / sfreq
    data = np.vstack([np.sin(2 * np.pi * (i + 1) * t) * 20 for i in range(n_ch)])  # (ch, samp)
    multiplexed = data.T.astype('<f4').tobytes()  # MULTIPLEXED = sample-major
    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, 'w') as zf:
        zf.writestr(f'{base}.vhdr', vhdr.encode('utf-8'))
        zf.writestr(f'{base}.vmrk', vmrk.encode('utf-8'))
        zf.writestr(f'{base}.eeg', multiplexed)
    return zbuf.getvalue()


def _ecg_dicom_bytes(n=1000, fs=500, n_leads=12):
    import pydicom
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    lead_names = ['Lead I', 'Lead II', 'Lead III', 'Lead aVR', 'Lead aVL', 'Lead aVF',
                  'Lead V1', 'Lead V2', 'Lead V3', 'Lead V4', 'Lead V5', 'Lead V6']
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
    wf.NumberOfWaveformChannels = n_leads
    wf.NumberOfWaveformSamples = n
    wf.SamplingFrequency = fs
    wf.WaveformBitsAllocated = 16
    wf.WaveformSampleInterpretation = 'SS'
    chans = []
    data = np.zeros((n, n_leads), dtype=np.int16)
    for i in range(n_leads):
        ch = Dataset()
        ch.ChannelSensitivity = 1.0
        ch.ChannelSensitivityCorrectionFactor = 1.0
        ch.ChannelBaseline = 0.0
        unit = Dataset()
        unit.CodeValue = 'uV'
        unit.CodingSchemeDesignator = 'UCUM'
        unit.CodeMeaning = 'microvolt'
        ch.ChannelSensitivityUnitsSequence = [unit]
        src = Dataset()
        src.CodeValue = str(i + 1)
        src.CodingSchemeDesignator = 'MDC'
        src.CodeMeaning = lead_names[i]
        ch.ChannelSourceSequence = [src]
        ch.WaveformBitsStored = 16
        chans.append(ch)
        data[:, i] = (np.sin(np.linspace(0, 20 * np.pi, n)) * 1000 * (i + 1)).astype(np.int16)
    wf.ChannelDefinitionSequence = chans
    wf.WaveformData = data.tobytes()
    ds.WaveformSequence = [wf]
    ds.is_little_endian = True
    ds.is_implicit_VR = False
    buf = io.BytesIO()
    ds.save_as(buf, write_like_original=False)
    return buf.getvalue()


def _smartwatch_ecg_pdf_bytes(n_strips=3, w=1200, strip_gap=250, top=200):
    """Synthesize a smartwatch-style ECG PDF: red trace on white, N strips.

    Each strip is a flat red baseline (dense rows -> detectable strip) with
    periodic upward QRS-like spikes, embedded as the page image — exactly the
    raster-only shape the digitizer must handle. No grid/text needed.
    """
    from PIL import Image, ImageDraw

    h = top + strip_gap * n_strips + 100
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    red = (220, 30, 40)
    x0, x1 = 60, w - 60
    for s in range(n_strips):
        base_y = top + s * strip_gap
        draw.line([(x0, base_y), (x1, base_y)], fill=red, width=3)  # baseline
        for x in range(x0 + 60, x1 - 20, 110):                       # QRS spikes
            draw.line([(x, base_y), (x + 4, base_y - 55)], fill=red, width=3)
            draw.line([(x + 4, base_y - 55), (x + 8, base_y)], fill=red, width=3)
    buf = io.BytesIO()
    img.save(buf, format="PDF")
    return buf.getvalue()


# --- tests -----------------------------------------------------------------

class ConverterSmokeTest(APITestCase):
    def setUp(self):
        self.tech = User.objects.create_user(
            email='tech@test.com', password='PassB1!xx', full_name='Tech',
            role=User.Role.TECHNICIAN)
        self.client.force_authenticate(user=self.tech)

    def _post(self, modality, filename, content, **extra):
        f = SimpleUploadedFile(filename, content, content_type='application/octet-stream')
        return self.client.post(f'/api/convert/{modality}/', {'file': f, **extra}, format='multipart')

    # MRI -------------------------------------------------------------------
    def test_mri_nifti_to_png(self):
        resp = self._post('mri', 'vol.nii.gz', _nifti_bytes())
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        self.assertEqual(resp['Content-Type'], 'image/png')
        self.assertIn('attachment', resp['Content-Disposition'])
        from PIL import Image
        img = Image.open(io.BytesIO(resp.content))
        self.assertEqual(img.format, 'PNG')
        self.assertEqual(img.mode, 'L')

    def test_mri_single_dicom_to_png(self):
        resp = self._post('mri', 'scan.dcm', _mri_dicom_bytes(rows=32, cols=32))
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        self.assertEqual(resp['Content-Type'], 'image/png')
        from PIL import Image
        img = Image.open(io.BytesIO(resp.content))
        self.assertEqual(img.size, (32, 32))

    def test_mri_dicom_series_zip_with_slice_index(self):
        resp = self._post('mri', 'series.zip', _mri_dicom_series_zip(n=3), slice_index='0')
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        self.assertEqual(resp['Content-Type'], 'image/png')

    def test_mri_unsupported_extension_is_clean_422(self):
        resp = self._post('mri', 'notes.txt', b'hello')
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data['status'], 'failed')
        self.assertEqual(resp.data['error_type'], 'UnsupportedFormat')

    # Echo ------------------------------------------------------------------
    def test_echo_multiframe_dicom_to_mp4(self):
        resp = self._post('echo', 'cine.dcm', _echo_multiframe_dicom_bytes(frames=5))
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        self.assertEqual(resp['Content-Type'], 'video/mp4')
        self.assertGreater(len(resp.content), 0)
        # The mp4 re-opens and has frames.
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as fh:
            fh.write(resp.content)
            path = fh.name
        try:
            import cv2
            cap = cv2.VideoCapture(path)
            self.assertTrue(cap.isOpened())
            count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            cap.release()
            self.assertGreaterEqual(count, 1)
        finally:
            os.remove(path)

    # EEG -------------------------------------------------------------------
    def test_eeg_brainvision_zip_to_edf(self):
        resp = self._post('eeg', 'eeg.zip', _brainvision_zip_bytes(n_ch=2))
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        self.assertGreater(len(resp.content), 0)
        with tempfile.NamedTemporaryFile(suffix='.edf', delete=False) as fh:
            fh.write(resp.content)
            path = fh.name
        try:
            import mne
            raw = mne.io.read_raw_edf(path, preload=False, verbose='ERROR')
            self.assertEqual(len(raw.ch_names), 2)
        finally:
            os.remove(path)

    # ECG -------------------------------------------------------------------
    def test_ecg_dicom_waveform_to_csv(self):
        resp = self._post('ecg', 'ecg.dcm', _ecg_dicom_bytes())
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        self.assertEqual(resp['Content-Type'], 'text/csv')
        import pandas as pd
        df = pd.read_csv(io.BytesIO(resp.content))
        self.assertEqual(list(df.columns),
                         ['I', 'II', 'III', 'aVR', 'aVL', 'aVF',
                          'V1', 'V2', 'V3', 'V4', 'V5', 'V6'])
        self.assertEqual(len(df), 1000)

    def test_ecg_unsupported_format_is_friendly_422(self):
        resp = self._post('ecg', 'scan.xml', b'<ecg/>')
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data['error_type'], 'UnsupportedFormat')

    # ECG — smartwatch single-lead PDF --------------------------------------
    def test_ecg_smartwatch_pdf_returns_inline_result(self):
        resp = self._post('ecg', 'watch.pdf', _smartwatch_ecg_pdf_bytes(n_strips=3))
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        # Inline analysis result (JSON), not a bare file download.
        self.assertEqual(resp.data['status'], 'success')
        self.assertTrue(resp.data['single_lead'])
        self.assertEqual(resp.data['lead'], 'I')
        self.assertEqual(resp.data['n_samples'], 15000)  # 3 strips x 10 s x 500 Hz
        self.assertIn('screening', resp.data)
        self.assertIn('signal_preview', resp.data)
        self.assertGreater(len(resp.data['signal_preview']), 0)
        # The CSV is embedded for download — single 'I' column.
        import pandas as pd
        df = pd.read_csv(io.StringIO(resp.data['csv_text']))
        self.assertEqual(list(df.columns), ['I'])
        self.assertEqual(len(df), 15000)
        self.assertTrue(resp.data['csv_filename'].endswith('_leadI.csv'))

    def test_ecg_pdf_without_trace_is_clean_422(self):
        """A PDF with no red ECG trace fails cleanly (422), never a 500."""
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (400, 300), (255, 255, 255)).save(buf, format='PDF')
        resp = self._post('ecg', 'blank.pdf', buf.getvalue())
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.data['error_type'], 'NoTraceFound')

    @unittest.skipUnless(SMARTWATCH_SAMPLE.exists(),
                         f"Missing real smartwatch sample at {SMARTWATCH_SAMPLE}")
    def test_ecg_smartwatch_real_sample_hr_matches_printed(self):
        """Ground truth: the reference watch PDF prints 76 bpm — the server's own
        single-lead screening must reproduce it (end-to-end CV correctness)."""
        with open(SMARTWATCH_SAMPLE, 'rb') as fh:
            resp = self._post('ecg', 'watch.pdf', fh.read())
        self.assertEqual(resp.status_code, 200, getattr(resp, 'data', resp.content))
        hr = resp.data['screening']['mean_hr_bpm']
        self.assertIsNotNone(hr)
        self.assertAlmostEqual(hr, 76.0, delta=6.0,
                               msg=f'screened HR {hr} far from printed 76 bpm')
        self.assertEqual(resp.data['screening']['hr_classification'], 'Normal')
