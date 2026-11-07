"""SEC F09 and TQ-01, Socket.IO half: the two socket connects authenticate like HTTP.

Both connects resolved the user by the token's ``email`` claim alone, never comparing
``sub``, so an access token outlived a delete-and-re-register of its address: it opened
the NEW account's personal channel (room invites with their PIN) and any room that
account sat in. And the access-vs-refresh rule on both connects was untested: every
existing handler test replaced ``decode_token`` with a Mock.

These run the real handlers against the test database with real JWTs; only the
Socket.IO server (``sio``) is a mock.
"""

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.user import UserController
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.table import Room, User
from majlisna.api.ws.handlers import _authenticate_member, _connect_personal
from majlisna.settings import Settings


@pytest.fixture(autouse=True)
def mock_sio() -> Iterator[AsyncMock]:
    """The Socket.IO server is the only thing faked: the auth runs for real."""
    with patch("majlisna.api.ws.handlers.sio") as mock:
        mock.enter_room = AsyncMock()
        mock.save_session = AsyncMock()
        mock.emit = AsyncMock()
        yield mock


@pytest.fixture(autouse=True)
def real_database(engine: AsyncEngine, test_settings: Settings) -> Iterator[None]:
    """The handlers open their own session on the app engine with ``Settings()``: point
    both at the test database and the test JWT key."""
    with (
        patch("majlisna.api.ws.handlers.get_engine", new=AsyncMock(return_value=engine)),
        patch("majlisna.api.ws.handlers.Settings", return_value=test_settings),
    ):
        yield


@pytest_asyncio.fixture(name="re_registered")
async def get_re_registered(session: AsyncSession, auth_controller: AuthController, create_user, create_room) -> dict:
    """A deletes their account and keeps an access token; B registers the same address
    and opens a room."""
    a = await create_user(username="first_owner", email="reused@test.com")
    old_token = auth_controller.create_access_token(str(a.id), a.email_address)
    await UserController(session).delete_user(a.id)
    b = await create_user(username="second_owner", email="reused@test.com")
    b_room: Room = await create_room(owner=b)
    await session.commit()
    return {"old_token": old_token, "b": b, "b_room": b_room, "a_id": a.id}


@pytest.mark.asyncio
async def test_personal_connect_refuses_an_old_token_of_a_re_registered_address(re_registered: dict, mock_sio):
    """The old token must not open B's ``user:{id}`` channel (where invites carry a PIN)."""
    # Act / Assert
    with pytest.raises(ConnectionRefusedError):
        await _connect_personal("sid-old", re_registered["old_token"])
    mock_sio.enter_room.assert_not_awaited()
    mock_sio.save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_member_connect_refuses_an_old_token_of_a_re_registered_address(re_registered: dict):
    """Nor may it join the room B sits in."""
    # Prepare
    b_room: Room = re_registered["b_room"]

    # Act / Assert
    with pytest.raises(ConnectionRefusedError):
        await _authenticate_member("sid-old", re_registered["old_token"], b_room.id)


@pytest.mark.asyncio
async def test_the_new_owner_of_the_address_still_connects(
    re_registered: dict, auth_controller: AuthController, mock_sio
):
    """The control: B's own token opens B's channel and B's room."""
    # Prepare
    b: User = re_registered["b"]
    b_room: Room = re_registered["b_room"]
    token = auth_controller.create_access_token(str(b.id), b.email_address)

    # Act
    await _connect_personal("sid-b", token)
    member = await _authenticate_member("sid-b2", token, b_room.id)

    # Assert
    mock_sio.enter_room.assert_awaited_once_with("sid-b", f"user:{b.id}")
    assert member.user.id == b.id


@pytest_asyncio.fixture(name="seated")
async def get_seated(session: AsyncSession, create_user, create_room) -> dict:
    """A player seated in a room."""
    user = await create_user(username="seated", email="seated@test.com")
    room: Room = await create_room(owner=user)
    link = (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room.id))).first()
    assert link is not None
    return {"user": user, "room_id": room.id}


@pytest.mark.asyncio
async def test_personal_connect_refuses_a_refresh_token(seated: dict, auth_controller: AuthController, mock_sio):
    """A real refresh token of a real account is not an access token."""
    # Prepare
    user: User = seated["user"]
    refresh = auth_controller.create_refresh_token(str(user.id), user.email_address)

    # Act / Assert
    with pytest.raises(ConnectionRefusedError):
        await _connect_personal("sid-r", refresh)
    mock_sio.enter_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_member_connect_refuses_a_refresh_token(seated: dict, auth_controller: AuthController):
    """Same for a room connection, by a real member of that room."""
    # Prepare
    user: User = seated["user"]
    room_id: UUID = seated["room_id"]
    refresh = auth_controller.create_refresh_token(str(user.id), user.email_address)

    # Act / Assert
    with pytest.raises(ConnectionRefusedError):
        await _authenticate_member("sid-r", refresh, room_id)


@pytest.mark.asyncio
async def test_member_connect_accepts_the_access_token_of_the_same_member(
    seated: dict, auth_controller: AuthController
):
    """The control for the two refusals above: the member's access token is answered."""
    # Prepare
    user: User = seated["user"]
    room_id: UUID = seated["room_id"]
    access = auth_controller.create_access_token(str(user.id), user.email_address)

    # Act
    member = await _authenticate_member("sid-a", access, room_id)

    # Assert
    assert member.user.id == user.id
