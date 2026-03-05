"""Test configuration for API route tests."""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(name="test_app")
def get_test_app_fixture() -> FastAPI:
    """Create a test FastAPI application instance without lifespan."""
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["LOGFIRE_TOKEN"] = "fake"

    from ipg.app import create_app  # noqa: PLC0415

    return create_app(lifespan=None)


@pytest.fixture(name="client")
def get_test_client_fixture(test_app: FastAPI) -> TestClient:
    """Create a TestClient instance for making HTTP requests."""
    return TestClient(test_app)
