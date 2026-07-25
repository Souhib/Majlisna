"""Test configuration for API route tests."""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(name="test_app")
def get_test_app_fixture() -> FastAPI:
    """Create a test FastAPI application instance without lifespan."""
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    # Empty, not "fake". `_configure_observability` only calls logfire.configure
    # when the token is truthy, and `send_to_logfire="if-token-present"` means a
    # placeholder token is still *present* — so every test that built the app
    # attempted a real export and collected `401 Invalid token`, along with the
    # network round-trip and the warning noise. Empty disables it outright, while
    # still shadowing any real token a developer has in their environment.
    os.environ["LOGFIRE_TOKEN"] = ""

    from majlisna.app import create_app  # noqa: PLC0415

    return create_app(lifespan=None)


@pytest.fixture(name="client")
def get_test_client_fixture(test_app: FastAPI) -> TestClient:
    """Create a TestClient instance for making HTTP requests."""
    return TestClient(test_app)
