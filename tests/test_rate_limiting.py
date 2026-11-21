"""
Unit tests for Token Bucket rate limiter.
"""
from unittest.mock import MagicMock, patch
from django.test import TestCase

from core.rate_limiting import TokenBucket


class TokenBucketTest(TestCase):
    """Test Token Bucket rate limiting logic."""

    def _make_limiter(self, capacity=10, refill_rate=1.0):
        """Create a TokenBucket with a mocked Redis client."""
        mock_redis = MagicMock()
        # Mock register_script to return a callable script mock
        mock_script = MagicMock()
        mock_redis.register_script.return_value = mock_script
        limiter = TokenBucket(mock_redis, capacity=capacity, refill_rate=refill_rate, key_prefix="test")
        return limiter, mock_script

    def test_allowed_when_tokens_available(self):
        """Returns (True, 0.0) when tokens are available."""
        limiter, mock_script = self._make_limiter()
        mock_script.return_value = [1, 0]
        allowed, retry = limiter.is_allowed("user1")
        self.assertTrue(allowed)
        self.assertEqual(retry, 0.0)

    def test_denied_when_no_tokens(self):
        """Returns (False, retry_after) when bucket is empty."""
        limiter, mock_script = self._make_limiter()
        mock_script.return_value = [0, 5000]  # 5000ms = 5s
        allowed, retry = limiter.is_allowed("user1")
        self.assertFalse(allowed)
        self.assertAlmostEqual(retry, 5.0, places=1)

    def test_fail_open_on_redis_unavailable(self):
        """Allows request when Redis is unavailable (fail-open)."""
        import redis
        mock_redis = MagicMock()
        mock_script = MagicMock()
        mock_script.side_effect = redis.ConnectionError("Redis unavailable")
        mock_redis.register_script.return_value = mock_script
        limiter = TokenBucket(mock_redis, 10, 1.0, "test")
        allowed, retry = limiter.is_allowed("user1")
        self.assertTrue(allowed)
        self.assertEqual(retry, 0.0)


class RateLimitMiddlewareTest(TestCase):
    """Test rate limit middleware integration."""

    def test_health_check_not_rate_limited(self):
        """Health check endpoint bypasses rate limiting."""
        from django.test import Client
        client = Client()
        # Health check should always return a response (not 429)
        # Even without Redis, the endpoint itself is not gated by rate limiting
        response = client.get("/health/")
        self.assertNotEqual(response.status_code, 429)
