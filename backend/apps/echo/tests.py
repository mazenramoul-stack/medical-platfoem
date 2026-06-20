"""Tests for Echo SHAP explainability (echo_gradient_shap, explain_echo, EchoExplainView).

These need the heavy echo stack (torch + torchvision + captum + opencv). The pure-
explainer test builds an R(2+1)D-18 EF model directly (random init — no EchoNet
weights needed), so it always runs and exercises whether GradientShap backprops
through the video model. The explain_echo / view tests need the real EchoNet
checkpoints; they skipTest gracefully when ``get_echo_models()`` can't load them (a
fresh checkout without the not-bundled echonet_*.pt), and run for real when present.
CI runs only the weight-free suites — run these locally:

    python manage.py test apps.echo

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


def _build_ef_model():
    """An R(2+1)D-18 with a single-output EF head (random init, no weights)."""
    import torch.nn as nn
    from torchvision.models.video import r2plus1d_18

    model = r2plus1d_18(weights=None)
    model.fc = nn.Linear(model.fc.in_features, 1)
    model.eval()
    return model


class EchoGradientShapTest(SimpleTestCase):
    """Direct unit coverage of the GradientShap explainer on a real R(2+1)D-18.

    Builds the EF model directly (no EchoNet weights) — this exercises whether
    GradientShap actually backprops through the video model. A short clip keeps
    the CPU cost of the backward passes small.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = _build_ef_model()

    def test_returns_thw_map_in_unit_range(self):
        from apps.inference.explainers.echo_shap import echo_gradient_shap
        clip = np.random.default_rng(0).standard_normal((3, 8, 112, 112)).astype(np.float32)
        attr = echo_gradient_shap(self.model, clip, n_samples=2)
        self.assertEqual(attr.shape, (8, 112, 112))
        self.assertGreaterEqual(float(attr.min()), 0.0)
        self.assertLessEqual(float(attr.max()), 1.0 + 1e-5)

    def test_frame_importance_has_one_value_per_frame_in_unit_range(self):
        from apps.inference.explainers.echo_shap import (
            echo_gradient_shap, frame_importance)
        clip = np.random.default_rng(1).standard_normal((3, 8, 112, 112)).astype(np.float32)
        attr = echo_gradient_shap(self.model, clip, n_samples=2)
        imp = frame_importance(attr)
        self.assertEqual(imp.shape, (8,))
        self.assertGreaterEqual(float(imp.min()), 0.0)
        self.assertLessEqual(float(imp.max()), 1.0 + 1e-5)


# --- shared fixtures ---------------------------------------------------------

def write_synthetic_avi(path: str, n_frames: int = 16, size: int = 112,
                        seed: int = 0) -> str:
    """Write a tiny synthetic echo .avi that load_echo_video (OpenCV) can read."""
    import cv2

    os.makedirs(os.path.dirname(path), exist_ok=True)
    rng = np.random.default_rng(seed)
    writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*'MJPG'), 30.0, (size, size))
    if not writer.isOpened():
        raise unittest.SkipTest('OpenCV VideoWriter has no MJPG codec on this host.')
    try:
        for _ in range(n_frames):
            writer.write(rng.integers(0, 255, (size, size, 3), dtype=np.uint8))
    finally:
        writer.release()
    return path


def echo_models_load() -> bool:
    """True iff the EchoNet checkpoints load (skip heavy tests otherwise)."""
    try:
        from apps.inference.model_loader import ModelLoader
        ModelLoader().get_echo_models()
        return True
    except Exception:
        return False


# Resolved once at import; the models are singletons reused by the real tests below.
ECHO_OK = echo_models_load()
SKIP_MSG = 'EchoNet weights (echonet_*.pt) not available — explain_echo tests skipped.'


@unittest.skipUnless(ECHO_OK, SKIP_MSG)
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ExplainEchoEnvelopeTest(SimpleTestCase):
    """explain_echo returns the {status, ...} envelope and NEVER raises (Contract 2)."""

    def test_success_on_synthetic_avi(self):
        from apps.inference import explain_echo
        path = write_synthetic_avi(
            os.path.join(settings.MEDIA_ROOT, 'echo/uploads/synthetic.avi'))
        res = explain_echo(path, n_samples=2)
        self.assertEqual(res['status'], 'success', msg=res)
        self.assertTrue(res['shap_path'].endswith('.png'))
        self.assertTrue(os.path.exists(res['shap_path']))
        self.assertEqual(res['target'], 'ef')
        self.assertIsInstance(res['ef'], float)
        self.assertGreaterEqual(res['n_frames'], 1)
        self.assertEqual(len(res['frame_importance']), res['n_frames'])
        self.assertEqual(len(res['top_frames']), 3)
        # top_frames carry a clip index + an approximate source video frame.
        for tf in res['top_frames']:
            self.assertIn('clip_index', tf)
            self.assertIn('video_frame', tf)

    def test_garbage_video_returns_failed_envelope_without_raising(self):
        from apps.inference import explain_echo
        path = os.path.join(settings.MEDIA_ROOT, 'echo/uploads/garbage.avi')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as fh:
            fh.write(b'not a real AVI at all\x00\x01\x02')
        res = explain_echo(path)  # must not raise
        self.assertEqual(res['status'], 'failed')
        self.assertIn('error', res)
        self.assertIn('error_type', res)


@unittest.skipUnless(ECHO_OK, SKIP_MSG)
@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class EchoExplainViewTest(APITestCase):
    """POST /api/echo/{id}/explain/ — doctor isolation (Contract 1) + happy path."""

    def setUp(self):
        from apps.echo.models import EchoAnalysis
        from apps.patients.models import Patient, PatientAssignment
        self.doc_a = User.objects.create_user(
            email='echo_a@x.com', password='p', full_name='EA', role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='echo_b@x.com', password='p', full_name='EB', role=User.Role.DOCTOR)
        self.tech = User.objects.create_user(
            email='echo_t@x.com', password='p', full_name='ET', role=User.Role.TECHNICIAN)
        self.patient = Patient.objects.create(
            full_name='P', age=50, gender='M', created_by=self.doc_a)
        PatientAssignment.objects.create(
            patient=self.patient, doctor=self.doc_a, assigned_by=self.doc_a)
        avi_src = write_synthetic_avi(os.path.join(tempfile.mkdtemp(), 'src.avi'))
        with open(avi_src, 'rb') as fh:
            avi_bytes = fh.read()
        avi = SimpleUploadedFile('echo.avi', avi_bytes, content_type='video/x-msvideo')
        self.analysis = EchoAnalysis.objects.create(
            patient=self.patient, file=avi, status=EchoAnalysis.Status.COMPLETED)
        self.url = f'/api/echo/{self.analysis.pk}/explain/'

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
        self.assertEqual(resp.data['target'], 'ef')
        self.assertEqual(len(resp.data['frame_importance']), resp.data['n_frames'])

    def test_technician_gets_200(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.post(self.url, {}, format='json')
        self.assertEqual(resp.status_code, 200, msg=resp.content)
