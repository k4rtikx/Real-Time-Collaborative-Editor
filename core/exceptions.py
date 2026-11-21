"""Custom application exceptions."""


class CollabEditError(Exception):
    """Base exception for all CollabEdit application errors."""


class PermissionDenied(CollabEditError):
    """Raised when a user does not have permission to perform an action."""


class DocumentNotFound(CollabEditError):
    """Raised when a document does not exist or is deleted."""


class RateLimitExceeded(CollabEditError):
    """Raised when a client exceeds the configured rate limit."""

    def __init__(self, retry_after: float = 0.0):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after:.1f} seconds.")


class WebSocketError(CollabEditError):
    """Raised when a WebSocket protocol error occurs."""

    def __init__(self, message: str, close_code: int = 4000):
        self.close_code = close_code
        super().__init__(message)
