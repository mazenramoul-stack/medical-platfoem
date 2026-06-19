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
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APITestCase

from apps.ecg.models import ECGAnalysis
from apps.echo.models import EchoAnalysis
from apps.eeg.models import EEGAnalysis
from apps.mri.models import MRIAnalysis
from apps.patients.models import Patient

User = get_user_model()


class RegistrationSecurityTest(APITestCase):
    """The public register endpoint may pick doctor/technician but never staff."""

    def setUp(self):
        # Reset the register throttle (shared LocMemCache) between tests so the
        # 5/min limit doesn't 429 a later test in the same process.
        cache.clear()

    def test_cannot_self_register_with_an_invalid_role(self):
        # 'admin' is no longer a valid role → rejected, no account created.
        resp = self.client.post('/api/auth/register/', {
            'email': 'evil@example.com', 'password': 'StrongPass1!',
            'full_name': 'Evil User', 'role': 'admin',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, msg=resp.content)
        self.assertFalse(User.objects.filter(email='evil@example.com').exists())

    def test_cannot_self_register_as_staff_or_superuser(self):
        # A technician self-registration is allowed, but a malicious is_staff /
        # is_superuser in the same payload must be ignored.
        resp = self.client.post('/api/auth/register/', {
            'email': 'tech@example.com', 'password': 'StrongPass1!',
            'full_name': 'Tech User', 'role': 'technician',
            'is_staff': True, 'is_superuser': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, msg=resp.content)
        user = User.objects.get(email='tech@example.com')
        self.assertEqual(user.role, 'technician')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


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


class PatientHistoryAggregateTest(APITestCase):
    """The /history/ aggregate must return ALL four modalities, doctor-scoped.

    Regression for the bug where /history/ silently omitted echo & EEG even
    though those analyses existed — leaving the documented aggregate endpoint
    an incomplete view of the patient record.
    """

    def setUp(self):
        super().setUp()
        self.doc_a = User.objects.create_user(
            email='hist_a@example.com', password='PassA1!xx', full_name='Hist A')
        self.doc_b = User.objects.create_user(
            email='hist_b@example.com', password='PassB1!xx', full_name='Hist B')
        self.patient = Patient.objects.create(
            doctor=self.doc_a, full_name='Hist Patient', age=60, gender='F')
        MRIAnalysis.objects.create(
            patient=self.patient, file='mri/uploads/a.png',
            status=MRIAnalysis.Status.COMPLETED)
        ECGAnalysis.objects.create(
            patient=self.patient, file='ecg/uploads/a.dat',
            status=ECGAnalysis.Status.COMPLETED)
        EchoAnalysis.objects.create(
            patient=self.patient, file='echo/uploads/a.avi',
            status=EchoAnalysis.Status.COMPLETED,
            result_ef=42.0, result_ef_category='reduced')
        EEGAnalysis.objects.create(
            patient=self.patient, file='eeg/uploads/a.edf',
            status=EEGAnalysis.Status.COMPLETED,
            result_dominant_pattern='Seizure', result_harmful=True)

    def test_history_includes_all_four_modalities(self):
        self.client.force_authenticate(user=self.doc_a)
        resp = self.client.get(f'/api/patients/{self.patient.pk}/history/')
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        data = resp.json()
        for key in ('mri_analyses', 'ecg_analyses', 'echo_analyses', 'eeg_analyses'):
            self.assertIn(key, data, msg=f'{key} missing from /history/')
            self.assertEqual(len(data[key]), 1, msg=f'{key}: {data.get(key)}')
        # Modality-specific fields are serialized (not just empty stubs).
        self.assertEqual(data['echo_analyses'][0]['result_ef'], 42.0)
        self.assertEqual(data['eeg_analyses'][0]['result_dominant_pattern'], 'Seizure')

    def test_history_echo_eeg_stay_doctor_scoped(self):
        # Doctor B cannot reach Doctor A's patient at all → no echo/eeg leak.
        self.client.force_authenticate(user=self.doc_b)
        resp = self.client.get(f'/api/patients/{self.patient.pk}/history/')
        self.assertEqual(resp.status_code, 404)
