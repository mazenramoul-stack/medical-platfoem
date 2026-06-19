"""Access-control tests for the assignment-based patient model.

The platform's #1 invariant (CLAUDE.md "Doctor isolation") is redefined here:
a doctor sees a patient iff a PatientAssignment links them — *not* a single owner
FK. A technician (back-office) sees everything. These tests lock that contract,
plus the anti-privilege-escalation rules (a doctor can never assign doctors or
self-elevate) and the technician-only doctors endpoint.

They run on the in-memory SQLite test DB (core/settings.py selects it when
'test' is in sys.argv) via the ORM + force_authenticate, so they execute in
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
from apps.patients.access import (
    get_patient_or_404,
    scope_by_patient,
    scope_patients,
    visible_patient_ids,
)
from apps.patients.models import Patient, PatientAssignment

User = get_user_model()


def make_patient(created_by, *doctors, full_name='P', age=50, gender='M'):
    """Create a patient and assign it to the given doctors."""
    p = Patient.objects.create(
        full_name=full_name, age=age, gender=gender, created_by=created_by)
    for doc in doctors:
        PatientAssignment.objects.create(patient=p, doctor=doc, assigned_by=created_by)
    return p


class RegistrationSecurityTest(APITestCase):
    """The public register endpoint may pick doctor/technician but never staff."""

    def setUp(self):
        cache.clear()

    def test_cannot_self_register_with_an_invalid_role(self):
        resp = self.client.post('/api/auth/register/', {
            'email': 'evil@example.com', 'password': 'StrongPass1!',
            'full_name': 'Evil User', 'role': 'admin',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, msg=resp.content)
        self.assertFalse(User.objects.filter(email='evil@example.com').exists())

    def test_cannot_self_register_as_staff_or_superuser(self):
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


class AccessHelperTest(APITestCase):
    """Unit-level coverage of the access helpers (the single source of truth)."""

    def setUp(self):
        self.doc_a = User.objects.create_user(
            email='a@x.com', password='p', full_name='A', role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='b@x.com', password='p', full_name='B', role=User.Role.DOCTOR)
        self.tech = User.objects.create_user(
            email='t@x.com', password='p', full_name='T', role=User.Role.TECHNICIAN)
        self.p_a = make_patient(self.doc_a, self.doc_a, full_name='PA')
        self.p_shared = make_patient(self.tech, self.doc_a, self.doc_b, full_name='PS')

    def test_technician_sees_all(self):
        self.assertIsNone(visible_patient_ids(self.tech))
        self.assertEqual(scope_patients(self.tech).count(), 2)

    def test_doctor_sees_only_assigned(self):
        ids = set(visible_patient_ids(self.doc_a))
        self.assertEqual(ids, {self.p_a.pk, self.p_shared.pk})
        self.assertEqual(set(scope_patients(self.doc_b).values_list('id', flat=True)),
                         {self.p_shared.pk})

    def test_get_patient_or_404_respects_scope(self):
        from django.http import Http404
        self.assertEqual(get_patient_or_404(self.doc_b, self.p_shared.pk).pk, self.p_shared.pk)
        with self.assertRaises(Http404):
            get_patient_or_404(self.doc_b, self.p_a.pk)

    def test_scope_by_patient_filters_analyses(self):
        mri = MRIAnalysis.objects.create(
            patient=self.p_a, file='mri/uploads/a.png', status=MRIAnalysis.Status.COMPLETED)
        self.assertEqual(scope_by_patient(self.tech, MRIAnalysis.objects.all()).count(), 1)
        self.assertEqual(scope_by_patient(self.doc_a, MRIAnalysis.objects.all()).count(), 1)
        self.assertEqual(scope_by_patient(self.doc_b, MRIAnalysis.objects.all()).count(), 0)
        _ = mri


class DoctorIsolationTest(APITestCase):
    """Doctor B is walled off from a patient assigned only to Doctor A."""

    def setUp(self):
        self.doc_a = User.objects.create_user(
            email='doc_a@example.com', password='PassA1!xx', full_name='Doctor A',
            role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='doc_b@example.com', password='PassB1!xx', full_name='Doctor B',
            role=User.Role.DOCTOR)
        self.patient_a = make_patient(self.doc_a, self.doc_a, full_name='Patient A')
        self.mri_a = MRIAnalysis.objects.create(
            patient=self.patient_a, file='mri/uploads/a.png',
            status=MRIAnalysis.Status.COMPLETED)

    def _as(self, user):
        self.client.force_authenticate(user=user)

    def test_b_cannot_retrieve_a_patient(self):
        self._as(self.doc_b)
        self.assertEqual(self.client.get(f'/api/patients/{self.patient_a.pk}/').status_code, 404)

    def test_b_list_excludes_a_patient(self):
        self._as(self.doc_b)
        resp = self.client.get('/api/patients/')
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.patient_a.pk, [p['id'] for p in resp.data])

    def test_b_cannot_delete_a_patient(self):
        self._as(self.doc_b)
        self.assertEqual(self.client.delete(f'/api/patients/{self.patient_a.pk}/').status_code, 404)
        self.assertTrue(Patient.objects.filter(pk=self.patient_a.pk).exists())

    def test_b_cannot_view_a_patient_history(self):
        self._as(self.doc_b)
        self.assertEqual(self.client.get(f'/api/patients/{self.patient_a.pk}/history/').status_code, 404)

    def test_b_cannot_retrieve_a_mri(self):
        self._as(self.doc_b)
        self.assertEqual(self.client.get(f'/api/mri/{self.mri_a.pk}/').status_code, 404)

    def test_b_mri_list_filtered_to_a_patient_is_empty(self):
        self._as(self.doc_b)
        resp = self.client.get(f'/api/mri/?patient_id={self.patient_a.pk}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 0)

    def test_b_cannot_delete_a_mri(self):
        self._as(self.doc_b)
        self.assertEqual(self.client.delete(f'/api/mri/{self.mri_a.pk}/').status_code, 404)
        self.assertTrue(MRIAnalysis.objects.filter(pk=self.mri_a.pk).exists())

    def test_b_cannot_upload_to_a_patient(self):
        self._as(self.doc_b)
        png = SimpleUploadedFile('x.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')
        resp = self.client.post('/api/mri/upload/', {
            'patient_id': self.patient_a.pk, 'file': png,
        }, format='multipart')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.patient_a.mri_analyses.count(), 1)

    def test_a_can_access_own_assigned_patient_and_mri(self):
        self._as(self.doc_a)
        self.assertEqual(self.client.get(f'/api/patients/{self.patient_a.pk}/').status_code, 200)
        self.assertEqual(self.client.get(f'/api/mri/{self.mri_a.pk}/').status_code, 200)


class SharedPatientTest(APITestCase):
    """A patient assigned to several doctors is visible to all of them."""

    def setUp(self):
        self.tech = User.objects.create_user(
            email='t@x.com', password='p', full_name='Tech', role=User.Role.TECHNICIAN)
        self.doc_a = User.objects.create_user(
            email='a@x.com', password='p', full_name='A', role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='b@x.com', password='p', full_name='B', role=User.Role.DOCTOR)
        self.shared = make_patient(self.tech, self.doc_a, self.doc_b, full_name='Shared')

    def test_both_doctors_see_the_shared_patient(self):
        for doc in (self.doc_a, self.doc_b):
            self.client.force_authenticate(user=doc)
            resp = self.client.get(f'/api/patients/{self.shared.pk}/')
            self.assertEqual(resp.status_code, 200, msg=f'{doc.email}: {resp.content}')
            self.assertIn(self.shared.pk, [p['id'] for p in self.client.get('/api/patients/').data])

    def test_serializer_exposes_both_assigned_doctors(self):
        self.client.force_authenticate(user=self.doc_a)
        resp = self.client.get(f'/api/patients/{self.shared.pk}/')
        ids = {d['id'] for d in resp.data['doctors']}
        self.assertEqual(ids, {self.doc_a.pk, self.doc_b.pk})


class TechnicianBackOfficeTest(APITestCase):
    """A technician sees/manages every patient and assigns doctors."""

    def setUp(self):
        self.tech = User.objects.create_user(
            email='t@x.com', password='p', full_name='Tech', role=User.Role.TECHNICIAN)
        self.doc_a = User.objects.create_user(
            email='a@x.com', password='p', full_name='A', role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='b@x.com', password='p', full_name='B', role=User.Role.DOCTOR)
        # A patient that belongs to doc_a only.
        self.p_a = make_patient(self.doc_a, self.doc_a, full_name='Owned by A')

    def test_technician_sees_all_patients(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.get('/api/patients/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(self.p_a.pk, [p['id'] for p in resp.data])

    def test_technician_creates_patient_and_assigns_doctors(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.post('/api/patients/', {
            'full_name': 'New Intake', 'age': 40, 'gender': 'F',
            'doctor_ids': [self.doc_a.pk, self.doc_b.pk],
        }, format='json')
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        self.assertEqual({d['id'] for d in resp.data['doctors']}, {self.doc_a.pk, self.doc_b.pk})
        pid = resp.data['id']
        # Both assigned doctors now see it; created_by is the technician.
        self.assertEqual(Patient.objects.get(pk=pid).created_by_id, self.tech.pk)
        self.client.force_authenticate(user=self.doc_b)
        self.assertEqual(self.client.get(f'/api/patients/{pid}/').status_code, 200)

    def test_technician_assigning_a_non_doctor_is_rejected(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.post('/api/patients/', {
            'full_name': 'Bad', 'age': 30, 'gender': 'M',
            'doctor_ids': [self.tech.pk],  # a technician is not a doctor
        }, format='json')
        self.assertEqual(resp.status_code, 400, msg=resp.content)

    def test_technician_can_reassign_via_patch(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.patch(f'/api/patients/{self.p_a.pk}/',
                                 {'doctor_ids': [self.doc_b.pk]}, format='json')
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        self.assertEqual({d['id'] for d in resp.data['doctors']}, {self.doc_b.pk})
        # doc_a no longer sees it; doc_b now does.
        self.client.force_authenticate(user=self.doc_a)
        self.assertEqual(self.client.get(f'/api/patients/{self.p_a.pk}/').status_code, 404)
        self.client.force_authenticate(user=self.doc_b)
        self.assertEqual(self.client.get(f'/api/patients/{self.p_a.pk}/').status_code, 200)


class AntiEscalationTest(APITestCase):
    """A doctor can never assign doctors or self-elevate access."""

    def setUp(self):
        self.doc_a = User.objects.create_user(
            email='a@x.com', password='p', full_name='A', role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='b@x.com', password='p', full_name='B', role=User.Role.DOCTOR)

    def test_doctor_create_is_auto_self_assigned(self):
        self.client.force_authenticate(user=self.doc_a)
        resp = self.client.post('/api/patients/', {
            'full_name': 'Mine', 'age': 33, 'gender': 'M',
        }, format='json')
        self.assertEqual(resp.status_code, 201, msg=resp.content)
        self.assertEqual({d['id'] for d in resp.data['doctors']}, {self.doc_a.pk})
        # doc_b cannot see doc_a's self-created patient.
        self.client.force_authenticate(user=self.doc_b)
        self.assertEqual(self.client.get(f"/api/patients/{resp.data['id']}/").status_code, 404)

    def test_doctor_cannot_assign_doctors_on_create(self):
        self.client.force_authenticate(user=self.doc_a)
        resp = self.client.post('/api/patients/', {
            'full_name': 'Grab', 'age': 33, 'gender': 'M',
            'doctor_ids': [self.doc_a.pk, self.doc_b.pk],
        }, format='json')
        self.assertEqual(resp.status_code, 400, msg=resp.content)

    def test_doctor_cannot_assign_doctors_on_update(self):
        self.client.force_authenticate(user=self.doc_a)
        p = make_patient(self.doc_a, self.doc_a, full_name='Mine')
        resp = self.client.patch(f'/api/patients/{p.pk}/',
                                 {'doctor_ids': [self.doc_b.pk]}, format='json')
        self.assertEqual(resp.status_code, 400, msg=resp.content)


class DoctorsEndpointTest(APITestCase):
    """GET /api/auth/doctors/ is technician-only."""

    def setUp(self):
        self.tech = User.objects.create_user(
            email='t@x.com', password='p', full_name='Tech', role=User.Role.TECHNICIAN)
        self.doc = User.objects.create_user(
            email='d@x.com', password='p', full_name='Doc', role=User.Role.DOCTOR)

    def test_technician_can_list_doctors(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.get('/api/auth/doctors/')
        self.assertEqual(resp.status_code, 200, msg=resp.content)
        emails = {d['email'] for d in resp.data}
        self.assertIn('d@x.com', emails)
        self.assertNotIn('t@x.com', emails)  # technicians aren't doctors

    def test_doctor_gets_403(self):
        self.client.force_authenticate(user=self.doc)
        self.assertEqual(self.client.get('/api/auth/doctors/').status_code, 403)


class PatientHistoryAggregateTest(APITestCase):
    """The /history/ aggregate returns all four modalities, assignment-scoped."""

    def setUp(self):
        super().setUp()
        self.doc_a = User.objects.create_user(
            email='hist_a@example.com', password='PassA1!xx', full_name='Hist A',
            role=User.Role.DOCTOR)
        self.doc_b = User.objects.create_user(
            email='hist_b@example.com', password='PassB1!xx', full_name='Hist B',
            role=User.Role.DOCTOR)
        self.patient = make_patient(self.doc_a, self.doc_a, full_name='Hist Patient',
                                    age=60, gender='F')
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
        self.assertEqual(data['echo_analyses'][0]['result_ef'], 42.0)
        self.assertEqual(data['eeg_analyses'][0]['result_dominant_pattern'], 'Seizure')

    def test_history_stays_assignment_scoped(self):
        self.client.force_authenticate(user=self.doc_b)
        resp = self.client.get(f'/api/patients/{self.patient.pk}/history/')
        self.assertEqual(resp.status_code, 404)
