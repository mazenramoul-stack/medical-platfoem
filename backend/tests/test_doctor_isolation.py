"""Doctor-isolation and registration-security API tests.

These cover the platform's #1 documented invariant — a doctor must NEVER see or
touch another doctor's patients or analyses (CLAUDE.md "Doctor isolation"
contract) — plus the registration privilege-escalation guard.

They run on the in-memory SQLite test DB that core/settings.py selects when
'test' is in sys.argv (djongo + MongoDB cannot host a throwaway test DB). They
use the ORM + force_authenticate rather than real uploads, so they execute in
milliseconds and never trigger model downloads/inference.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.mri.models import MRIAnalysis
from apps.patients.models import Patient

User = get_user_model()


class RegistrationSecurityTest(APITestCase):
    """The public register endpoint must never mint a non-doctor."""

    def test_cannot_self_register_as_admin(self):
        resp = self.client.post('/api/auth/register/', {
            'email': 'evil@example.com', 'password': 'StrongPass1!',
            'full_name': 'Evil User', 'role': 'admin',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, msg=resp.content)
        # Response reflects doctor, not the requested admin…
        self.assertEqual(resp.data['user']['role'], 'doctor')
        # …and the persisted user is a doctor, not an admin.
        self.assertEqual(User.objects.get(email='evil@example.com').role, 'doctor')


class DoctorIsolationTest(APITestCase):
    """Doctor B must be walled off from Doctor A's data on every endpoint."""

    def setUp(self):
        super().setUp()
        self.doc_a = User.objects.create_user(
            email='doc_a@example.com', password='PassA1!xx', full_name='Doctor A')
        self.doc_b = User.objects.create_user(
            email='doc_b@example.com', password='PassB1!xx', full_name='Doctor B')
        self.patient_a = Patient.objects.create(
            doctor=self.doc_a, full_name='Patient A', age=50, gender='M')
        self.mri_a = MRIAnalysis.objects.create(
            patient=self.patient_a, file='mri/uploads/a.png',
            status=MRIAnalysis.Status.COMPLETED)

    def _as(self, user):
        self.client.force_authenticate(user=user)

    # --- patients --------------------------------------------------------
    def test_b_cannot_retrieve_a_patient(self):
        self._as(self.doc_b)
        resp = self.client.get(f'/api/patients/{self.patient_a.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_b_list_excludes_a_patient(self):
        self._as(self.doc_b)
        resp = self.client.get('/api/patients/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.patient_a.pk, [p['id'] for p in resp.data])

    def test_b_cannot_delete_a_patient(self):
        self._as(self.doc_b)
        resp = self.client.delete(f'/api/patients/{self.patient_a.pk}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Patient.objects.filter(pk=self.patient_a.pk).exists())

    def test_b_cannot_view_a_patient_history(self):
        self._as(self.doc_b)
        resp = self.client.get(f'/api/patients/{self.patient_a.pk}/history/')
        self.assertEqual(resp.status_code, 404)

    # --- MRI analyses ----------------------------------------------------
    def test_b_cannot_retrieve_a_mri(self):
        self._as(self.doc_b)
        resp = self.client.get(f'/api/mri/{self.mri_a.pk}/')
        self.assertEqual(resp.status_code, 404)

    def test_b_mri_list_filtered_to_a_patient_is_empty(self):
        self._as(self.doc_b)
        resp = self.client.get(f'/api/mri/?patient_id={self.patient_a.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)

    def test_b_cannot_delete_a_mri(self):
        self._as(self.doc_b)
        resp = self.client.delete(f'/api/mri/{self.mri_a.pk}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(MRIAnalysis.objects.filter(pk=self.mri_a.pk).exists())

    def test_b_cannot_upload_to_a_patient(self):
        self._as(self.doc_b)
        png = SimpleUploadedFile('x.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')
        resp = self.client.post('/api/mri/upload/', {
            'patient_id': self.patient_a.pk, 'file': png,
        }, format='multipart')
        # Patient A is invisible to B → 404 before any inference runs.
        self.assertEqual(resp.status_code, 404)
        # No record was created under A.
        self.assertEqual(self.patient_a.mri_analyses.count(), 1)

    # --- positive control: A still sees A's own data ---------------------
    def test_a_can_access_own_patient_and_mri(self):
        self._as(self.doc_a)
        self.assertEqual(
            self.client.get(f'/api/patients/{self.patient_a.pk}/').status_code, 200)
        self.assertEqual(
            self.client.get(f'/api/mri/{self.mri_a.pk}/').status_code, 200)
