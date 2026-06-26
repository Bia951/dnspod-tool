class DnspodToolError(Exception):
    """Base exception for user-facing tool errors."""


class ConfigError(DnspodToolError):
    """Raised when credentials or local configuration are invalid."""


class CredentialNotFound(ConfigError):
    """Raised when no usable credential source can be found."""


class ApiError(DnspodToolError):
    """Raised when DNSPod or Tencent Cloud returns an API error."""
