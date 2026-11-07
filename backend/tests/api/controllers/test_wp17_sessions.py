"""SEC F01: revocable sessions, single-use refresh tokens and an absolute session lifetime.

The JWTs were stateless (``sub``, ``email``, ``exp``, ``type``): ``/auth/refresh`` checked
only the signature and minted a fresh 7-day pair, logout only cleared cookies, and a reset
touched no token state. The security probe
``test_phase_b_functional.py::test_f01_tokens_survive_logout_password_change_and_reset``
proved it on PostgreSQL: the same refresh token refreshed twice, and after a logout and a
full forgot/reset cycle the old access token still read ``/auth/me`` and the old refresh
token still refreshed. These are that probe, inverted, through the real app and real JWTs,
on both dialects (the default SQLite run and ``--use-postgres``).
"""

import asyncio
from collections.abc import AsyncGenerator, Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from jose import jwt
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import REFRESH_REUSE_GRACE_SECONDS, SESSION_ABSOLUTE_LIFETIME_DAYS
from majlisna.api.controllers.auth import AuthController
from majlisna.api.models.auth_session import AuthSession, revoke_user_sessions
from majlisna.api.models.table import Room, User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.error import InvalidTokenError, SessionRevokedError
from majlisna.api.ws import handlers
from majlisna.api.ws.handlers import _authenticate_member, _connect_personal
from majlisna.dependencies import get_current_user, get_email_service, get_session, get_settings
from majlisna.settings import Settings

ME_URL = "/api/v1/auth/me"
LOGIN_URL = "/api/v1/auth/login"
REFRESH_URL = "/api/v1/auth/refresh"
LOGOUT_URL = "/api/v1/auth/logout"
FORGOT_URL = "/api/v1/auth/forgot-password"
RESET_URL = "/api/v1/auth/reset-password"
REFRESH_COOKIE = "majlisna-refresh-token"
SESSION_REVOKED_KEY = "errors.api.sessionRevoked"

MEMBER_EMAIL = "member@test.com"
MEMBER_PASSWORD = "password123"


# ── Fixtures and helpers ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def fresh_rate_limits() -> Iterator[None]:
    """The limiter is in-memory and process-wide: every test starts and ends with empty buckets."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(name="mail")
def get_mail() -> Mock:
    """The email service, faked: the reset link is read from the call, as a user reads it."""
    mail = Mock()
    mail.send_password_reset_email = AsyncMock(return_value=True)
    mail.send_verification_email = AsyncMock(return_value=True)
    return mail


@pytest_asyncio.fixture(name="api")
async def get_api(
    test_app: FastAPI, session: AsyncSession, test_settings: Settings, mail: Mock
) -> AsyncGenerator[httpx.AsyncClient]:
    """An async client on the real app, on the test database and the test JWT key."""

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: test_settings
    test_app.dependency_overrides[get_email_service] = lambda: mail
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    test_app.dependency_overrides.clear()


@pytest_asyncio.fixture(name="member")
async def get_member(create_user) -> User:
    return await create_user(username="member", email=MEMBER_EMAIL, password=MEMBER_PASSWORD)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _claims(token: str) -> dict:
    return jwt.get_unverified_claims(token)


def _sid(token: str) -> UUID:
    return UUID(_claims(token)["sid"])


def _refresh_cookie(response: httpx.Response) -> str:
    """The refresh token a response set: the httpOnly cookie, its only carrier (SEC F13, review INT-06)."""
    token = response.cookies.get(REFRESH_COOKIE)
    assert token, response.text
    return token


def _pair(response: httpx.Response) -> dict:
    """The body, which never holds the refresh token, plus the refresh token from its cookie."""
    body = response.json()
    assert "refresh_token" not in body, "a script in the page could read it"
    return {**body, "refresh_token": _refresh_cookie(response)}


async def _login(api: httpx.AsyncClient, password: str = MEMBER_PASSWORD) -> dict:
    """POST /auth/login; the cookie jar is emptied so each call below presents only what it names."""
    response = await api.post(LOGIN_URL, json={"email": MEMBER_EMAIL, "password": password})
    api.cookies.clear()
    assert response.status_code == 200, response.text
    return _pair(response)


async def _refresh(api: httpx.AsyncClient, refresh_token: str) -> httpx.Response:
    response = await api.post(REFRESH_URL, json={"refresh_token": refresh_token})
    api.cookies.clear()
    return response


async def _me(api: httpx.AsyncClient, access_token: str) -> httpx.Response:
    response = await api.get(ME_URL, headers=_bearer(access_token))
    api.cookies.clear()
    return response


async def _stored(session: AsyncSession, sid: UUID) -> AuthSession:
    """The session row as the database has it now (not the identity map's copy)."""
    statement = select(AuthSession).where(AuthSession.id == sid).execution_options(populate_existing=True)
    return (await session.exec(statement)).one()


def _utc(instant: datetime) -> datetime:
    # SQLite reads TIMESTAMP WITH TIME ZONE back naive (backend/CLAUDE.md).
    return instant.replace(tzinfo=UTC) if instant.tzinfo is None else instant


async def _set_session(session: AsyncSession, sid: UUID, **values: object) -> None:
    await session.exec(update(AuthSession).where(AuthSession.id == sid).values(**values))
    await session.commit()


def _assert_revoked(response: httpx.Response) -> None:
    assert response.status_code == 401, response.text
    assert response.json()["error_key"] == SESSION_REVOKED_KEY


# ── Tokens name a session ─────────────────────────────────────────


async def test_login_opens_a_session_that_both_tokens_name(api: httpx.AsyncClient, session: AsyncSession, member: User):
    """Access and refresh carry the session's ``sid`` and ``iat``; the refresh token its ``jti``."""
    # Prepare
    before = datetime.now(UTC)

    # Act
    tokens = await _login(api)

    # Assert
    access, refresh = _claims(tokens["access_token"]), _claims(tokens["refresh_token"])
    assert access["sid"] == refresh["sid"]
    assert "iat" in access
    assert "iat" in refresh
    assert refresh["jti"]
    assert "jti" not in access
    stored = await _stored(session, UUID(access["sid"]))
    assert stored.user_id == member.id
    assert stored.current_refresh_jti == refresh["jti"]
    assert stored.revoked_at is None
    lifetime = _utc(stored.expires_at) - before
    assert timedelta(days=SESSION_ABSOLUTE_LIFETIME_DAYS) - timedelta(minutes=1) <= lifetime
    assert lifetime <= timedelta(days=SESSION_ABSOLUTE_LIFETIME_DAYS) + timedelta(minutes=1)
    assert refresh["exp"] <= int(_utc(stored.expires_at).timestamp())


async def test_signing_in_purges_the_accounts_sessions_past_their_lifetime(
    auth_controller: AuthController, session: AsyncSession, member: User, create_user
):
    """One row per sign-in would grow the table forever: a new sign-in drops the account's dead
    rows (past ``expires_at``, whose tokens can no longer work), and only those."""
    # Prepare — an ended session and a live one for the member, an ended one for someone else
    other = await create_user(username="other", email="other@test.com", password=MEMBER_PASSWORD)
    ended = _sid((await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)).access_token)
    live = _sid((await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)).access_token)
    others_ended = _sid((await auth_controller.login("other@test.com", MEMBER_PASSWORD)).access_token)
    for sid in (ended, others_ended):
        await _set_session(session, sid, expires_at=datetime.now(UTC) - timedelta(minutes=1))

    # Act
    fresh = _sid((await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)).access_token)

    # Assert
    rows = (await session.exec(select(AuthSession).execution_options(populate_existing=True))).all()
    remaining = {(row.id, row.user_id) for row in rows}
    assert remaining == {(live, member.id), (fresh, member.id), (others_ended, other.id)}


async def test_get_current_user_records_the_callers_session(
    auth_controller: AuthController,
    member: User,  # noqa: ARG001 — the account login signs into
):
    """``request.state.session_id`` is the caller's sid (WP-27 spares it on a password change)."""
    # Prepare
    tokens = await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)
    request = Mock(cookies={})

    # Act
    await get_current_user(request, tokens.access_token, auth_controller)

    # Assert
    assert request.state.session_id == _sid(tokens.access_token)


async def test_a_legacy_access_token_without_sid_still_reads_me_until_it_expires(
    api: httpx.AsyncClient, auth_controller: AuthController, member: User
):
    """No forced logout at deploy: a token minted before sessions existed works out its 15 minutes."""
    # Prepare
    legacy = auth_controller.create_access_token(str(member.id), member.email_address)
    request = Mock(cookies={})

    # Act
    response = await _me(api, legacy)
    await get_current_user(request, legacy, auth_controller)

    # Assert
    assert response.status_code == 200
    assert response.json()["id"] == str(member.id)
    assert request.state.session_id is None


# ── Logout ────────────────────────────────────────────────────────


async def test_after_logout_the_old_access_and_refresh_tokens_answer_401(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
):
    """Logout used to only clear cookies: a copied token kept working."""
    # Prepare
    tokens = await _login(api)

    # Act
    logout = await api.post(LOGOUT_URL, headers=_bearer(tokens["access_token"]))
    api.cookies.clear()
    me_after = await _me(api, tokens["access_token"])
    refresh_after = await _refresh(api, tokens["refresh_token"])

    # Assert
    assert logout.status_code == 200
    _assert_revoked(me_after)
    _assert_revoked(refresh_after)
    stored = await _stored(session, _sid(tokens["access_token"]))
    assert stored.revoked_at is not None


async def test_logout_with_only_the_refresh_cookie_ends_the_session(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
):
    """A tab whose access token already expired still signs its session out (the cookie is sent)."""
    # Prepare
    tokens = await _login(api)
    api.cookies.set(REFRESH_COOKIE, tokens["refresh_token"])

    # Act
    logout = await api.post(LOGOUT_URL)
    api.cookies.clear()
    refresh_after = await _refresh(api, tokens["refresh_token"])

    # Assert
    assert logout.status_code == 200
    _assert_revoked(refresh_after)
    stored = await _stored(session, _sid(tokens["refresh_token"]))
    assert stored.revoked_at is not None


async def test_logout_signs_out_only_the_callers_session(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
):
    """The phone that logs out ends its own session, not the laptop's."""
    # Prepare
    phone = await _login(api)
    laptop = await _login(api)

    # Act
    await api.post(LOGOUT_URL, headers=_bearer(phone["access_token"]))
    api.cookies.clear()

    # Assert
    assert (await _me(api, laptop["access_token"])).status_code == 200
    assert (await _stored(session, _sid(laptop["access_token"]))).revoked_at is None


async def test_logout_without_any_token_still_answers_ok(api: httpx.AsyncClient):
    """Nothing to sign out: the cookies are cleared all the same."""
    # Act
    response = await api.post(LOGOUT_URL)

    # Assert
    assert response.status_code == 200


# ── Reset ─────────────────────────────────────────────────────────


async def test_after_a_reset_every_earlier_token_answers_401(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
    mail: Mock,
):
    """The "my account was stolen" path: after a reset the thief's sessions end, on every device."""
    # Prepare — two devices signed in
    phone = await _login(api)
    laptop = await _login(api)
    forgot = await api.post(FORGOT_URL, json={"email": MEMBER_EMAIL})
    api.cookies.clear()
    reset_url = mail.send_password_reset_email.await_args.args[2]
    reset_token = parse_qs(urlparse(reset_url).query)["token"][0]

    # Act
    reset = await api.post(RESET_URL, json={"token": reset_token, "new_password": "R3set-Passw0rd!"})
    api.cookies.clear()

    # Assert
    assert forgot.status_code == 200
    assert reset.status_code == 200, reset.text
    for device in (phone, laptop):
        _assert_revoked(await _me(api, device["access_token"]))
        _assert_revoked(await _refresh(api, device["refresh_token"]))
        assert (await _stored(session, _sid(device["access_token"]))).revoked_at is not None
    fresh = await _login(api, password="R3set-Passw0rd!")
    assert (await _me(api, fresh["access_token"])).status_code == 200


# ── Refresh: single use, reuse detection, the grace window ────────


async def test_reusing_a_refresh_token_after_the_grace_window_revokes_the_session(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
):
    """The second use of one refresh token, long after its rotation, is theft: the whole session ends."""
    # Prepare
    tokens = await _login(api)
    sid = _sid(tokens["refresh_token"])
    first = await _refresh(api, tokens["refresh_token"])
    assert first.status_code == 200, first.text
    rotated = _pair(first)
    assert rotated["refresh_token"] != tokens["refresh_token"]
    stale = datetime.now(UTC) - timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS + 5)
    await _set_session(session, sid, rotated_at=stale)

    # Act
    reuse = await _refresh(api, tokens["refresh_token"])

    # Assert
    _assert_revoked(reuse)
    assert (await _stored(session, sid)).revoked_at is not None
    # the whole session is gone, the rotated pair included
    _assert_revoked(await _refresh(api, rotated["refresh_token"]))
    _assert_revoked(await _me(api, rotated["access_token"]))


async def test_within_the_grace_window_the_raced_tab_gets_the_same_refresh_token(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
):
    """Two tabs refreshing at once: the second is answered the CURRENT refresh token, not revoked."""
    # Prepare
    tokens = await _login(api)
    sid = _sid(tokens["refresh_token"])
    first = await _refresh(api, tokens["refresh_token"])
    assert first.status_code == 200, first.text

    # Act
    raced = await _refresh(api, tokens["refresh_token"])

    # Assert
    assert raced.status_code == 200, raced.text
    assert _refresh_cookie(raced) == _refresh_cookie(first)
    assert (await _me(api, raced.json()["access_token"])).status_code == 200
    stored = await _stored(session, sid)
    assert stored.revoked_at is None
    assert stored.current_refresh_jti == _claims(_refresh_cookie(first))["jti"]
    # and the current token still rotates normally
    onward = await _refresh(api, _refresh_cookie(first))
    assert onward.status_code == 200, onward.text
    assert _refresh_cookie(onward) != _refresh_cookie(first)


async def test_a_session_past_its_absolute_lifetime_cannot_refresh(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
):
    """However often it was refreshed, a session ends at ``expires_at``."""
    # Prepare
    tokens = await _login(api)
    sid = _sid(tokens["refresh_token"])
    await _set_session(session, sid, expires_at=datetime.now(UTC) - timedelta(minutes=1))

    # Act
    refresh = await _refresh(api, tokens["refresh_token"])
    me = await _me(api, tokens["access_token"])

    # Assert
    _assert_revoked(refresh)
    _assert_revoked(me)


async def test_refreshing_never_extends_the_session(
    api: httpx.AsyncClient,
    session: AsyncSession,
    member: User,  # noqa: ARG001
):
    """The rotated refresh token expires no later than the session, and ``expires_at`` does not move."""
    # Prepare — a session with an hour left, shorter than a refresh token's 7 days
    tokens = await _login(api)
    sid = _sid(tokens["refresh_token"])
    ends = datetime.now(UTC) + timedelta(hours=1)
    await _set_session(session, sid, expires_at=ends)

    # Act
    response = await _refresh(api, tokens["refresh_token"])

    # Assert
    assert response.status_code == 200, response.text
    assert _claims(_refresh_cookie(response))["exp"] <= int(ends.timestamp())
    assert abs(_utc((await _stored(session, sid)).expires_at) - ends) < timedelta(seconds=1)


async def test_an_access_token_cannot_refresh(api: httpx.AsyncClient, member: User):  # noqa: ARG001
    """The type rule still holds on the new path."""
    # Prepare
    tokens = await _login(api)

    # Act
    response = await _refresh(api, tokens["access_token"])

    # Assert
    assert response.status_code == 401
    assert response.json()["error_key"] == "errors.api.invalidToken"


async def test_refresh_without_any_token_is_refused(auth_controller: AuthController):
    """No body and no cookie: 401, as before (the check moved from the route to the controller)."""
    # Act / Assert
    with pytest.raises(InvalidTokenError):
        await auth_controller.refresh_session(None)


# ── Legacy tokens (minted before sessions existed) ───────────────


async def test_a_legacy_refresh_token_is_upgraded_into_a_session_that_rotates_and_revokes(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, member: User
):
    """Untrackable, so accepted once and turned into a real session — which then behaves like any other."""
    # Prepare
    legacy = auth_controller.create_refresh_token(str(member.id), member.email_address)
    assert "sid" not in _claims(legacy)

    # Act
    upgraded = await _refresh(api, legacy)

    # Assert — a session now stands behind the new pair
    assert upgraded.status_code == 200, upgraded.text
    pair = _pair(upgraded)
    sid = _sid(pair["refresh_token"])
    assert _sid(pair["access_token"]) == sid
    stored = await _stored(session, sid)
    assert stored.user_id == member.id
    assert stored.current_refresh_jti == _claims(pair["refresh_token"])["jti"]
    # it rotates…
    rotated = await _refresh(api, pair["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    # …and a late reuse revokes it
    await _set_session(session, sid, rotated_at=datetime.now(UTC) - timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS + 5))
    _assert_revoked(await _refresh(api, pair["refresh_token"]))
    assert (await _stored(session, sid)).revoked_at is not None


async def test_a_legacy_refresh_token_upgrades_once_and_its_reuse_revokes_that_session(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, member: User
):
    """Review R3: the legacy token was upgraded into a NEW session on every use, for 7 days.

    A stolen copy minted fresh sessions after the victim logged out, reset the password
    or tripped reuse detection. Now its digest is recorded on the session it opened: a
    second presentation outside the two-tab grace is a replayed copy — refused, and
    the session it opened is revoked, like any reused refresh token.
    """
    # Prepare
    legacy = auth_controller.create_refresh_token(str(member.id), member.email_address)
    first = await _refresh(api, legacy)
    assert first.status_code == 200, first.text
    sid = _sid(_refresh_cookie(first))
    await _set_session(session, sid, created_at=datetime.now(UTC) - timedelta(seconds=REFRESH_REUSE_GRACE_SECONDS + 5))

    # Act
    again = await _refresh(api, legacy)

    # Assert
    _assert_revoked(again)
    assert (await _stored(session, sid)).revoked_at is not None
    assert len((await session.exec(select(AuthSession).where(AuthSession.user_id == member.id))).all()) == 1


async def test_a_legacy_refresh_token_presented_after_a_reset_opens_nothing(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, member: User
):
    """The probe of R3: upgrade, every session revoked (what a reset does), the same legacy token twice more."""
    # Prepare
    legacy = auth_controller.create_refresh_token(str(member.id), member.email_address)
    assert (await _refresh(api, legacy)).status_code == 200
    await revoke_user_sessions(session, member.id)
    await session.commit()

    # Act
    second = await _refresh(api, legacy)
    third = await _refresh(api, legacy)

    # Assert
    _assert_revoked(second)
    _assert_revoked(third)
    rows = (await session.exec(select(AuthSession).where(AuthSession.user_id == member.id))).all()
    assert len(rows) == 1
    assert rows[0].revoked_at is not None


async def test_two_tabs_upgrading_one_legacy_token_share_one_session(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, member: User
):
    """Inside the grace, the second tab gets the session the first one opened, not a revocation."""
    # Prepare
    legacy = auth_controller.create_refresh_token(str(member.id), member.email_address)
    first = await _refresh(api, legacy)
    assert first.status_code == 200, first.text

    # Act
    second = await _refresh(api, legacy)

    # Assert
    assert second.status_code == 200, second.text
    sid = _sid(_refresh_cookie(first))
    assert _sid(_refresh_cookie(second)) == sid
    assert _refresh_cookie(second) == _refresh_cookie(first)
    assert (await _stored(session, sid)).revoked_at is None
    assert len((await session.exec(select(AuthSession).where(AuthSession.user_id == member.id))).all()) == 1


async def test_a_legacy_refresh_token_of_a_deleted_account_is_refused(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, member: User
):
    """The upgrade still requires the account named by BOTH claims."""
    # Prepare
    legacy = auth_controller.create_refresh_token(str(member.id), member.email_address)
    await session.delete(member)
    await session.commit()

    # Act
    response = await _refresh(api, legacy)

    # Assert
    assert response.status_code == 401
    assert (await session.exec(select(AuthSession))).all() == []


# ── One account per mailbox, through the real routes (SEC F14) ────


async def test_an_address_registers_once_whatever_its_case_and_signs_in_in_any_case(
    api: httpx.AsyncClient, session: AsyncSession
):
    """Port of test_f14_email_unique_only_case_sensitively, inverted: it answered 201 twice,
    two accounts for one mailbox."""
    # Prepare
    first = await api.post(
        "/api/v1/auth/register",
        json={"username": "ali_lower", "email_address": "ali@example.com", "password": MEMBER_PASSWORD},
    )
    api.cookies.clear()

    # Act
    second = await api.post(
        "/api/v1/auth/register",
        json={"username": "ali_upper", "email_address": "Ali@Example.com", "password": MEMBER_PASSWORD},
    )
    api.cookies.clear()
    login = await api.post(LOGIN_URL, json={"email": "ALI@example.COM", "password": MEMBER_PASSWORD})
    api.cookies.clear()

    # Assert
    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error_key"] == "errors.api.userAlreadyExists"
    assert login.status_code == 200, login.text
    assert login.json()["user"]["id"] == first.json()["id"]
    accounts = (await session.exec(select(User).execution_options(populate_existing=True))).all()
    assert [account.email_address for account in accounts] == ["ali@example.com"]


# ── Socket.IO: the same check at connect ─────────────────────────


@pytest.fixture(name="sockets")
def get_sockets(engine: AsyncEngine, test_settings: Settings) -> Iterator[AsyncMock]:
    """The handlers open their own session with ``Settings()``: point both at the test database
    and key. Only the Socket.IO server is faked."""
    with (
        patch("majlisna.api.ws.handlers.sio") as mock_sio,
        patch("majlisna.api.ws.handlers.get_engine", new=AsyncMock(return_value=engine)),
        patch("majlisna.api.ws.handlers.Settings", return_value=test_settings),
    ):
        mock_sio.enter_room = AsyncMock()
        mock_sio.save_session = AsyncMock()
        mock_sio.emit = AsyncMock()
        yield mock_sio


async def test_a_revoked_sessions_access_token_cannot_open_a_socket(
    sockets: AsyncMock, auth_controller: AuthController, member: User, create_room
):
    """A signed-out device's socket is refused at connect, personal channel and room alike."""
    # Prepare
    room: Room = await create_room(owner=member)
    tokens = await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)
    await auth_controller.logout(access_token=tokens.access_token, refresh_token=None)

    # Act / Assert
    with pytest.raises(ConnectionRefusedError):
        await _connect_personal("sid-revoked", tokens.access_token)
    with pytest.raises(ConnectionRefusedError):
        await _authenticate_member("sid-revoked-room", tokens.access_token, room.id)
    sockets.enter_room.assert_not_awaited()


async def test_a_live_sessions_access_token_opens_a_socket(
    sockets: AsyncMock, auth_controller: AuthController, member: User, create_room
):
    """The control: the same flow, without the logout, connects."""
    # Prepare
    room: Room = await create_room(owner=member)
    tokens = await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)

    # Act
    await _connect_personal("sid-live", tokens.access_token)
    caller = await _authenticate_member("sid-live-room", tokens.access_token, room.id)

    # Assert
    sockets.enter_room.assert_awaited_once_with("sid-live", f"user:{member.id}")
    assert caller.user.id == member.id


async def test_authenticate_refuses_a_revoked_session_with_session_revoked(
    auth_controller: AuthController,
    member: User,  # noqa: ARG001
):
    """The named 401 the client reads as "you were signed out" (errors.api.sessionRevoked)."""
    # Prepare
    tokens = await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)
    await auth_controller.logout(access_token=None, refresh_token=tokens.refresh_token)

    # Act / Assert
    with pytest.raises(SessionRevokedError):
        await get_current_user(Mock(cookies={}), tokens.access_token, auth_controller)


@pytest.fixture(name="socket_maps")
def get_socket_maps() -> Iterator[None]:
    """The per-process socket maps, empty before and after."""
    handlers._user_sids.clear()
    handlers._socket_sessions.clear()
    yield
    handlers._user_sids.clear()
    handlers._socket_sessions.clear()


async def test_a_socket_opened_before_its_session_ended_is_cut_by_the_next_tick(
    sockets: AsyncMock,
    socket_maps: None,  # noqa: ARG001
    auth_controller: AuthController,
    session: AsyncSession,
    member: User,
    create_room,
    count_statements,
):
    """Review R5: the session was checked at connect only. A thief's personal socket kept
    receiving the victim's room invites (code and PIN) after the reset, and their room
    sockets the room state, until they happened to reconnect."""
    # Prepare — a personal socket and a room socket, both on one live session
    room: Room = await create_room(owner=member)
    tokens = await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)
    await _connect_personal("sid-personal", tokens.access_token)
    # The room socket through the real handshake: it records the socket's session (and its
    # seat) only once it has checked the socket is still there.
    with (
        patch.object(handlers, "fetch_room_state", AsyncMock(return_value={})),
        patch.object(handlers, "fire_notify_room_changed"),
    ):
        assert await handlers.connect("sid-room", {}, {"token": tokens.access_token, "room_id": str(room.id)})
    assert handlers._user_sids == {f"{member.id}:{room.id}": "sid-room"}
    sockets.rooms = Mock(
        side_effect=lambda sid: [sid, f"user:{member.id}"] + ([f"room:{room.id}"] if sid == "sid-room" else [])
    )
    sockets.leave_room = AsyncMock()
    sockets.disconnect = AsyncMock()
    assert await handlers.audit_local_socket_memberships(session) == 0  # live: nothing to cut
    sockets.disconnect.assert_not_awaited()
    await auth_controller.logout(access_token=tokens.access_token, refresh_token=None)
    queries = count_statements("auth_session")

    # Act — this worker's next tick
    cut = await handlers.audit_local_socket_memberships(session)

    # Assert — both cut, off every channel first (no invite reaches them meanwhile), in one read
    assert cut == 2
    assert {c.args[0] for c in sockets.disconnect.await_args_list} == {"sid-personal", "sid-room"}
    left = {c.args for c in sockets.leave_room.await_args_list}
    assert ("sid-personal", f"user:{member.id}") in left
    assert ("sid-room", f"room:{room.id}") in left
    assert queries.count == 1
    assert handlers._socket_sessions == {}
    assert handlers._user_sids == {}


# ── Two tabs racing (postgres: real concurrency, one connection each) ─


async def _refresh_own_session(engine: AsyncEngine, settings: Settings, refresh_token: str) -> str:
    async with AsyncSession(engine, expire_on_commit=False) as own_session:
        return (await AuthController(own_session, settings).refresh_session(refresh_token)).refresh_token


@pytest.mark.postgres
async def test_two_tabs_refreshing_one_token_at_once_both_stay_signed_in(
    engine: AsyncEngine,
    session: AsyncSession,
    auth_controller: AuthController,
    test_settings: Settings,
    member: User,  # noqa: ARG001
):
    """Without the row lock both rotate, one rotation is lost, and that tab's next refresh reads as theft."""
    # Prepare
    tokens = await auth_controller.login(MEMBER_EMAIL, MEMBER_PASSWORD)
    sid = _sid(tokens.refresh_token)

    # Act
    results = await asyncio.gather(
        _refresh_own_session(engine, test_settings, tokens.refresh_token),
        _refresh_own_session(engine, test_settings, tokens.refresh_token),
        return_exceptions=True,
    )

    # Assert
    assert all(isinstance(result, str) for result in results), results
    assert results[0] == results[1]
    stored = await _stored(session, sid)
    assert stored.revoked_at is None
    assert stored.current_refresh_jti == _claims(str(results[0]))["jti"]


@pytest.mark.postgres
async def test_two_tabs_upgrading_one_legacy_token_at_once_get_one_session(
    engine: AsyncEngine,
    session: AsyncSession,
    auth_controller: AuthController,
    test_settings: Settings,
    member: User,
):
    """Both first presentations insert; the unique digest makes the loser take the grace path, not a 500."""
    # Prepare
    legacy = auth_controller.create_refresh_token(str(member.id), member.email_address)

    # Act
    results = await asyncio.gather(
        _refresh_own_session(engine, test_settings, legacy),
        _refresh_own_session(engine, test_settings, legacy),
        return_exceptions=True,
    )

    # Assert
    assert all(isinstance(result, str) for result in results), results
    assert _sid(str(results[0])) == _sid(str(results[1]))
    rows = (
        await session.exec(
            select(AuthSession).where(AuthSession.user_id == member.id).execution_options(populate_existing=True)
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].revoked_at is None
