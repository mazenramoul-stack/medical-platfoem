"""Authentication regression tests.

These guard security-critical behaviour of the public auth surface. The
registration tests lock in the role contract: an anonymous POST to
/api/auth/register/ may choose between the two self-service roles
(doctor / technician) but must NEVER be able to grant itself Django staff /
superuser access — those control the Django admin and stay server-controlled,
and the role is embedded in the JWT.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class RegistrationRoleTest(APITestCase):
    """Self-registration may pick doctor or technician, nothing more privileged."""

    def setUp(self):
        # The register endpoint is throttled (5/min) via the shared LocMemCache,
        # which persists across tests in one process. Clear it so each test gets
        # a fresh budget and one test's POSTs don't 429 the next.
        cache.clear()
        self.url = reverse('authentication:register')
        self.payload = {
            'email': 'new@test.com',
            'password': 'StrongPass123!',
            'full_name': 'New User',
        }

    def test_register_creates_a_doctor_by_default(self):
        resp = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.data['user']['role'], User.Role.DOCTOR)
        user = User.objects.get(email=self.payload['email'])
        self.assertEqual(user.role, User.Role.DOCTOR)

    def test_register_can_create_a_technician(self):
        resp = self.client.post(
            self.url, {**self.payload, 'role': 'technician'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        # The chosen role is honoured (the anti-elevation guard now only blocks
        # staff/superuser, not the doctor/technician choice).
        self.assertEqual(resp.data['user']['role'], User.Role.TECHNICIAN)
        user = User.objects.get(email=self.payload['email'])
        self.assertEqual(user.role, User.Role.TECHNICIAN)

    def test_register_rejects_an_invalid_role(self):
        # 'admin' is no longer a role; any value outside {doctor, technician}
        # is a 400, and no account is created.
        resp = self.client.post(
            self.url, {**self.payload, 'role': 'admin'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST, resp.content)
        self.assertFalse(User.objects.filter(email=self.payload['email']).exists())

    def test_register_cannot_grant_staff_or_superuser(self):
        # Malicious payload trying to mass-assign Django staff/superuser. The
        # request still succeeds (those fields are simply ignored) but the
        # created account has neither flag.
        resp = self.client.post(
            self.url,
            {**self.payload, 'role': 'technician',
             'is_staff': True, 'is_superuser': True},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        user = User.objects.get(email=self.payload['email'])
        self.assertEqual(user.role, User.Role.TECHNICIAN)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)


class CreateSuperuserRoleTest(APITestCase):
    """create_superuser mints a technician with Django staff + superuser flags."""

    def test_create_superuser_defaults_to_technician(self):
        su = User.objects.create_superuser(
            email='root@test.com', password='StrongPass123!', full_name='Root')
        self.assertEqual(su.role, User.Role.TECHNICIAN)
        # Django-admin access is independent of the app role field.
        self.assertTrue(su.is_staff)
        self.assertTrue(su.is_superuser)


class LogoutRevocationTest(APITestCase):
    """Logout must blacklist the refresh token so it can no longer be used."""

    def setUp(self):
        # Create the user + tokens via the ORM (no HTTP register) to avoid the
        # register rate-throttle in the shared test process.
        self.user = User.objects.create_user(
            email='logout@test.com', password='x', full_name='L O', role='doctor')

    def _tokens(self):
        r = RefreshToken.for_user(self.user)
        return str(r.access_token), str(r)

    def test_logout_blacklists_refresh_token(self):
        access, refresh = self._tokens()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        out = self.client.post(reverse('authentication:logout'), {'refresh': refresh}, format='json')
        self.assertEqual(out.status_code, status.HTTP_205_RESET_CONTENT, out.content)

        # The blacklisted refresh token can no longer be exchanged for an access token.
        self.client.credentials()  # drop auth header
        r = self.client.post(reverse('authentication:token_refresh'), {'refresh': refresh}, format='json')
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requires_a_refresh_token(self):
        access, _ = self._tokens()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        out = self.client.post(reverse('authentication:logout'), {}, format='json')
        self.assertEqual(out.status_code, status.HTTP_400_BAD_REQUEST)
