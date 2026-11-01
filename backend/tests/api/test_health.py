"""GET /health: liveness for Docker and Traefik, and the commit that is actually running.

The promote job polls this endpoint after it fast-forwards `production` and waits
until ``version`` is the commit it promoted (INFRA-11). Without the field, a Dokploy
build that failed after promote left production 13.7 h behind the promoted commit
while CI, main and the production branch all said it was deployed.
"""

from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from majlisna.app import create_app
from majlisna.settings import Settings

RUNNING_COMMIT = "0f3c9a1b2d4e5f60718293a4b5c6d7e8f9012345"


def _app_on_test_database(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> FastAPI:
    """The real app, its health probe pointed at the test database."""
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("LOGFIRE_TOKEN", "")
    monkeypatch.setattr("majlisna.app._get_engine", AsyncMock(return_value=engine))
    return create_app(lifespan=None)


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest.fixture(name="health_app")
def get_health_app_fixture(monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine) -> FastAPI:
    """The app of an image built with `--build-arg GIT_SHA=<commit>` (ENV GIT_SHA)."""
    monkeypatch.setenv("GIT_SHA", RUNNING_COMMIT)
    return _app_on_test_database(monkeypatch, engine)


async def test_health_reports_the_running_commit(health_app: FastAPI):
    """The body names the commit baked into the image (ENV GIT_SHA), next to the DB status."""
    # Prepare
    expected_version = Settings().git_sha

    # Act
    async with _client(health_app) as client:
        response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert expected_version == RUNNING_COMMIT
    assert body["version"] == expected_version
    assert body["status"] == "healthy"
    assert body["db"] == "ok"
    assert datetime.fromisoformat(body["timestamp"]).tzinfo is not None


async def test_health_version_is_unknown_when_the_image_carries_no_commit(
    monkeypatch: pytest.MonkeyPatch, engine: AsyncEngine
):
    """A build without the GIT_SHA build arg says so, instead of claiming any commit."""
    # Prepare
    monkeypatch.delenv("GIT_SHA", raising=False)
    app = _app_on_test_database(monkeypatch, engine)

    # Act
    async with _client(app) as client:
        response = await client.get("/health")

    # Assert
    assert response.status_code == 200
    assert response.json()["version"] == Settings().git_sha == "unknown"


async def test_health_still_names_the_commit_when_the_database_is_down(
    monkeypatch: pytest.MonkeyPatch, health_app: FastAPI
):
    """A 503 keeps the version, so a deploy check can tell 'new build, DB down' from 'old build'."""
    # Prepare
    monkeypatch.setattr(
        "majlisna.app._get_engine", AsyncMock(side_effect=ConnectionRefusedError("database unreachable"))
    )

    # Act
    async with _client(health_app) as client:
        response = await client.get("/health")

    # Assert
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "error"
    assert body["version"] == RUNNING_COMMIT
