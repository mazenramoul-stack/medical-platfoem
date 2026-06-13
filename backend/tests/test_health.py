"""The /api/health/ probe returns 200 + a status/database/weights payload."""

from django.test import TestCase


class HealthEndpointTest(TestCase):
    def test_health_reports_ok_when_db_is_up(self):
        resp = self.client.get('/api/health/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['database'], 'ok')
        self.assertIn('weights', data)
        # weight keys are always reported (values depend on what's on disk)
        for key in ('mri_classifier', 'ecg_finetuned', 'echonet', 'biot_iiic_head'):
            self.assertIn(key, data['weights'])

    def test_health_needs_no_auth(self):
        # No Authorization header set — must still succeed (it's a public probe).
        self.assertEqual(self.client.get('/api/health/').status_code, 200)
