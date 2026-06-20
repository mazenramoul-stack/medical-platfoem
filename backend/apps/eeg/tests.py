"""Tests for EEG SHAP explainability (eeg_gradient_shap, explain_eeg, EEGExplainView).

These need the heavy EEG stack (torch + captum + mne/edfio). The pure-explainer
test builds a BIOTClassifier directly (random init — no trained head needed), so it
always runs. The explain_eeg / view tests need the fine-tuned IIIC head; they
skipTest gracefully when ``get_eeg_model()`` can't load it (a fresh checkout without
``biot_iiic.pt``), and run for real when the head is present. CI runs only the
weight-free suites — run these locally:

    python manage.py test apps.eeg

The view tests run on the in-memory SQLite test DB (core/settings.py swaps it in
when 'test' in sys.argv) via force_authenticate, mirroring apps/ecg/tests.py.
"""

from __future__ import annotations

import os
import tempfile
import unittest

import numpy as np
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

User = get_user_model()

# 16 longitudinal-bipolar channel labels, in BIOT's convert_signals() order.
BIPOLAR_CHANNELS = [
    'FP1-F7', 'F7-T7', 'T7-P7', 'P7-O1',
    'FP2-F8', 'F8-T8', 'T8-P8', 'P8-O2',
    'FP1-F3', 'F3-C3', 'C3-P3', 'P3-O1',
    'FP2-F4', 'F4-C4', 'C4-P4', 'P4-O2',
]
IIIC_CODES = ['SZ', 'LPD', 'GPD', 'LRDA', 'GRDA', 'Other']


class EegGradientShapTest(SimpleTestCase):
    """Direct unit coverage of the GradientShap explainer on a real BIOT model.

    Builds a BIOTClassifier directly (no trained head) — this exercises whether
    GradientShap actually backprops through BIOT's STFT front-end.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from apps.inference.biot import BIOTClassifier
        cls.model = BIOTClassifier(n_classes=6, n_channels=16, n_fft=200, hop_length=100)
        cls.model.eval()

    def test_returns_16x2000_map_in_unit_range(self):
        from apps.inference.explainers.eeg_shap import eeg_gradient_shap
        sig = np.random.default_rng(0).standard_normal((16, 2000)).astype(np.float32)
        attr = eeg_gradient_shap(self.model, sig, target_class=0, n_samples=4)
        self.assertEqual(attr.shape, (16, 2000))
        self.assertGreaterEqual(float(attr.min()), 0.0)
        self.assertLessEqual(float(attr.max()), 1.0 + 1e-5)

    def test_per_channel_importance_has_16_channels_in_unit_range(self):
        from apps.inference.explainers.eeg_shap import (
            eeg_gradient_shap, per_channel_importance)
        sig = np.random.default_rng(1).standard_normal((16, 2000)).astype(np.float32)
        attr = eeg_gradient_shap(self.model, sig, target_class=2, n_samples=4)
        imp = per_channel_importance(attr, BIPOLAR_CHANNELS)
        self.assertEqual(set(imp.keys()), set(BIPOLAR_CHANNELS))
        self.assertTrue(all(0.0 <= v <= 1.0 for v in imp.values()))


# --- shared fixtures ---------------------------------------------------------

def write_synthetic_edf(path: str, seconds: float = 12.0, sfreq: float = 256.0,
                        seed: int = 0) -> str:
    """Write a tiny synthetic referential 10-20 EDF that edf_to_bipolar can read.

    Uses mne + edfio (pyedflib is not installed in this venv). Channels are the
    referential 10-20 electrodes the BIOT bipolar montage requires.
    """
    import mne
    from apps.inference.eeg_preprocess import _REQUIRED_ELECTRODES

    ch_names = list(_REQUIRED_ELECTRODES)
    n = int(sfreq * seconds)
    rng = np.random.default_rng(seed)
    data = rng.standard_normal((len(ch_names), n)).astype(np.float64) * 2e-5  # ~20µV
    info = mne.create_info(ch_names=ch_names, sfreq=sfreq, ch_types='eeg')
    raw = mne.io.RawArray(data, info, verbose='ERROR')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw.export(path, fmt='edf', verbose='ERROR')
    return path


def eeg_head_loads() -> bool:
    """True iff the fine-tuned BIOT IIIC head loads (skip heavy tests otherwise)."""
    try:
        from apps.inference.model_loader import ModelLoader
        ModelLoader().get_eeg_model()
        return True
    except Exception:
        return False


# Resolved once at import; the model is a singleton reused by the real tests below.
EEG_HEAD = eeg_head_loads()
SKIP_MSG = 'BIOT IIIC head (biot_iiic.pt) not available — explain_eeg tests skipped.'


@unittest.skipUnless(EEG_HEAD, SKIP_MSG)
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ExplainEegEnvelopeTest(SimpleTestCase):
    """explain_eeg returns the {status, ...} envelope and NEVER raises (Contract 2)."""

    def test_success_on_synthetic_edf(self):
        from apps.inference import explain_eeg
        path = write_synthetic_edf(
            os.path.join(settings.MEDIA_ROOT, 'eeg/uploads/synthetic.edf'))
        res = explain_eeg(path)
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertTrue(res['shap_path'].endswith('.png'))
        self.assertTrue(os.path.exists(res['shap_path']))
        self.assertEqual(len(res['per_channel_importance']), 16)
        self.assertEqual(set(res['per_channel_importance'].keys()), set(BIPOLAR_CHANNELS))
        self.assertEqual(len(res['top_channels']), 3)
        self.assertIn(res['target_class'], IIIC_CODES)
        self.assertIn(res['predicted_class'], IIIC_CODES)
        self.assertEqual(set(res['class_probabilities'].keys()), set(IIIC_CODES))

    def test_chosen_class_is_honored(self):
        from apps.inference import explain_eeg
        path = write_synthetic_edf(
            os.path.join(settings.MEDIA_ROOT, 'eeg/uploads/syn_lpd.edf'), seed=2)
        res = explain_eeg(path, target_class='LPD')
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertEqual(res['target_class'], 'LPD')

    def test_numeric_class_index_is_honored(self):
        from apps.inference import explain_eeg
        path = write_synthetic_edf(
            os.path.join(settings.MEDIA_ROOT, 'eeg/uploads/syn_idx.edf'), seed=5)
        res = explain_eeg(path, target_class=3)  # LRDA
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertEqual(res['target_class'], 'LRDA')

    def test_invalid_class_falls_back_to_predicted(self):
        # Locked decision: a bad target_class is NOT a hard error — explain_eeg
        # falls back to the predicted class (kept explicit via target_class) so the
        # envelope contract is never broken by client input.
        from apps.inference import explain_eeg
        path = write_synthetic_edf(
            os.path.join(settings.MEDIA_ROOT, 'eeg/uploads/syn_bad.edf'), seed=3)
        res = explain_eeg(path, target_class='NOT_A_CLASS')
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertIn(res['target_class'], IIIC_CODES)
        self.assertEqual(res['target_class'], res['predicted_class'])

    def test_garbage_edf_returns_failed_envelope_without_raising(self):
        from apps.inference import explain_eeg
        path = os.path.join(settings.MEDIA_ROOT, 'eeg/uploads/garbage.edf')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(b'not a real EDF header at all\x00\x01\x02')
        res = explain_eeg(path)  # must not raise
        self.assertEqual(res['status'], 'failed')
        self.assertIn('error', res)
        self.assertIn('error_type', res)


@unittest.skipUnless(EEG_HEAD, SKIP_MSG)
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EEGExplainViewTest(APITestCase):
    """POST /api/eeg/{id}/explain/ — doctor isolation (Contract 1) + happy path."""

    def setUp(self):
        from apps.eeg.models import EEGAnalysis
        from apps.patients.models import Patient, PatientAssignment
        self.doc_a = User.objects.create_user(
            email='eeg_a@x.com', password='p', full_name='EA', role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='eeg_b@x.com', password='p', full_name='EB', role=User.Role.DOCTOR)
        self.tech = User.objects.create_user(
            email='eeg_t@x.com', password='p', full_name='ET', role=User.Role.TECHNICIAN)
        self.patient = Patient.objects.create(
            full_name='P', age=50, gender='M', created_by=self.doc_a)
        PatientAssignment.objects.create(
            patient=self.patient, doctor=self.doc_a, assigned_by=self.doc_a)
        edf_src = write_synthetic_edf(os.path.join(tempfile.mkdtemp(), 'src.edf'))
        with open(edf_src, 'rb') as fh:
            edf_bytes = fh.read()
        edf = SimpleUploadedFile('eeg.edf', edf_bytes, content_type='application/octet-stream')
        self.analysis = EEGAnalysis.objects.create(
            patient=self.patient, file=edf, status=EEGAnalysis.Status.COMPLETED)
        self.url = f'/api/eeg/{self.analysis.pk}/explain/'

    def test_unassigned_doctor_gets_404(self):
        self.client.force_authenticate(user=self.doc_b)
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 404)

    def test_owner_gets_200_with_signed_shap_url(self):
        self.client.force_authenticate(user=self.doc_a)
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertIn('shap_path', resp.data)
        self.assertIn('sig=', resp.data['shap_path'])  # signed, time-limited URL
        self.assertEqual(len(resp.data['per_channel_importance']), 16)
        self.assertIn(resp.data['target_class'], IIIC_CODES)

    def test_technician_gets_200(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 200, msg=resp.content)

    def test_invalid_target_class_falls_back_and_returns_200(self):
        self.client.force_authenticate(user=self.doc_a)
        resp = self.client.post(self.url, {'target_class': 'BOGUS'}, format='json')
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertIn(resp.data['target_class'], IIIC_CODES)
        self.assertEqual(resp.data['target_class'], resp.data['predicted_class'])
