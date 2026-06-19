"""IsTechnician gate + routing tests for the conversion endpoint.

These do not exercise the actual converters (a technician with no file is
rejected for the missing file BEFORE any converter runs), so they isolate the
permission/routing behaviour and run with no heavy libs.
"""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class IsTechnicianGateTest(APITestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            email='doc@test.com', password='PassA1!xx', full_name='Doc',
            role=User.Role.DOCTOR)
        self.tech = User.objects.create_user(
            email='tech@test.com', password='PassB1!xx', full_name='Tech',
            role=User.Role.TECHNICIAN)
        self.url = '/api/convert/mri/'

    def test_anonymous_is_rejected(self):
        resp = self.client.post(self.url, {}, format='multipart')
        self.assertIn(resp.status_code,
                      (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_doctor_gets_403(self):
        self.client.force_authenticate(user=self.doctor)
        resp = self.client.post(self.url, {}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)

    def test_doctor_gets_403_even_with_a_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_authenticate(user=self.doctor)
        f = SimpleUploadedFile('scan.dcm', b'not really a dicom', content_type='application/dicom')
        resp = self.client.post(self.url, {'file': f}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN, resp.content)

    def test_technician_passes_the_gate(self):
        # No file -> 400 (the gate let the technician through; the request fails
        # later for the missing file, NOT 403).
        self.client.force_authenticate(user=self.tech)
        resp = self.client.post(self.url, {}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertEqual(resp.data['status'], 'failed')
        self.assertEqual(resp.data['error_type'], 'MissingFile')

    def test_unknown_modality_404s(self):
        self.client.force_authenticate(user=self.tech)
        resp = self.client.post('/api/convert/bogus/', {}, format='multipart')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
