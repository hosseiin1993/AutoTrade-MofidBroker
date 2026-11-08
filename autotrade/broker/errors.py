class EasyApiError(RuntimeError):
    """API call failed — orchestration may fall back or abort."""


class ApiAuthError(EasyApiError):
    """HTTP 401 — token expired or rejected."""
