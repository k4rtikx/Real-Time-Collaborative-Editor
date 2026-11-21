"""
Integration tests for health check endpoint.
"""
from django.test import TestCase


class HealthCheckTest(TestCase):
    """Test /health/ endpoint."""

    def test_health_check_returns_json(self):
        """Health check returns JSON with status field."""
        response = self.client.get("/health/")
        self.assertIn(response.status_code, [200, 503])
        data = response.json()
        self.assertIn("status", data)
        self.assertIn("db", data)
        self.assertIn("redis", data)

    def test_health_check_no_auth_required(self):
        """Health check is accessible without authentication."""
        response = self.client.get("/health/")
        # Should not redirect to login
        self.assertNotEqual(response.status_code, 302)
