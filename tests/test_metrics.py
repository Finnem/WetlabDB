"""Metrics exposition tests."""

from __future__ import annotations

from wetlabdb.api.metrics import prometheus_text, record_http_request, record_operation, reset_for_tests


def test_prometheus_text_format():
    reset_for_tests()
    record_http_request(method="GET", path="/api/health", status=200)
    from wetlabdb.api.metrics import record_http_duration, record_storage_error

    record_http_duration(method="GET", path="/api/health", status=200, duration_ms=12.5)
    record_storage_error("readiness.list_databases")
    record_operation("search.similarity")
    text = prometheus_text()
    assert "wetlabdb_http_requests_total" in text
    assert "wetlabdb_http_request_duration_ms_bucket" in text
    assert "wetlabdb_storage_errors_total" in text
    assert "wetlabdb_operations_total" in text
    assert "search.similarity" in text
    assert text.endswith("\n")
