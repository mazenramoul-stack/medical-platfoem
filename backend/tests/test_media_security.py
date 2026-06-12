"""Tests for signed, time-limited patient-media serving (core.media).

Locks in the fix for the unauthenticated-/media/ PHI exposure: media is served
ONLY with a valid, unexpired HMAC signature, and path traversal is refused.
"""

from __future__ import annotations

import os

from django.conf import settings
from django.test import SimpleTestCase

from core.media import signed_media_url


class SignedMediaTest(SimpleTestCase):
    REL = 'test_media_security/sample.txt'
    CONTENT = b'PHI-bytes-should-be-gated'

    def setUp(self):
        super().setUp()
        self.full = os.path.join(str(settings.MEDIA_ROOT), self.REL)
        os.makedirs(os.path.dirname(self.full), exist_ok=True)
        with open(self.full, 'wb') as fh:
            fh.write(self.CONTENT)

    def tearDown(self):
        try:
            os.remove(self.full)
            os.rmdir(os.path.dirname(self.full))
        except OSError:
            pass
        super().tearDown()

    def _path_with_query(self, url):
        # signed_media_url(None, ...) returns a relative '/media/...?exp=&sig='
        return url

    def test_valid_signature_serves_file(self):
        url = signed_media_url(None, self.REL)
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(b''.join(resp.streaming_content), self.CONTENT)

    def test_unsigned_request_is_forbidden(self):
        resp = self.client.get(f'{settings.MEDIA_URL}{self.REL}')
        self.assertEqual(resp.status_code, 403)

    def test_tampered_signature_is_forbidden(self):
        url = signed_media_url(None, self.REL)
        resp = self.client.get(url[:-3] + 'abc')  # corrupt the sig tail
        self.assertEqual(resp.status_code, 403)

    def test_expired_signature_is_forbidden(self):
        url = signed_media_url(None, self.REL, ttl=-10)  # already expired
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 403)

    def test_path_traversal_is_blocked(self):
        # A correctly-signed path that escapes MEDIA_ROOT must not serve.
        url = signed_media_url(None, '../core/settings.py')
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (403, 404))
