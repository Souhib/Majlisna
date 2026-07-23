"""Social authentication service for Google Sign-In.

Handles access token verification via Google's userinfo API.
"""

import httpx
from loguru import logger

from majlisna.api.schemas.error import InvalidCredentialsError
from majlisna.api.schemas.social_auth import SocialTokenPayload
from majlisna.settings import Settings


class SocialAuthService:
    """Service for verifying Google OAuth2 access tokens."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def verify_google_access_token(self, access_token: str) -> SocialTokenPayload:
        """Verify a Google OAuth2 access token and return the user's info.

        First checks the token's audience (that it was minted for THIS app) via
        Google's tokeninfo endpoint, then fetches the profile via userinfo.
        Without the audience check, a valid Google token issued for any other
        application would be accepted, enabling account takeover.

        :param access_token: The Google OAuth2 access token from the client.
        :return: Verified user info from Google.
        :raises InvalidCredentialsError: If the token is invalid, expired, or was
            issued for a different application.
        """
        expected_client_id = self.settings.google_client_id_web
        if not expected_client_id:
            logger.error("GOOGLE_CLIENT_ID_WEB is not configured; refusing to verify Google tokens")
            raise InvalidCredentialsError()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Audience check — confirm the token was issued for this app.
                token_info_resp = await client.get(
                    "https://oauth2.googleapis.com/tokeninfo",
                    params={"access_token": access_token},
                )
                token_info_resp.raise_for_status()
                token_info = token_info_resp.json()

                if expected_client_id not in (token_info.get("aud"), token_info.get("azp")):
                    logger.warning(
                        "Google token audience mismatch",
                        aud=token_info.get("aud"),
                        azp=token_info.get("azp"),
                    )
                    raise InvalidCredentialsError()

                # 2. Profile fetch — name and picture for account creation.
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                resp.raise_for_status()
                user_info = resp.json()

            if not user_info.get("email_verified", False):
                raise InvalidCredentialsError()

            # The subject must be consistent between the two endpoints.
            token_sub = token_info.get("sub")
            if token_sub and token_sub != user_info.get("sub"):
                raise InvalidCredentialsError()

            return SocialTokenPayload(
                sub=user_info["sub"],
                email=user_info["email"],
                email_verified=user_info.get("email_verified", False),
                first_name=user_info.get("given_name"),
                last_name=user_info.get("family_name"),
                picture=user_info.get("picture"),
            )

        except InvalidCredentialsError:
            raise
        except Exception as e:
            logger.warning("Google access token verification failed", error=str(e))
            raise InvalidCredentialsError() from e
