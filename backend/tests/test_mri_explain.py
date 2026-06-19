"""Tests for the MRI explainability endpoint + serializer field (Grad-CAM / SHAP).

DB-backed but weight-free: the serializer-field check and the doctor-isolation check
run on the in-memory SQLite test DB (so they run in CI). The isolation 404 fires at
get_object_or_404 BEFORE explain_mri runs, so no model weights are loaded.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.mri.models import MRIAnalysis
from apps.mri.serializers import MRIAnalysisSerializer
from apps.mri.views import MRIExplainView
from apps.patients.models import Patient, PatientAssignment

User = get_user_model()


class GradcamUrlFieldTest(TestCase):
    def test_serializer_exposes_gradcam_url_key(self):
        self.assertIn("gradcam_url", MRIAnalysisSerializer().fields)


class MRIExplainIsolationTest(APITestCase):
    """The explain endpoint must be doctor-isolated (a cross-doctor id -> 404)."""

    def setUp(self):
        super().setUp()
        self.doc_a = User.objects.create_user(
            email='xai_a@example.com', password='PassA1!xx', full_name='XAI A')
        self.doc_b = User.objects.create_user(
            email='xai_b@example.com', password='PassB1!xx', full_name='XAI B')
        self.patient_a = Patient.objects.create(
            full_name='XAI Patient', age=55, gender='F', created_by=self.doc_a)
        PatientAssignment.objects.create(patient=self.patient_a, doctor=self.doc_a)
        self.mri_a = MRIAnalysis.objects.create(
            patient=self.patient_a, file='mri/uploads/a.png',
            status=MRIAnalysis.Status.COMPLETED)

    def test_b_cannot_explain_a_mri(self):
        self.client.force_authenticate(user=self.doc_b)
        resp = self.client.post(f'/api/mri/{self.mri_a.pk}/explain/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(MRIAnalysis.objects.filter(pk=self.mri_a.pk).exists())

    def test_explain_route_is_registered(self):
        # Confirms the endpoint exists and maps to MRIExplainView WITHOUT executing
        # the view (so no model weights load) — complements the isolation test, which
        # otherwise couldn't distinguish "route missing" from "isolation working".
        from django.urls import resolve
        match = resolve(f'/api/mri/{self.mri_a.pk}/explain/')
        self.assertIs(match.func.view_class, MRIExplainView)
