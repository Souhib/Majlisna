"""TQ-02: Google token verification, run for real against a fake Google (httpx.MockTransport).

Every earlier test replaced ``verify_google_access_token`` with an AsyncMock, so the
whole body of it (21% line coverage) never ran: deleting the audience check — the
account-takeover guard of CLAUDE.md ("a Google token issued to another app must be
refused") — passed CI (mutant V03). Here only the network is fake: the service's own
code decides.
"""

from collections.abc import Callable

import httpx
import pytest

from majlisna.api.schemas.error import InvalidCredentialsError
from majlisna.api.schemas.social_auth import SocialTokenPayload
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.settings import Settings

OUR_CLIENT_ID = "majlisna-web.apps.googleusercontent.com"
OTHER_CLIENT_ID = "some-other-app.apps.googleusercontent.com"
TOKENINFO_PATH = "/tokeninfo"
USERINFO_PATH = "/oauth2/v3/userinfo"
GOOGLE_SUB = "109876543210"


def _settings(client_id: str = OUR_CLIENT_ID) -> Settings:
    return Settings(  # type: ignore[call-arg]
        database_url="sqlite+aiosqlite:///:memory:",
        google_client_id_web=client_id,
    )


def _token_info(**overrides: object) -> dict:
    return {"aud": OUR_CLIENT_ID, "azp": OUR_CLIENT_ID, "sub": GOOGLE_SUB, "expires_in": "3599"} | overrides


def _user_info(**overrides: object) -> dict:
    return {
        "sub": GOOGLE_SUB,
        "email": "player@gmail.com",
        "email_verified": True,
        "given_name": "Aisha",
        "family_name": "Rahman",
        "picture": "https://lh3.googleusercontent.com/a/photo",
    } | overrides


class FakeGoogle:
    """Answers tokeninfo and userinfo; records what it was asked."""

    def __init__(self, token_info: httpx.Response, user_info: httpx.Response) -> None:
        self.answers = {TOKENINFO_PATH: token_info, USERINFO_PATH: user_info}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.answers[request.url.path]

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]


def _service(google: Callable[[httpx.Request], httpx.Response], client_id: str = OUR_CLIENT_ID) -> SocialAuthService:
    return SocialAuthService(_settings(client_id), transport=httpx.MockTransport(google))


async def test_a_token_for_this_app_returns_the_verified_profile():
    """The happy path: both endpoints asked, the profile returned."""
    # Prepare
    google = FakeGoogle(httpx.Response(200, json=_token_info()), httpx.Response(200, json=_user_info()))

    # Act
    payload = await _service(google).verify_google_access_token("ya29.good")

    # Assert
    assert payload == SocialTokenPayload(
        sub=GOOGLE_SUB,
        email="player@gmail.com",
        email_verified=True,
        first_name="Aisha",
        last_name="Rahman",
        picture="https://lh3.googleusercontent.com/a/photo",
    )
    assert google.paths() == [TOKENINFO_PATH, USERINFO_PATH]
    assert google.requests[0].url.params["access_token"] == "ya29.good"
    assert google.requests[1].headers["authorization"] == "Bearer ya29.good"


@pytest.mark.parametrize(
    "token_info",
    [
        _token_info(aud=OTHER_CLIENT_ID, azp=OTHER_CLIENT_ID),
        _token_info(aud=None, azp=None),
    ],
    ids=["minted-for-another-app", "no-audience"],
)
async def test_a_token_minted_for_another_app_is_refused(token_info: dict):
    """The account-takeover guard: userinfo answers for ANY valid Google token."""
    # Prepare
    google = FakeGoogle(httpx.Response(200, json=token_info), httpx.Response(200, json=_user_info()))

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(google).verify_google_access_token("ya29.foreign")
    assert google.paths() == [TOKENINFO_PATH]  # refused before the profile is even read


async def test_the_audience_may_be_named_by_azp_alone():
    """Google puts the web client in ``azp`` when ``aud`` names another of the project's clients."""
    # Prepare
    google = FakeGoogle(
        httpx.Response(200, json=_token_info(aud=OTHER_CLIENT_ID, azp=OUR_CLIENT_ID)),
        httpx.Response(200, json=_user_info()),
    )

    # Act
    payload = await _service(google).verify_google_access_token("ya29.azp")

    # Assert
    assert payload.sub == GOOGLE_SUB


async def test_an_unverified_google_email_is_refused():
    """Google's verified email is what proves the mailbox (and lets SEC F02 reset an account)."""
    # Prepare
    google = FakeGoogle(
        httpx.Response(200, json=_token_info()), httpx.Response(200, json=_user_info(email_verified=False))
    )

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(google).verify_google_access_token("ya29.unverified")


async def test_a_sub_that_differs_between_tokeninfo_and_userinfo_is_refused():
    """The two answers must be about the same Google account."""
    # Prepare
    google = FakeGoogle(
        httpx.Response(200, json=_token_info()), httpx.Response(200, json=_user_info(sub="another-account"))
    )

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(google).verify_google_access_token("ya29.mismatch")


@pytest.mark.parametrize("status", [400, 401, 500])
async def test_tokeninfo_refusing_the_token_is_invalid_credentials_not_a_500(status: int):
    """Google answers 400 for an expired or forged token: that is a 401 for the player."""
    # Prepare
    google = FakeGoogle(httpx.Response(status, json={"error": "invalid_token"}), httpx.Response(200, json=_user_info()))

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(google).verify_google_access_token("ya29.expired")


async def test_userinfo_refusing_the_token_is_invalid_credentials():
    """The second call failing is the same refusal."""
    # Prepare
    google = FakeGoogle(httpx.Response(200, json=_token_info()), httpx.Response(401, json={"error": "invalid"}))

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(google).verify_google_access_token("ya29.revoked")


async def test_a_profile_without_an_email_is_invalid_credentials():
    """A malformed userinfo answer is a refusal, not a KeyError (a 500)."""
    # Prepare
    profile = _user_info()
    del profile["email"]
    google = FakeGoogle(httpx.Response(200, json=_token_info()), httpx.Response(200, json=profile))

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(google).verify_google_access_token("ya29.no-email")


async def test_google_unreachable_is_invalid_credentials():
    """A network failure is a refusal too, never an unhandled exception."""

    # Prepare
    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(unreachable).verify_google_access_token("ya29.offline")


async def test_without_a_configured_client_id_nothing_is_accepted():
    """Fails closed: no GOOGLE_CLIENT_ID_WEB, no Google sign-in (and Google is not asked)."""
    # Prepare
    google = FakeGoogle(httpx.Response(200, json=_token_info()), httpx.Response(200, json=_user_info()))

    # Act / Assert
    with pytest.raises(InvalidCredentialsError):
        await _service(google, client_id="").verify_google_access_token("ya29.good")
    assert google.requests == []
