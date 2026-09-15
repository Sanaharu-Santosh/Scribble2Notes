from __future__ import annotations


def test_health_reports_configured_engines(client):
    response = client.get("/api/health")
    assert response.status_code == 200

    body = response.json()
    assert body["status"] == "ok"
    # Phase 0 ships with both engines mocked so the app runs without credentials.
    assert body["ocr_engine"] == "mock"
    assert body["layout_engine"] == "mock"
    assert body["using_mocks"] is True
