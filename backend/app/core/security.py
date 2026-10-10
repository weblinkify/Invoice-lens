"""API-key auth. Demo mode leaves the API open."""

import hmac

from fastapi import Request
from fastapi.security import APIKeyHeader

from app.core.errors import AppError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(request: Request) -> None:
    settings = request.app.state.services.settings
    if settings.demo_mode:
        return
    supplied = request.headers.get("X-API-Key", "")
    expected = settings.api_key or ""
    if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise AppError(401, "Missing or invalid X-API-Key header", code="unauthorized")
