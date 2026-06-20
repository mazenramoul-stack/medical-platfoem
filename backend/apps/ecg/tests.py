"""Tests for ECG SHAP explainability (ecg_gradient_shap, explain_ecg, ECGExplainView).

These need the heavy ECG stack (torch + ecglib + captum) and download ecglib
weights on first run, so CI runs only the weight-free suites — run these locally:

    python manage.py test apps.ecg

The view tests run on the in-memory SQLite test DB (core/settings.py swaps it in
when 'test' in sys.argv) via force_authenticate, mirroring tests/test_doctor_isolation.py.
"""

from __future__ import annotations

import io
import os
import tempfile

import numpy as np
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APITestCase

User = get_user_model()

LEADS = ['I', 'II', 'III', 'aVR', 'aVL', 'aVF', 'V1', 'V2', 'V3', 'V4', 'V5', 'V6']
PATHOLOGY_CODES = ['AFIB', '1AVB', 'STACH', 'SBRAD', 'RBBB', 'LBBB', 'PVC']


def synthetic_ecg_csv_bytes(n: int = 5000, seed: int = 0) -> bytes:
    """A tiny synthetic 12-lead ECG CSV (columns I..V6, ~5000 rows @ 500 Hz)."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, n / 500.0, n, endpoint=False)
    cols = [np.sin(2 * np.pi * 1.2 * t + k * 0.3) + 0.1 * rng.standard_normal(n)
            for k in range(12)]
    arr = np.stack(cols, axis=1)  # (n, 12)
    buf = io.StringIO()
    np.savetxt(buf, arr, delimiter=',', header=','.join(LEADS), comments='', fmt='%.4f')
    return buf.getvalue().encode('utf-8')


class EcgGradientShapTest(SimpleTestCase):
    """Direct unit coverage of the GradientShap explainer on a real ecglib model."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        from ecglib.models import create_model
        cls.model = create_model(model_name='densenet1d121', pathology='AFIB', pretrained=True)
        cls.model.eval()

    def test_returns_12x5000_map_in_unit_range(self):
        from apps.inference.explainers.ecg_shap import ecg_gradient_shap
        sig = np.random.default_rng(0).standard_normal((12, 5000)).astype(np.float32)
        attr = ecg_gradient_shap(self.model, sig, n_samples=4)
        self.assertEqual(attr.shape, (12, 5000))
        self.assertGreaterEqual(float(attr.min()), 0.0)
        self.assertLessEqual(float(attr.max()), 1.0 + 1e-5)

    def test_per_lead_importance_has_12_leads_in_unit_range(self):
        from apps.inference.explainers.ecg_shap import ecg_gradient_shap, per_lead_importance
        sig = np.random.default_rng(1).standard_normal((12, 5000)).astype(np.float32)
        attr = ecg_gradient_shap(self.model, sig, n_samples=4)
        imp = per_lead_importance(attr, LEADS)
        self.assertEqual(set(imp.keys()), set(LEADS))
        self.assertTrue(all(0.0 <= v <= 1.0 for v in imp.values()))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ExplainEcgEnvelopeTest(SimpleTestCase):
    """explain_ecg returns the {status, ...} envelope and NEVER raises (Contract 2)."""

    def _write(self, name, data: bytes) -> str:
        path = os.path.join(settings.MEDIA_ROOT, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(data)
        return path

    def test_success_on_synthetic_csv(self):
        from apps.inference import explain_ecg
        path = self._write('ecg/uploads/synthetic.csv', synthetic_ecg_csv_bytes())
        res = explain_ecg(path)
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertTrue(res['shap_path'].endswith('.png'))
        self.assertTrue(os.path.exists(res['shap_path']))
        self.assertEqual(len(res['per_lead_importance']), 12)
        self.assertEqual(set(res['per_lead_importance'].keys()), set(LEADS))
        self.assertEqual(len(res['top_leads']), 3)
        self.assertIn(res['pathology'], PATHOLOGY_CODES)

    def test_chosen_pathology_is_honored(self):
        from apps.inference import explain_ecg
        path = self._write('ecg/uploads/syn_rbbb.csv', synthetic_ecg_csv_bytes(seed=2))
        res = explain_ecg(path, pathology='RBBB')
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertEqual(res['pathology'], 'RBBB')

    def test_invalid_pathology_falls_back_to_primary(self):
        # Locked decision: a bad pathology value is NOT a hard error — explain_ecg
        # falls back to the primary diagnosis (kept explicit via the returned
        # `pathology`) so the envelope contract is never broken by client input.
        from apps.inference import explain_ecg
        path = self._write('ecg/uploads/syn_bad.csv', synthetic_ecg_csv_bytes(seed=3))
        res = explain_ecg(path, pathology='NOT_A_CODE')
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertIn(res['pathology'], PATHOLOGY_CODES)

    def test_garbage_csv_returns_failed_envelope_without_raising(self):
        from apps.inference import explain_ecg
        path = self._write('ecg/uploads/garbage.csv', b'not,a,real\nzz,qq,\n')
        res = explain_ecg(path)  # must not raise
        self.assertEqual(res['status'], 'failed')
        self.assertIn('error', res)
        self.assertIn('error_type', res)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ECGExplainViewTest(APITestCase):
    """POST /api/ecg/{id}/explain/ — doctor isolation (Contract 1) + happy path."""

    def setUp(self):
        from apps.ecg.models import ECGAnalysis
        from apps.patients.models import Patient, PatientAssignment
        self.doc_a = User.objects.create_user(
            email='exp_a@x.com', password='p', full_name='EA', role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='exp_b@x.com', password='p', full_name='EB', role=User.Role.DOCTOR)
        self.tech = User.objects.create_user(
            email='exp_t@x.com', password='p', full_name='ET', role=User.Role.TECHNICIAN)
        self.patient = Patient.objects.create(
            full_name='P', age=50, gender='M', created_by=self.doc_a)
        PatientAssignment.objects.create(
            patient=self.patient, doctor=self.doc_a, assigned_by=self.doc_a)
        csv = SimpleUploadedFile('ecg.csv', synthetic_ecg_csv_bytes(), content_type='text/csv')
        self.analysis = ECGAnalysis.objects.create(
            patient=self.patient, file=csv, status=ECGAnalysis.Status.COMPLETED)
        self.url = f'/api/ecg/{self.analysis.pk}/explain/'

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
        self.assertEqual(len(resp.data['per_lead_importance']), 12)
        self.assertIn(resp.data['pathology'], PATHOLOGY_CODES)

    def test_technician_gets_200(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 200, msg=resp.content)

    def test_invalid_pathology_falls_back_and_returns_200(self):
        self.client.force_authenticate(user=self.doc_a)
        resp = self.client.post(self.url, {'pathology': 'BOGUS'}, format='json')
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertIn(resp.data['pathology'], PATHOLOGY_CODES)
