"""The per-user rate-limit key and the 429 envelope (majlisna.api.rate_limit)."""

import json
import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from limits import parse
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit
from starlette.requests import Request

from majlisna.api.constants import RATE_LIMIT_USER_KEY_PREFIX
from majlisna.api.controllers.auth import AuthController
from majlisna.api.models.table import User
from majlisna.api.rate_limit import rate_limit_exceeded_handler, user_or_ip_key
from majlisna.api.schemas.auth import TokenPayload
from majlisna.dependencies import get_current_user


def _request(client_host: str = "203.0.113.7") -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": [], "client": (client_host, 1234)})


def test_a_signed_in_caller_is_counted_per_user():
    """Two phones on one home connection: same IP, two keys."""
    # Arrange
    first, second = _request(), _request()
    first.state.user_id = "u-1"
    second.state.user_id = "u-2"

    # Act
    keys = {user_or_ip_key(first), user_or_ip_key(second)}

    # Assert
    assert keys == {f"{RATE_LIMIT_USER_KEY_PREFIX}u-1", f"{RATE_LIMIT_USER_KEY_PREFIX}u-2"}


def test_an_anonymous_caller_is_counted_per_ip():
    """Without an authenticated user the key falls back to the remote address."""
    # Act
    key = user_or_ip_key(_request("198.51.100.4"))

    # Assert
    assert key == "198.51.100.4"


@pytest.mark.asyncio
async def test_get_current_user_records_the_verified_user_on_the_request():
    """The real dependency is what makes the per-user key work: it records the id, and
    only after the token has been checked against the account."""
    # Arrange
    user_id = uuid.uuid4()
    controller = Mock(spec=AuthController)
    controller.decode_token = Mock(
        return_value=TokenPayload(sub=str(user_id), email="owner@example.com", exp=0, type="access")
    )
    controller.get_user_by_email = AsyncMock(
        return_value=User(id=user_id, username="owner", email_address="owner@example.com", password="hashed-pw-123")
    )
    request = _request()

    # Act
    user = await get_current_user(request, "a.b.c", controller)

    # Assert
    assert user.id == user_id
    assert request.state.user_id == str(user_id)
    assert user_or_ip_key(request) == f"{RATE_LIMIT_USER_KEY_PREFIX}{user_id}"


@pytest.mark.asyncio
async def test_the_429_handler_answers_the_standard_error_envelope():
    """A translatable `error_key`, the English fallback and the limit — not slowapi's bare string."""
    # Arrange
    limit = Limit(parse("30/minute"), user_or_ip_key, None, False, None, None, None, 1, False)
    exc = RateLimitExceeded(limit)
    request = _request()

    # Act
    response = await rate_limit_exceeded_handler(request, exc)

    # Assert
    assert response.status_code == 429
    body = json.loads(bytes(response.body))
    assert body["error_key"] == "errors.api.rateLimitExceeded"
    assert body["error"] == "RateLimitExceededError"
    assert body["message"] == "Too many requests. Please wait a moment and try again."
    assert body["details"] == {"limit": "30 per 1 minute"}
