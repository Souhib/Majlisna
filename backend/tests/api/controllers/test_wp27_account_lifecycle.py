"""WP-27: the account lifecycle (SEC F05, F14, F15, F01).

- **F05.** Deleting an account purged the player's ``RoomUserLink`` rows directly, so
  the leave flow never ran: the deleted player stayed alive in ``live_state`` and in the
  description and vote order (an untimed round waited on them for ever), and a host's
  deletion orphaned the room (owner NULL, INACTIVE) under a game still IN_PROGRESS.
  Deletion now runs ``_handle_permanent_disconnect`` for every seat first — elimination
  or repair, ownership transfer, deactivation — and the deleted player is a leaver
  (neither a win nor a loss). Ported from the security probes
  ``test_f05_player_deletes_account_mid_game_and_wedges_untimed_round`` and
  ``test_f05_host_deletes_account_and_no_one_can_start_next_round``.
- **F14.** A Google-only account's password is a random value nobody knows, so deletion
  could not be confirmed. It now takes a fresh Google access token, verified like a
  sign-in (the same audience check), whose ``sub`` must be the account's.
- **F15.** ``profile_picture_url`` took any string of any length (``javascript:``, a
  20 000-character tracker): only https on Google's avatar CDN now, bounded.
- **F01.** A password change signs out every OTHER session of the account.
"""

from collections.abc import AsyncGenerator, Callable
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import AUTH_PROVIDER_GOOGLE, AVATAR_URL_MAX_LENGTH
from majlisna.api.controllers.auth import AuthController
from majlisna.api.controllers.shared import verify_password
from majlisna.api.controllers.undercover_game import UndercoverGameController
from majlisna.api.controllers.user import UserController
from majlisna.api.models.auth_session import AuthSession
from majlisna.api.models.game import GameStatus
from majlisna.api.models.relationship import RoomUserLink
from majlisna.api.models.room import RoomType
from majlisna.api.models.stats import UserStats
from majlisna.api.models.table import Game, Room, User
from majlisna.api.rate_limit import limiter
from majlisna.api.schemas.error import GoogleAccountMismatchError, InvalidCredentialsError
from majlisna.api.schemas.user import DepartedRoom
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.api.utils.game_state import left_player_ids
from majlisna.dependencies import get_session, get_settings, get_social_auth_service
from majlisna.settings import Settings

CLIENT_ID = "majlisna-web.apps.googleusercontent.com"
OWNER_SUB = "google-sub-owner"
DELETE_URL = "/api/v1/users/me/account"
ME_URL = "/api/v1/auth/me"
PASSWORD = "password123"  # setup_undercover_game's and create_user's default


# ─── Helpers ──────────────────────────────────────────────────────────────────


async def _fresh(session: AsyncSession, model, pk):
    return (await session.exec(select(model).where(model.id == pk).execution_options(populate_existing=True))).one()


async def _start_undercover(session: AsyncSession, setup_undercover_game, num_players: int) -> tuple[dict, UUID]:
    """A started Undercover game without Mr. White (untimed phases: the default 0)."""
    setup = await setup_undercover_game(num_players)
    room = await _fresh(session, Room, setup["room"].id)
    room.settings = {**(room.settings or {}), "enable_mr_white": False}
    flag_modified(room, "settings")
    session.add(room)
    await session.commit()
    started = await UndercoverGameController(session).create_and_start(setup["room"].id, setup["users"][0].id)
    return setup, UUID(started.game_id)


async def _describe_until_voting(session: AsyncSession, game_id: UUID) -> None:
    """Every alive player whose turn comes describes, until the round opens its vote."""
    controller = UndercoverGameController(session)
    for _ in range(20):
        turn = (await _fresh(session, Game, game_id)).live_state["turns"][-1]
        if turn["phase"] != "describing":
            return
        describer = turn["description_order"][turn["current_describer_index"]]
        await controller.submit_description(game_id, UUID(describer), "clue")
    pytest.fail("the describing phase never ended")


async def _everyone_votes_for(session: AsyncSession, game_id: UUID, target: str) -> None:
    """Every alive player votes for ``target``; ``target`` votes for someone else alive."""
    controller = UndercoverGameController(session)
    players = (await _fresh(session, Game, game_id)).live_state["players"]
    alive = [p["user_id"] for p in players if p["is_alive"]]
    for voter in alive:
        choice = target if voter != target else next(uid for uid in alive if uid != target)
        await controller.submit_vote(game_id, UUID(voter), UUID(choice))


def _fake_google(sub: str, email: str) -> Callable[[httpx.Request], httpx.Response]:
    """Google's tokeninfo and userinfo for a token minted for THIS app, naming ``sub``."""

    def _answer(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/tokeninfo":
            return httpx.Response(200, json={"aud": CLIENT_ID, "azp": CLIENT_ID, "sub": sub, "expires_in": "3599"})
        return httpx.Response(
            200, json={"sub": sub, "email": email, "email_verified": True, "given_name": "Real", "family_name": "Owner"}
        )

    return _answer


def _google_service(settings: Settings, sub: str, email: str) -> SocialAuthService:
    """The real verification, against a fake Google: only the network is stood in for."""
    return SocialAuthService(settings, transport=httpx.MockTransport(_fake_google(sub, email)))


@pytest.fixture(name="google_settings")
def get_google_settings(test_settings: Settings) -> Settings:
    return test_settings.model_copy(update={"google_client_id_web": CLIENT_ID})


@pytest_asyncio.fixture(name="api")
async def get_api(
    test_app: FastAPI, session: AsyncSession, google_settings: Settings
) -> AsyncGenerator[httpx.AsyncClient]:
    """The real app on the test database and the test JWT key; fresh rate-limit budgets."""

    async def _test_session() -> AsyncGenerator[AsyncSession]:
        yield session

    test_app.dependency_overrides[get_session] = _test_session
    test_app.dependency_overrides[get_settings] = lambda: google_settings
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=test_app), base_url="http://test") as client:
        yield client
    limiter.reset()
    test_app.dependency_overrides.clear()


class _RecordingEmailService:
    """Keeps the reset link's token instead of sending it."""

    token: str = ""

    async def send_password_reset_email(self, _to: str, _username: str, url: str) -> bool:
        self.token = url.split("token=", 1)[1]
        return True


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _google_user(session: AsyncSession, google_settings: Settings, email: str = "g.only@test.com") -> tuple:
    """A Google-only account (random sentinel password), signed in; returns (user, access token)."""
    service = _google_service(google_settings, OWNER_SUB, email)
    result = await AuthController(session, google_settings).social_login(
        social_auth_service=service, access_token="google-token"
    )
    user = (await session.exec(select(User).where(User.email_address == email))).one()
    assert user.auth_provider == AUTH_PROVIDER_GOOGLE
    return user, result.access_token


# ─── F05: deletion runs the departure ────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_describer_deleting_mid_round_moves_the_round_on(session: AsyncSession, setup_undercover_game):
    """The round passes the deleted describer, the game plays to its end, and they score nothing.

    Untimed phases (the default 0): before the fix the ghost stayed alive at the
    describer's seat, the next player's describe answered NotYourTurn, timer-expired
    answered timer_not_expired, and the host could not kick a seat that was gone.
    """
    # Prepare — the first non-host civilian in the order is about to describe
    setup, game_id = await _start_undercover(session, setup_undercover_game, 4)
    room_id, host_id = setup["room"].id, str(setup["users"][0].id)
    state = (await _fresh(session, Game, game_id)).live_state
    order = state["turns"][-1]["description_order"]
    roles = {p["user_id"]: p["role"] for p in state["players"]}
    victim_index = next(i for i, uid in enumerate(order) if uid != host_id and roles[uid] == "civilian")
    victim = order[victim_index]
    controller = UndercoverGameController(session)
    for uid in order[:victim_index]:
        await controller.submit_description(game_id, UUID(uid), "clue")

    # Act
    departed = await UserController(session).delete_user_account(UUID(victim), PASSWORD)

    # Assert — the departure ran, the round moved on
    game = await _fresh(session, Game, game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    assert victim in left_player_ids(game.live_state)
    ghost = next(p for p in game.live_state["players"] if p["user_id"] == victim)
    assert ghost["is_alive"] is False
    turn = game.live_state["turns"][-1]
    later = order[victim_index + 1 :]
    if later:
        assert turn["phase"] == "describing"
        assert turn["description_order"][turn["current_describer_index"]] == later[0]
    else:
        assert turn["phase"] == "voting"
    room = await _fresh(session, Room, room_id)
    assert room.type == RoomType.ACTIVE
    assert str(room.owner_id) == host_id
    assert (await session.exec(select(RoomUserLink).where(RoomUserLink.user_id == UUID(victim)))).all() == []
    assert (await session.exec(select(User).where(User.id == UUID(victim)))).first() is None
    assert departed == [DepartedRoom(room_id=room_id, game_id=game_id)]

    # Act — the table plays on: the rest describe, and everyone votes out the undercover
    await _describe_until_voting(session, game_id)
    undercover = next(uid for uid, role in roles.items() if role == "undercover")
    await _everyone_votes_for(session, game_id, undercover)

    # Assert — the game finishes (no FK error on the deleted player), who stayed scores
    game = await _fresh(session, Game, game_id)
    assert game.game_status == GameStatus.FINISHED
    assert game.live_state["winner"] == "civilians"
    assert victim not in game.live_state["winner_ids"]
    stats_owners = {str(s.user_id) for s in (await session.exec(select(UserStats))).all()}
    assert victim not in stats_owners
    assert {uid for uid in order if uid != victim} <= stats_owners


@pytest.mark.asyncio
async def test_the_host_deleting_mid_game_hands_the_room_to_a_player(session: AsyncSession, setup_undercover_game):
    """Ownership passes to a player, the room stays live with its game, and the new host can move on.

    Before: owner NULL, room INACTIVE, the game IN_PROGRESS — every next-round answered
    403 and the game could never finish. Eight players, so two undercovers: the host's
    departure alone never decides the game.
    """
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 8)
    room_id, host_id = setup["room"].id, setup["users"][0].id

    # Act
    departed = await UserController(session).delete_user_account(host_id, PASSWORD)

    # Assert — a player holds the room, its game still running
    room = await _fresh(session, Room, room_id)
    game = await _fresh(session, Game, game_id)
    assert room.type == RoomType.ACTIVE
    assert room.active_game_id == game_id
    assert game.game_status == GameStatus.IN_PROGRESS
    assert str(host_id) in left_player_ids(game.live_state)
    seated = {str(link.user_id) for link in (await session.exec(select(RoomUserLink))).all()}
    players = {p["user_id"]: p for p in game.live_state["players"]}
    assert room.owner_id is not None
    new_host = str(room.owner_id)
    assert new_host in seated
    assert players[new_host]["is_alive"] is True
    assert players[str(host_id)]["is_alive"] is False
    assert departed == [DepartedRoom(room_id=room_id, game_id=game_id)]

    # Act — the round resolves (a civilian voted out), then the new host opens the next one
    await _describe_until_voting(session, game_id)
    target = next(uid for uid, p in players.items() if p["is_alive"] and p["role"] == "civilian" and uid != new_host)
    await _everyone_votes_for(session, game_id, target)
    advanced = await UndercoverGameController(session).start_next_round(game_id, room_id, UUID(new_host))

    # Assert
    assert advanced.advanced is True
    game = await _fresh(session, Game, game_id)
    assert game.game_status == GameStatus.IN_PROGRESS
    assert len(game.live_state["turns"]) == 2
    assert game.live_state["turns"][-1]["phase"] == "describing"


@pytest.mark.asyncio
async def test_the_internal_delete_user_runs_the_departure_too(session: AsyncSession, setup_undercover_game):
    """``delete_user`` (no confirmation, internal) leaves the game the same way."""
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 4)
    victim = setup["users"][1].id

    # Act
    departed = await UserController(session).delete_user(victim)

    # Assert
    game = await _fresh(session, Game, game_id)
    assert str(victim) in left_player_ids(game.live_state)
    assert next(p for p in game.live_state["players"] if p["user_id"] == str(victim))["is_alive"] is False
    assert (await session.exec(select(User).where(User.id == victim))).first() is None
    assert departed == [DepartedRoom(room_id=setup["room"].id, game_id=game_id)]


@pytest.mark.asyncio
async def test_a_lobby_member_deleting_leaves_the_lobby(session: AsyncSession, create_user, create_room):
    """No game: the seat goes, the room stays the host's, the pair carries no game."""
    # Prepare
    host = await create_user(username="lobbyhost", email="lobbyhost@test.com")
    guest = await create_user(username="lobbyguest", email="lobbyguest@test.com")
    room = await create_room(owner=host)
    session.add(RoomUserLink(room_id=room.id, user_id=guest.id, connected=True))
    await session.commit()
    room_id, host_id, guest_id = room.id, host.id, guest.id

    # Act
    departed = await UserController(session).delete_user_account(guest_id, PASSWORD)

    # Assert
    assert departed == [DepartedRoom(room_id=room_id, game_id=None)]
    room = await _fresh(session, Room, room_id)
    assert room.type == RoomType.ACTIVE
    assert room.owner_id == host_id
    links = (await session.exec(select(RoomUserLink).where(RoomUserLink.room_id == room_id))).all()
    assert [link.user_id for link in links] == [host_id]


@pytest.mark.asyncio
async def test_a_wrong_password_leaves_every_seat_in_place(session: AsyncSession, setup_undercover_game):
    """The confirmation comes first: a refused deletion plays no departure."""
    # Prepare
    setup, game_id = await _start_undercover(session, setup_undercover_game, 4)
    victim = setup["users"][1].id

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await UserController(session).delete_user_account(victim, "not-the-password")
    game = await _fresh(session, Game, game_id)
    assert str(victim) not in left_player_ids(game.live_state)
    assert next(p for p in game.live_state["players"] if p["user_id"] == str(victim))["is_alive"] is True
    assert (await session.exec(select(RoomUserLink).where(RoomUserLink.user_id == victim))).first() is not None


# ─── F14: a Google-only account confirms with Google ─────────────────────────


@pytest.mark.asyncio
async def test_a_google_user_deletes_with_a_google_token_naming_the_account(
    api: httpx.AsyncClient, session: AsyncSession, test_app: FastAPI, google_settings: Settings
):
    """The real verification against a fake Google: the token's sub is the profile's."""
    # Prepare
    user, access_token = await _google_user(session, google_settings)
    test_app.dependency_overrides[get_social_auth_service] = lambda: _google_service(
        google_settings, OWNER_SUB, user.email_address
    )
    user_id = user.id

    # Act
    response = await api.request(
        "DELETE", DELETE_URL, json={"google_access_token": "fresh-google-token"}, headers=_bearer(access_token)
    )

    # Assert
    assert response.status_code == 204, response.text
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == user_id))).first() is None
    assert (await session.exec(select(AuthSession).where(AuthSession.user_id == user_id))).all() == []


@pytest.mark.asyncio
async def test_a_google_token_of_another_account_is_a_403(
    api: httpx.AsyncClient, session: AsyncSession, test_app: FastAPI, google_settings: Settings
):
    """A valid token for THIS app, but of another Google account: refused, nothing deleted."""
    # Prepare
    user, access_token = await _google_user(session, google_settings)
    test_app.dependency_overrides[get_social_auth_service] = lambda: _google_service(
        google_settings, "someone-else", "someone.else@test.com"
    )
    user_id = user.id

    # Act
    response = await api.request(
        "DELETE", DELETE_URL, json={"google_access_token": "their-token"}, headers=_bearer(access_token)
    )

    # Assert
    assert response.status_code == 403
    assert response.json()["error_key"] == "errors.api.googleAccountMismatch"
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == user_id))).first() is not None


@pytest.mark.asyncio
async def test_a_google_token_cannot_confirm_an_account_never_linked_to_google(
    session: AsyncSession, create_user, google_settings: Settings
):
    """An email account without a google_sub: no Google token names it."""
    # Prepare
    user = await create_user(username="emailonly", email="emailonly@test.com")
    service = _google_service(google_settings, OWNER_SUB, "emailonly@test.com")

    # Act / Assert
    with pytest.raises(GoogleAccountMismatchError):
        await UserController(session).delete_user_account(
            user.id, google_access_token="google-token", social_auth_service=service
        )
    assert (await session.exec(select(User).where(User.id == user.id))).first() is not None


@pytest.mark.asyncio
async def test_a_google_user_still_cannot_delete_with_a_typed_password(
    session: AsyncSession, google_settings: Settings
):
    """Port of the probe: the sentinel is unknowable, so any typed password is refused."""
    # Prepare
    user, _ = await _google_user(session, google_settings)

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await UserController(session).delete_user_account(user.id, "anything-the-user-could-type")
    assert (await session.exec(select(User).where(User.id == user.id))).first() is not None


@pytest.mark.asyncio
async def test_a_google_user_can_still_delete_after_a_password_reset(
    session: AsyncSession, google_settings: Settings, auth_controller: AuthController
):
    """Port of the probe's mitigating path: a reset sets a known password, which deletion accepts."""
    # Prepare
    user, _ = await _google_user(session, google_settings, email="g.reset@test.com")
    user_id = user.id
    email_service = _RecordingEmailService()
    await auth_controller.request_password_reset("g.reset@test.com", email_service)
    await auth_controller.reset_password(email_service.token, "Chosen-Passw0rd!")

    # Act
    await UserController(session).delete_user_account(user_id, "Chosen-Passw0rd!")

    # Assert
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == user_id))).first() is None


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"password": PASSWORD, "google_access_token": "google-token"}])
async def test_a_deletion_names_exactly_one_confirmation(
    api: httpx.AsyncClient, auth_controller: AuthController, create_user, body: dict
):
    """Neither, or both: a validation error, nothing deleted."""
    # Prepare
    await create_user(username="confirmer", email="confirmer@test.com")
    login = await auth_controller.login("confirmer@test.com", PASSWORD)

    # Act
    response = await api.request("DELETE", DELETE_URL, json=body, headers=_bearer(login.access_token))

    # Assert
    assert response.status_code == 422
    assert response.json()["error_key"] == "errors.api.validation"
    assert (await api.get(ME_URL, headers=_bearer(login.access_token))).status_code == 200


@pytest.mark.asyncio
async def test_a_password_user_deletes_with_the_password_through_the_route(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, create_user
):
    """The password confirmation still works end to end."""
    # Prepare
    user = await create_user(username="pwdeleter", email="pwdeleter@test.com")
    login = await auth_controller.login("pwdeleter@test.com", PASSWORD)

    # Act
    response = await api.request("DELETE", DELETE_URL, json={"password": PASSWORD}, headers=_bearer(login.access_token))

    # Assert
    assert response.status_code == 204, response.text
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == user.id))).first() is None


# ─── F15: the avatar URL ──────────────────────────────────────────────────────

GOOGLE_AVATAR = "https://lh3.googleusercontent.com/a/xyz"
REFUSED_AVATARS = {
    "plain http": "http://x",
    "another host": "https://evil.example/a.png",
    "too long": "https://lh3.googleusercontent.com/a/" + "x" * (AVATAR_URL_MAX_LENGTH + 100),
    "javascript": "javascript:void(0)",
    "20k tracker": "https://tracker.invalid/p.gif?" + "x" * 20_000,
}


@pytest.mark.asyncio
@pytest.mark.parametrize("name", list(REFUSED_AVATARS))
async def test_a_profile_picture_off_googles_cdn_is_refused(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, create_user, name: str
):
    """Port of the probe's avatar half: a 20k URL and a javascript: one were stored and shown."""
    # Prepare
    user = await create_user(username="avatarist", email="avatarist@test.com")
    login = await auth_controller.login("avatarist@test.com", PASSWORD)

    # Act
    response = await api.patch(
        f"/api/v1/users/{user.id}",
        json={"profile_picture_url": REFUSED_AVATARS[name]},
        headers=_bearer(login.access_token),
    )

    # Assert
    assert response.status_code == 400
    assert response.json()["error_key"] == "errors.api.invalidAvatarUrl"
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == user.id))).one().profile_picture_url is None


@pytest.mark.asyncio
async def test_a_google_avatar_is_accepted_and_shown(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, create_user
):
    # Prepare
    user = await create_user(username="googlepic", email="googlepic@test.com")
    await create_user(username="viewer", email="viewer@test.com")
    login = await auth_controller.login("googlepic@test.com", PASSWORD)
    viewer_login = await auth_controller.login("viewer@test.com", PASSWORD)

    # Act
    response = await api.patch(
        f"/api/v1/users/{user.id}", json={"profile_picture_url": GOOGLE_AVATAR}, headers=_bearer(login.access_token)
    )
    public = await api.get(f"/api/v1/users/{user.id}", headers=_bearer(viewer_login.access_token))

    # Assert
    assert response.status_code == 200, response.text
    session.expunge_all()
    assert (await session.exec(select(User).where(User.id == user.id))).one().profile_picture_url == GOOGLE_AVATAR
    assert public.status_code == 200
    assert public.json()["profile_picture_url"] == GOOGLE_AVATAR


# ─── F01: a password change signs out the other sessions ─────────────────────


@pytest.mark.asyncio
async def test_a_password_change_revokes_the_other_sessions_and_keeps_the_callers(
    api: httpx.AsyncClient, auth_controller: AuthController, session: AsyncSession, create_user
):
    """Two devices signed in; the change is made from the first: the second is signed out."""
    # Prepare
    user = await create_user(username="twodevices", email="twodevices@test.com")
    phone = await auth_controller.login("twodevices@test.com", PASSWORD)
    laptop = await auth_controller.login("twodevices@test.com", PASSWORD)
    phone_sid = auth_controller.decode_token(phone.access_token).sid
    laptop_sid = auth_controller.decode_token(laptop.access_token).sid

    # Act
    response = await api.patch(
        f"/api/v1/users/{user.id}/password",
        json={"current_password": PASSWORD, "new_password": "brand-new-pass"},
        headers=_bearer(phone.access_token),
    )

    # Assert — re-read the rows
    assert response.status_code == 200, response.text
    session.expunge_all()
    rows = {str(row.id): row for row in (await session.exec(select(AuthSession))).all()}
    assert rows[str(phone_sid)].revoked_at is None
    assert rows[str(laptop_sid)].revoked_at is not None
    assert (await api.get(ME_URL, headers=_bearer(phone.access_token))).status_code == 200
    signed_out = await api.get(ME_URL, headers=_bearer(laptop.access_token))
    assert signed_out.status_code == 401
    assert signed_out.json()["error_key"] == "errors.api.sessionRevoked"


@pytest.mark.asyncio
async def test_a_password_change_without_a_known_session_revokes_every_session(
    session: AsyncSession, auth_controller: AuthController, create_user
):
    """A caller on a legacy token (no ``sid``) keeps nothing: every session is signed out."""
    # Prepare
    user = await create_user(username="legacy", email="legacy@test.com")
    await auth_controller.login("legacy@test.com", PASSWORD)
    await auth_controller.login("legacy@test.com", PASSWORD)

    # Act
    await UserController(session).update_user_password(user.id, PASSWORD, "brand-new-pass")

    # Assert
    session.expunge_all()
    rows = (await session.exec(select(AuthSession).where(AuthSession.user_id == user.id))).all()
    assert len(rows) == 2
    assert all(row.revoked_at is not None for row in rows)
    stored = (await session.exec(select(User).where(User.id == user.id))).one()
    assert verify_password("brand-new-pass", stored.password) is True
