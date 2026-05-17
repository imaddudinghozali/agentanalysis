from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_app


def test_dashboard_origin_can_preflight_analyze_endpoint():
    # Regression: ISSUE-001 - dashboard refresh was blocked by missing CORS headers.
    # Found by /qa on 2026-05-17.
    # Report: .gstack/qa-reports/qa-report-localhost-2026-05-17.md
    client = TestClient(create_app())

    response = client.options(
        "/api/analyze",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert "POST" in response.headers["access-control-allow-methods"]
