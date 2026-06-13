"""Authentication regression tests.

These guard security-critical behaviour of the public auth surface. The
registration role-escalation test in particular locks in the fix for the
mass-assignment flaw: an anonymous POST to /api/auth/register/ must NEVER be
able to mint a non-doctor account, because the role is embedded in the JWT.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


class RegistrationRoleEscalationTest(APITestCase):
    """A self-registering client must not be able to choose its own role."""

    def setUp(self):
        self.url = reverse('authentication:register')
        self.payload = {
            'email': 'attacker@test.com',
            'password': 'StrongPass123!',
            'full_name': 'A Ttacker',
        }

    def test_register_creates_a_doctor_by_default(self):
        resp = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertEqual(resp.data['user']['role'], User.Role.DOCTOR)
        user = User.objects.get(email=self.payload['email'])
        self.assertEqual(user.role, User.Role.DOCTOR)

    def test_register_cannot_self_elevate_to_admin(self):
        # Malicious payload trying to mass-assign an admin role.
        resp = self.client.post(
            self.url, {**self.payload, 'role': 'admin'}, format='json',
        )
        # The request still succeeds (role is silently ignored, not rejected)...
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        # ...but the created account is a DOCTOR, never an admin.
        self.assertEqual(resp.data['user']['role'], User.Role.DOCTOR)
        user = User.objects.get(email=self.payload['email'])
        self.assertEqual(user.role, User.Role.DOCTOR)
        self.assertNotEqual(user.role, User.Role.ADMIN)


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
