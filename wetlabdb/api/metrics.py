"""In-process request and operation counters (P2 observability)."""

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any

_lock = threading.Lock()
_request_total: dict[str, int] = defaultdict(int)
_request_errors: int = 0
_operation_total: dict[str, int] = defaultdict(int)
_storage_errors: dict[str, int] = defaultdict(int)

# Prometheus histogram buckets (milliseconds), upper bounds inclusive via le= label.
_LATENCY_BUCKET_BOUNDS_MS = (10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0)
_latency_buckets: dict[str, list[int]] = defaultdict(lambda: [0] * (len(_LATENCY_BUCKET_BOUNDS_MS) + 1))


def _latency_bucket_index(duration_ms: float) -> int:
    for index, bound in enumerate(_LATENCY_BUCKET_BOUNDS_MS):
        if duration_ms <= bound:
            return index
    return len(_LATENCY_BUCKET_BOUNDS_MS)


def record_http_request(*, method: str, path: str, status: int) -> None:
    key = f"{method} {path} {status // 100}xx"
    with _lock:
        _request_total[key] += 1
        if status >= 500:
            _request_errors += 1


def record_http_duration(*, method: str, path: str, status: int, duration_ms: float) -> None:
    route = f"{method} {path} {status // 100}xx"
    bucket = _latency_bucket_index(duration_ms)
    with _lock:
        _latency_buckets[route][bucket] += 1


def record_operation(name: str) -> None:
    with _lock:
        _operation_total[name] += 1


def record_storage_error(context: str) -> None:
    with _lock:
        _storage_errors[context] += 1


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "http_requests": dict(_request_total),
            "http_errors_5xx": _request_errors,
            "operations": dict(_operation_total),
            "storage_errors": dict(_storage_errors),
            "http_latency_buckets": {k: list(v) for k, v in _latency_buckets.items()},
        }


def prometheus_text() -> str:
    """Render counters in Prometheus exposition format."""
    snap = snapshot()
    lines = [
        "# HELP wetlabdb_http_errors_5xx Total HTTP 5xx responses.",
        "# TYPE wetlabdb_http_errors_5xx counter",
        f"wetlabdb_http_errors_5xx {snap['http_errors_5xx']}",
    ]
    for key, value in sorted(snap["http_requests"].items()):
        escaped = str(key).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'wetlabdb_http_requests_total{{route="{escaped}"}} {value}')

    lines.append("# HELP wetlabdb_http_request_duration_ms Request latency histogram buckets.")
    lines.append("# TYPE wetlabdb_http_request_duration_ms histogram")
    bounds = list(_LATENCY_BUCKET_BOUNDS_MS)
    for route, counts in sorted(snap["http_latency_buckets"].items()):
        escaped_route = str(route).replace("\\", "\\\\").replace('"', '\\"')
        cumulative = 0
        for index, count in enumerate(counts):
            cumulative += count
            le_label = str(bounds[index]) if index < len(bounds) else "+Inf"
            lines.append(
                f'wetlabdb_http_request_duration_ms_bucket{{route="{escaped_route}",le="{le_label}"}} {cumulative}'
            )
        total = sum(counts)
        lines.append(
            f'wetlabdb_http_request_duration_ms_count{{route="{escaped_route}"}} {total}'
        )

    lines.append("# HELP wetlabdb_storage_errors_total Storage backend failures by context.")
    lines.append("# TYPE wetlabdb_storage_errors_total counter")
    for context, value in sorted(snap["storage_errors"].items()):
        escaped = str(context).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'wetlabdb_storage_errors_total{{context="{escaped}"}} {value}')

    lines.append("# HELP wetlabdb_operations_total Application operation counters.")
    lines.append("# TYPE wetlabdb_operations_total counter")
    for name, value in sorted(snap["operations"].items()):
        escaped = str(name).replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'wetlabdb_operations_total{{operation="{escaped}"}} {value}')
    return "\n".join(lines) + "\n"


def reset_for_tests() -> None:
    with _lock:
        _request_total.clear()
        _request_errors = 0
        _operation_total.clear()
        _storage_errors.clear()
        _latency_buckets.clear()


__all__ = [
    "prometheus_text",
    "record_http_duration",
    "record_http_request",
    "record_operation",
    "record_storage_error",
    "reset_for_tests",
    "snapshot",
]
