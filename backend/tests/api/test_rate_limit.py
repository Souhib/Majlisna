"""The rate-limit keys (client address, user, refresh account) and the 429 envelope (majlisna.api.rate_limit)."""

import json
from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from jose import jwt
from limits import parse
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from majlisna.api.constants import RATE_LIMIT_USER_KEY_PREFIX
from majlisna.api.controllers.auth import AuthController
from majlisna.api.rate_limit import (
    build_limiter,
    client_ip_key,
    limiter,
    rate_limit_exceeded_handler,
    refresh_sub_key,
    user_or_ip_key,
)
from majlisna.dependencies import get_current_user, get_session, get_settings
from majlisna.settings import Settings


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
async def test_get_current_user_records_the_verified_user_on_the_request(auth_controller: AuthController, create_user):
    """The real dependency is what makes the per-user key work: it records the id, and
    only after the token has been checked against the account."""
    # Arrange — a real account and a real access token (no decode_token mock: TQ-01)
    owner = await create_user(username="owner", email="owner@example.com")
    user_id = owner.id
    token = auth_controller.create_access_token(str(user_id), owner.email_address)
    request = _request()

    # Act
    user = await get_current_user(request, token, auth_controller)

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


# ─── SEC F03 / INFRA-07 / PD-07: the client address behind Cloudflare ─────

CLOUDFLARE_EDGE = "162.158.12.34"  # inside 162.158.0.0/15
CLOUDFLARE_EDGE_V6 = "2606:4700:10::6816:1234"  # inside 2606:4700::/32
VISITOR = "198.51.100.9"


def _request_with(client_host: str, headers: dict[str, str]) -> Request:
    raw = [(name.lower().encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "method": "POST", "path": "/", "headers": raw, "client": (client_host, 1234)})


def test_a_public_peer_cannot_choose_its_key_with_proxy_headers():
    """A direct caller (not Cloudflare) writing CF-Connecting-IP / X-Forwarded-For keeps its own key."""
    # Prepare
    honest = _request_with("203.0.113.7", {})
    forged = _request_with("203.0.113.7", {"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "5.6.7.8"})

    # Act / Assert
    assert client_ip_key(honest) == "203.0.113.7"
    assert client_ip_key(forged) == "203.0.113.7"


@pytest.mark.parametrize("edge", [CLOUDFLARE_EDGE, CLOUDFLARE_EDGE_V6, f"::ffff:{CLOUDFLARE_EDGE}"])
def test_a_cloudflare_peer_is_keyed_on_the_visitor_it_names(edge: str):
    """Behind Cloudflare every request comes from an edge: the visitor is CF-Connecting-IP
    (which Cloudflare overwrites), so unrelated players stop sharing an edge's budget."""
    # Prepare
    request = _request_with(edge, {"CF-Connecting-IP": VISITOR, "X-Forwarded-For": "6.6.6.6"})

    # Act / Assert
    assert client_ip_key(request) == VISITOR


def test_two_visitors_behind_one_edge_get_two_keys():
    """The bug in production: 37 edges carried every visitor, so a table shared one login budget."""
    # Act
    keys = {
        client_ip_key(_request_with(CLOUDFLARE_EDGE, {"CF-Connecting-IP": "198.51.100.1"})),
        client_ip_key(_request_with(CLOUDFLARE_EDGE, {"CF-Connecting-IP": "198.51.100.2"})),
    }

    # Assert
    assert keys == {"198.51.100.1", "198.51.100.2"}


@pytest.mark.parametrize("header", [None, "", "not-an-address", "1.2.3.4, 5.6.7.8"])
def test_a_cloudflare_peer_without_a_usable_header_is_keyed_on_the_edge(header: str | None):
    """No (or a malformed) CF-Connecting-IP: fall back to the peer rather than trust garbage."""
    # Prepare
    headers = {} if header is None else {"CF-Connecting-IP": header}

    # Act / Assert
    assert client_ip_key(_request_with(CLOUDFLARE_EDGE, headers)) == CLOUDFLARE_EDGE


def test_the_default_key_and_the_anonymous_fallback_are_the_client_address():
    """Every per-IP limit (login, register, forgot-password…) and user_or_ip_key's fallback."""
    # Prepare
    request = _request_with(CLOUDFLARE_EDGE, {"CF-Connecting-IP": VISITOR})

    # Act / Assert
    assert limiter._key_func is client_ip_key
    assert user_or_ip_key(request) == VISITOR


def test_a_non_ip_peer_name_is_kept_as_is():
    """Starlette's TestClient names its peer "testclient"; the key must not crash on it."""
    # Act / Assert
    assert client_ip_key(_request_with("testclient", {"CF-Connecting-IP": VISITOR})) == "testclient"


# ─── FR-3 (d): /auth/refresh is limited per account, not per address ──────


def test_refresh_is_keyed_on_the_account_its_token_names():
    """The refresh route's key: the account recorded by its dependency, else the address."""
    # Prepare
    named, anonymous = _request(), _request("198.51.100.4")
    named.state.refresh_token_sub = "u-1"

    # Act / Assert
    assert refresh_sub_key(named) == f"{RATE_LIMIT_USER_KEY_PREFIX}u-1"
    assert refresh_sub_key(anonymous) == "198.51.100.4"


@pytest_asyncio.fixture(name="refresh_api")
async def get_refresh_api(
    test_app: FastAPI, session: AsyncSession, test_settings: Settings
) -> AsyncGenerator[httpx.AsyncClient]:
    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    limiter.reset()
    test_app.dependency_overrides.clear()


async def test_eleven_players_refreshing_from_one_address_are_not_rate_limited(
    refresh_api: httpx.AsyncClient, auth_controller: AuthController, create_user
):
    """A majlis is several phones on one connection: each refresh counts against its own account
    (10/minute), so the eleventh player's refresh is not a 429 that logs them out mid-game."""
    # Prepare — eleven accounts, each signed in
    refresh_tokens = []
    for index in range(11):
        await create_user(username=f"player{index}", email=f"player{index}@test.com", password="password123")
        refresh_tokens.append((await auth_controller.login(f"player{index}@test.com", "password123")).refresh_token)

    # Act
    statuses = []
    for token in refresh_tokens:
        response = await refresh_api.post("/api/v1/auth/refresh", json={"refresh_token": token})
        refresh_api.cookies.clear()
        statuses.append(response.status_code)

    # Assert
    assert statuses == [200] * 11


async def test_one_account_refreshing_too_often_is_still_limited(
    refresh_api: httpx.AsyncClient, auth_controller: AuthController, create_user
):
    """The per-account key still limits: the eleventh refresh of ONE account within a minute is a 429."""
    # Prepare
    await create_user(username="eager", email="eager@test.com", password="password123")
    token = (await auth_controller.login("eager@test.com", "password123")).refresh_token

    # Act
    statuses = []
    for _ in range(11):
        response = await refresh_api.post("/api/v1/auth/refresh", json={"refresh_token": token})
        refresh_api.cookies.clear()
        statuses.append(response.status_code)
        if response.status_code == 200:
            token = response.cookies["majlisna-refresh-token"]

    # Assert
    assert statuses[:10] == [200] * 10
    assert statuses[10] == 429


async def test_a_forged_refresh_token_is_keyed_on_the_address(
    refresh_api: httpx.AsyncClient, create_user, test_settings: Settings
):
    """The token is decoded (signature included) only to pick the bucket: a forged ``sub`` per
    request cannot buy a fresh budget each time."""
    # Prepare
    await create_user(username="victim", email="victim@test.com")
    forged = [
        jwt.encode(
            {"sub": f"forged-{index}", "email": "x@test.com", "type": "refresh"}, "not-our-key", algorithm="HS256"
        )
        for index in range(11)
    ]
    assert test_settings.jwt_secret_key != "not-our-key"

    # Act
    statuses = []
    for token in forged:
        response = await refresh_api.post("/api/v1/auth/refresh", json={"refresh_token": token})
        statuses.append(response.status_code)

    # Assert
    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


# ── A storage outage (review INT-02) ───────────────────────────────

# Nothing listens on port 1: a Redis that is down, refused at once.
_UNREACHABLE_REDIS = "redis://127.0.0.1:1/1"


def _outage_app(outage_limiter) -> FastAPI:
    """One limited route on its own app, its limiter pointed at a Redis that is down."""
    app = FastAPI()
    app.state.limiter = outage_limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

    @app.post("/limited")
    @outage_limiter.limit("2/minute")
    async def limited(request: Request) -> dict:  # noqa: ARG001 — slowapi reads the request
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_a_rate_limit_storage_outage_keeps_the_route_working_and_limited():
    """With Redis down, every limited route answered 500 (slowapi raises by default): sign-in,
    room joins, and since this release the gameplay routes (timer-expired, Kalimat answers,
    hint views). The counters now fall back to this worker's memory, and still limit."""
    # Prepare
    outage_limiter = build_limiter(storage_uri=_UNREACHABLE_REDIS, enabled=True)
    transport = httpx.ASGITransport(app=_outage_app(outage_limiter))

    # Act
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        answers = [(await client.post("/limited")).status_code for _ in range(3)]

    # Assert
    assert answers == [200, 200, 429]


def test_the_shared_limiter_falls_back_to_memory_when_its_storage_is_down():
    """The app's own limiter is built the same way (one place: ``build_limiter``)."""
    # Assert
    assert limiter._in_memory_fallback_enabled is True
