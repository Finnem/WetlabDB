"""HTTP hardening middleware for the FastAPI app."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_EXEMPT_PATHS = frozenset({"/api/login", "/api/health"})
MUTATION_HEADER = "x-wetlabdb-request"
MAX_BODY_BYTES = 10 * 1024 * 1024


class LimitBodySizeMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds :data:`MAX_BODY_BYTES`."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in MUTATING_METHODS:
            content_length = request.headers.get("content-length")
            if content_length is not None:
                try:
                    size = int(content_length)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": "Invalid Content-Length"},
                    )
                if size > MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Request body too large"},
                    )
        return await call_next(request)


class MutationHeaderMiddleware(BaseHTTPMiddleware):
    """Require ``X-WetlabDB-Request: 1`` on mutating ``/api/*`` calls (CSRF mitigation)."""

    def __init__(self, app, *, enabled: bool = True) -> None:
        super().__init__(app)
        self._enabled = enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        if self._enabled and self._requires_header(request):
            if request.headers.get(MUTATION_HEADER) != "1":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Missing mutation header"},
                )
        return await call_next(request)

    @staticmethod
    def _requires_header(request: Request) -> bool:
        if request.method not in MUTATING_METHODS:
            return False
        path = request.url.path
        if not path.startswith("/api/"):
            return False
        return path not in CSRF_EXEMPT_PATHS


__all__ = [
    "LimitBodySizeMiddleware",
    "MAX_BODY_BYTES",
    "MutationHeaderMiddleware",
]
