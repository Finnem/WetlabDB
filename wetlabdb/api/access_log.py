"""Structured access logging and HTTP metrics."""

from __future__ import annotations

import json
import logging
import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from wetlabdb.api.metrics import record_http_duration, record_http_request

_log = logging.getLogger("wetlabdb.access")


def _metric_path(path: str) -> str:
    path = re.sub(r"/api/databases/[^/]+", "/api/databases/:db", path)
    path = re.sub(r"/collections/[^/]+", "/collections/:coll", path)
    path = re.sub(r"/compounds/[^/]+", "/compounds/:id", path)
    return path


class AccessLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path = request.url.path
            if path.startswith("/api/"):
                record_http_request(method=request.method, path=_metric_path(path), status=status)
                record_http_duration(
                    method=request.method,
                    path=_metric_path(path),
                    status=status,
                    duration_ms=duration_ms,
                )
            payload = {
                "event": "http.access",
                "method": request.method,
                "path": path,
                "status": status,
                "duration_ms": duration_ms,
                "request_id": getattr(request.state, "request_id", None),
            }
            _log.info(json.dumps(payload, ensure_ascii=False))


__all__ = ["AccessLogMiddleware"]
