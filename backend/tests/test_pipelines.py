"""Automated tests for the Multimodal Medical AI Platform.

Three groups:
    1. MRIPipelineTest   — exercises analyze_mri() against the on-disk sample.
    2. ECGPipelineTest   — exercises analyze_ecg() against the on-disk sample.
    3. APITest           — end-to-end HTTP tests for auth, patients, MRI/ECG
                            upload, and report generation, using DRF's APIClient.

Inference tests use SimpleTestCase (no DB) and are skipped if the test sample
files don't exist. Generate them first via:

    python apps/inference/test_pipelines.py
"""

from __future__ import annotations

import io
import os
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

MRI_SAMPLE = BACKEND_DIR / "media" / "mri" / "test_sample.png"
ECG_SAMPLE = BACKEND_DIR / "media" / "ecg" / "test_sample.csv"


# ---------------------------------------------------------------------------
# Inference-pipeline tests (no DB)
# ---------------------------------------------------------------------------

@unittest.skipUnless(MRI_SAMPLE.exists(), f"Missing sample MRI at {MRI_SAMPLE}")
class MRIPipelineTest(SimpleTestCase):
    """Exercises the U-Net + ViT pipeline against the cached test image."""

    def test_mri_inference_on_sample(self):
        from apps.inference import analyze_mri

        result = analyze_mri(str(MRI_SAMPLE))

        self.assertEqual(result.get("status"), "success",
                         msg=f"analyze_mri failed: {result}")
        for key in (
            "tumor_detected", "tumor_type", "tumor_type_confidence",
            "tumor_area_pixels", "segmentation_confidence",
            "models_agree", "overall_verdict",
            "mask_path", "overlay_path", "analysis_path",
            "report", "models_used", "elapsed_seconds",
        ):
            self.assertIn(key, result, msg=f"missing key {key!r} in result")

        self.assertIsInstance(result["models_agree"], bool)
        self.assertIn(result["overall_verdict"], ("consistent", "uncertain"))
        self.assertIsInstance(result["tumor_type"], str)
        self.assertGreaterEqual(result["tumor_type_confidence"], 0.0)
        self.assertLessEqual(result["tumor_type_confidence"], 1.0)
        self.assertIsInstance(result["report"], str)
        self.assertGreater(len(result["report"]), 100)

    def test_classify_emits_gradcam_path(self):
        from apps.inference import analyze_mri

        result = analyze_mri(str(MRI_SAMPLE), mode="classify")
        self.assertEqual(result["status"], "success")
        self.assertIn("gradcam_path", result)
        self.assertTrue(result["gradcam_path"] is None or result["gradcam_path"].endswith("_gradcam.png"))

    def test_explain_mri_envelope(self):
        from apps.inference import explain_mri

        out = explain_mri(str(MRI_SAMPLE))
        self.assertIn(out["status"], ("success", "failed"))
        if out["status"] == "success":
            for key in ("gradcam_path", "shap_path", "peak", "agreement"):
                self.assertIn(key, out)
            self.assertIn("spearman", out["agreement"])
            self.assertIn("nx", out["peak"])


@unittest.skipUnless(ECG_SAMPLE.exists(), f"Missing sample ECG at {ECG_SAMPLE}")
class ECGPipelineTest(SimpleTestCase):
    """Exercises the DenseNet-1D ensemble + NeuroKit2 pipeline."""

    def test_ecg_inference_on_sample(self):
        from apps.inference import analyze_ecg

        result = analyze_ecg(str(ECG_SAMPLE))

        self.assertEqual(result.get("status"), "success",
                         msg=f"analyze_ecg failed: {result}")
        for key in (
            "arrhythmia_detected", "diagnosis", "diagnosis_confidence",
            "all_pathology_probabilities", "heart_rate_bpm", "hr_classification",
            "hrv_metrics", "plot_path", "report", "models_used", "elapsed_seconds",
        ):
            self.assertIn(key, result, msg=f"missing key {key!r} in result")

        # HRV dict shape
        for hrv_key in ("RMSSD_ms", "SDNN_ms", "pNN50_percent"):
            self.assertIn(hrv_key, result["hrv_metrics"])

        # Pathology probability dict shape
        probs = result["all_pathology_probabilities"]
        self.assertIsInstance(probs, dict)
        self.assertGreater(len(probs), 0)
        for code, entry in probs.items():
            self.assertIn("probability", entry)
            self.assertIn("detected", entry)
            self.assertGreaterEqual(entry["probability"], 0.0)
            self.assertLessEqual(entry["probability"], 1.0)


# ---------------------------------------------------------------------------
# Helper: build a minimal valid ECG CSV in-memory
# ---------------------------------------------------------------------------

def _build_minimal_ecg_csv() -> bytes:
    """Build a 10-second 12-lead CSV of synthetic-but-cheap data (no neurokit2)."""
    t = np.arange(5000) / 500.0  # 10 s @ 500 Hz
    leads = []
    rng = np.random.default_rng(0)
    for i in range(12):
        # Combine a few sines so the bandpass filter has something to chew on
        sig = (0.5 * np.sin(2 * np.pi * 1.2 * t)         # ~1.2 Hz "heartbeat"
               + 0.2 * np.sin(2 * np.pi * 5 * t + i)     # higher-freq harmonic
               + 0.05 * rng.standard_normal(len(t)))      # noise
        leads.append(sig)
    arr = np.array(leads).T
    buf = io.StringIO()
    pd.DataFrame(arr, columns=[f"L{i+1}" for i in range(12)]).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _build_minimal_png() -> bytes:
    """Tiny 8×8 PNG of pure grayscale noise, just to satisfy file-extension checks."""
    from PIL import Image
    arr = (np.random.default_rng(1).random((8, 8, 3)) * 255).astype(np.uint8)
    img = Image.fromarray(arr)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# API-level tests (uses test DB via APITestCase)
# ---------------------------------------------------------------------------

class APITest(APITestCase):
    """HTTP-layer tests covering auth, patients, MRI/ECG upload, and reports.

    The upload tests use minimal synthetic content — inference will likely
    fail on such data, but the API contract is what we're validating
    (HTTP status codes, response shape, doctor-scoped permissions).
    """

    EMAIL = "apitest@example.com"
    PASSWORD = "ApiTestPass1!"

    def setUp(self):
        super().setUp()
        self.token = None

    # --- auth flow ----------------------------------------------------

    def _register_and_login(self) -> str:
        if self.token:
            return self.token
        resp = self.client.post("/api/auth/register/", {
            "email": self.EMAIL, "password": self.PASSWORD,
            "full_name": "API Test", "role": "doctor",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, msg=resp.content)
        self.token = resp.data["access"]
        return self.token

    def _auth(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self._register_and_login()}")

    def test_auth_flow(self):
        # Register
        resp = self.client.post("/api/auth/register/", {
            "email": self.EMAIL, "password": self.PASSWORD,
            "full_name": "API Test", "role": "doctor",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["user"]["email"], self.EMAIL)
        access = resp.data["access"]

        # Login
        resp = self.client.post("/api/auth/login/", {
            "email": self.EMAIL, "password": self.PASSWORD,
        }, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)

        # /me/ with bearer
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["email"], self.EMAIL)

        # /me/ without bearer → 401
        self.client.credentials()
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 401)

    def test_create_patient(self):
        self._auth()
        resp = self.client.post("/api/patients/", {
            "full_name": "Test Patient",
            "age": 50,
            "gender": "M",
            "medical_history": "Hypertension",
        }, format="json")
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        self.assertEqual(resp.data["full_name"], "Test Patient")
        # Doctor was auto-set, not client-provided
        self.assertIsNotNone(resp.data.get("doctor"))

        # Patient appears in the list
        resp_list = self.client.get("/api/patients/")
        self.assertEqual(resp_list.status_code, 200)
        self.assertTrue(any(p["id"] == resp.data["id"] for p in resp_list.data))

    def test_mri_upload_endpoint(self):
        self._auth()
        # Need a patient first
        p = self.client.post("/api/patients/", {
            "full_name": "MRI Patient", "age": 60, "gender": "F",
        }, format="json").data
        pid = p["id"]

        upload = SimpleUploadedFile(
            "test.png", _build_minimal_png(), content_type="image/png",
        )
        resp = self.client.post("/api/mri/upload/", {
            "patient_id": pid, "file": upload,
        }, format="multipart")
        # 201 if inference succeeded; 202 if inference failed (still a valid record)
        self.assertIn(resp.status_code, (201, 202), msg=resp.content)
        self.assertIn("status", resp.data)
        self.assertIn("file_url", resp.data)
        self.assertEqual(resp.data["patient"], pid)

    def test_ecg_upload_endpoint(self):
        self._auth()
        p = self.client.post("/api/patients/", {
            "full_name": "ECG Patient", "age": 55, "gender": "M",
        }, format="json").data
        pid = p["id"]

        upload = SimpleUploadedFile(
            "test.csv", _build_minimal_ecg_csv(), content_type="text/csv",
        )
        resp = self.client.post("/api/ecg/upload/", {
            "patient_id": pid, "file": upload,
        }, format="multipart")
        self.assertIn(resp.status_code, (201, 202), msg=resp.content)
        self.assertIn("status", resp.data)
        self.assertEqual(resp.data["patient"], pid)

    def test_report_generation(self):
        """Reports require at least one *completed* analysis. If our synthetic
        upload didn't complete, report generation should return 400 with a
        sensible message — that's a valid API contract test even though the
        upstream pipeline failed on dummy data."""
        self._auth()
        p = self.client.post("/api/patients/", {
            "full_name": "Report Patient", "age": 40, "gender": "F",
        }, format="json").data
        pid = p["id"]

        # No analyses yet → 400 (at least one of mri_analysis_id / ecg_analysis_id required)
        resp = self.client.post("/api/reports/generate/", {
            "patient_id": pid,
        }, format="json")
        self.assertEqual(resp.status_code, 400, msg=resp.content)

        # Missing patient → 400
        resp = self.client.post("/api/reports/generate/", {
            "mri_analysis_id": 1,
        }, format="json")
        self.assertEqual(resp.status_code, 400)
