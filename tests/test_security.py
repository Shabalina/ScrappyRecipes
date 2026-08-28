"""Tests for app/core/security.py — the X-API-Key gate on /api/v1/... routes.

`/health` stays public for container health probes. Every /api/v1/... route
must reject a missing or wrong key and accept the correct one; exercised here
via slot-candidates as a representative protected GET, with `get_db` and
`get_slot_candidates` stubbed so neither Postgres nor the embedding call runs.
"""
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from tests.conftest import TEST_API_KEY

PROTECTED_ROUTE = "/api/v1/menu/slot-candidates"


@pytest.fixture
def api(monkeypatch, mock_db_session):
    import app.main as main

    monkeypatch.setattr("app.routers.menu.get_slot_candidates", AsyncMock(return_value=[]))

    async def override_get_db():
        yield mock_db_session

    main.app.dependency_overrides[main.get_db] = override_get_db
    try:
        yield TestClient(main.app)
    finally:
        main.app.dependency_overrides.clear()


class TestHealthCheckIsPublic:
    def test_health_check_requires_no_api_key(self, api):
        response = api.get("/health")

        assert response.status_code == 200


class TestProtectedEndpoints:
    def test_missing_api_key_is_forbidden(self, api):
        response = api.get(PROTECTED_ROUTE, params={"q": "soup"})

        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid or missing API key"

    def test_wrong_api_key_is_forbidden(self, api):
        response = api.get(
            PROTECTED_ROUTE, params={"q": "soup"}, headers={"X-API-Key": "wrong-key"}
        )

        assert response.status_code == 403

    def test_correct_api_key_is_allowed(self, api):
        response = api.get(
            PROTECTED_ROUTE, params={"q": "soup"}, headers={"X-API-Key": TEST_API_KEY}
        )

        assert response.status_code == 200
