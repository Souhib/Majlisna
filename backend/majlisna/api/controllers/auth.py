import re
import secrets
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.constants import (
    AUTH_PROVIDER_EMAIL,
    AUTH_PROVIDER_GOOGLE,
    EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS,
    PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
)
from majlisna.api.controllers.shared import (
    async_get_password_hash,
    async_verify_password,
    get_password_hash,
    verify_password,
)
from majlisna.api.models.table import User
from majlisna.api.models.token import EmailVerificationToken, PasswordResetToken
from majlisna.api.models.user import UserCreate
from majlisna.api.schemas.auth import LoginResult, LoginUserData, TokenPairResponse, TokenPayload
from majlisna.api.schemas.error import (
    InvalidCredentialsError,
    InvalidOrExpiredTokenError,
    InvalidTokenError,
    TokenExpiredError,
    UserNotFoundError,
)
from majlisna.api.schemas.social_auth import SocialLoginResponse, SocialLoginUserData, SocialTokenPayload
from majlisna.api.services.email import EmailService
from majlisna.api.services.social_auth import SocialAuthService
from majlisna.settings import Settings

# JWT `type` claim values, used to keep access and refresh tokens from being
# used interchangeably (a refresh token must not authenticate API calls, and an
# access token must not mint a new token pair at /refresh).
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"

# Precomputed bcrypt hash used only to equalize login response time when the
# email is unknown, so an attacker can't enumerate accounts by timing. Never
# matches any real password.
_DUMMY_PASSWORD_HASH = "$2b$12$crI5y/d5tqE1WJc6OVnBvOpy.Qj7TL6eITLs6R0pNjaB5mAoLRBFq"


class AuthController:
    """Controller for authentication operations."""

    def __init__(self, session: AsyncSession, settings: Settings):
        self.session = session
        self.settings = settings

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a plain password against a hashed password.

        Uses passlib bcrypt context from shared module.

        :param plain_password: The plain text password to verify.
        :param hashed_password: The hashed password to verify against.
        :return: True if the password matches, False otherwise.
        """
        return verify_password(plain_password, hashed_password)

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Hash a password using the shared password context.

        :param password: The plain text password to hash.
        :return: The hashed password string.
        """
        return get_password_hash(password)

    def create_access_token(self, user_id: str, email: str) -> str:
        """Create a JWT access token.

        :param user_id: The user's unique identifier.
        :param email: The user's email address.
        :return: Encoded JWT access token string.
        """
        expire = datetime.now(UTC) + timedelta(minutes=self.settings.access_token_expire_minutes)
        payload = {
            "sub": user_id,
            "email": email,
            "exp": expire,
            "type": TOKEN_TYPE_ACCESS,
        }
        return jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_encryption_algorithm)

    def create_refresh_token(self, user_id: str, email: str) -> str:
        """Create a JWT refresh token with longer expiry.

        :param user_id: The user's unique identifier.
        :param email: The user's email address.
        :return: Encoded JWT refresh token string.
        """
        expire = datetime.now(UTC) + timedelta(days=self.settings.refresh_token_expire_days)
        payload = {
            "sub": user_id,
            "email": email,
            "exp": expire,
            "type": TOKEN_TYPE_REFRESH,
        }
        return jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_encryption_algorithm)

    def create_token_pair(self, user_id: str, email: str) -> TokenPairResponse:
        """Create both access and refresh tokens.

        :param user_id: The user's unique identifier.
        :param email: The user's email address.
        :return: TokenPairResponse with both tokens.
        """
        return TokenPairResponse(
            access_token=self.create_access_token(user_id, email),
            refresh_token=self.create_refresh_token(user_id, email),
        )

    def decode_token(self, token: str, expected_type: str | None = None) -> TokenPayload:
        """Decode and validate a JWT token.

        :param token: The JWT token string to decode.
        :param expected_type: If given ("access" or "refresh"), reject a token
            whose `type` claim does not match. Callers that don't care (e.g.
            unit tests) omit it and no type check is performed.
        :return: TokenPayload with the decoded claims.
        :raises InvalidTokenError: If the token is malformed, invalid, or of the
            wrong type.
        :raises TokenExpiredError: If the token has expired.
        """
        try:
            payload = jwt.decode(
                token,
                self.settings.jwt_secret_key,
                algorithms=[self.settings.jwt_encryption_algorithm],
            )
            token_payload = TokenPayload(**payload)
        except JWTError as e:
            if "expired" in str(e).lower():
                raise TokenExpiredError() from e
            raise InvalidTokenError() from e

        if expected_type is not None and token_payload.type != expected_type:
            raise InvalidTokenError()
        return token_payload

    async def login(self, email: str, password: str) -> LoginResult:
        """Authenticate a user and return tokens with user data.

        :param email: The user's email address.
        :param password: The user's plain text password.
        :return: LoginResult with tokens and user info.
        :raises InvalidCredentialsError: If the email or password is incorrect.
        """
        user = await self.get_user_by_email(email)
        if user is None or user.auth_provider != AUTH_PROVIDER_EMAIL:
            # Run a bcrypt verify against a dummy hash so the response time for
            # an unknown / non-password account matches the wrong-password path,
            # preventing account enumeration by timing.
            await async_verify_password(password, _DUMMY_PASSWORD_HASH)
            raise InvalidCredentialsError(email=email)

        if not await async_verify_password(password, user.password):
            raise InvalidCredentialsError(email=email)

        tokens = self.create_token_pair(str(user.id), user.email_address)
        return LoginResult(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            user=LoginUserData(
                id=str(user.id),
                username=user.username,
                email=user.email_address,
            ),
        )

    async def register(self, user_create: UserCreate) -> User:
        """Register a new user with a hashed password.

        :param user_create: The user creation data.
        :return: The newly created User.
        """
        hashed_password = await async_get_password_hash(user_create.password)
        user_data = user_create.model_dump()
        user_data["password"] = hashed_password
        new_user = User(**user_data)
        self.session.add(new_user)
        await self.session.commit()
        await self.session.refresh(new_user)
        return new_user

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by their email address.

        :param email: The email address to search for.
        :return: The User if found, None otherwise.
        """
        result = await self.session.exec(select(User).where(User.email_address == email))
        return result.first()

    async def request_password_reset(self, email: str, email_service: EmailService) -> bool:
        """Generate a password reset token and send email."""
        user = await self.get_user_by_email(email)
        if not user:
            # Don't reveal whether user exists — return silently
            logger.debug("Password reset requested for unknown email")
            return True

        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
        reset_token = PasswordResetToken(user_id=user.id, token=token, expires_at=expires_at)
        self.session.add(reset_token)
        await self.session.commit()

        reset_url = f"{self.settings.frontend_url}/auth/reset-password?token={token}"
        await email_service.send_password_reset_email(user.email_address, user.username, reset_url)
        return True

    async def reset_password(self, token: str, new_password: str) -> bool:
        """Validate reset token and update password."""
        result = await self.session.exec(
            select(PasswordResetToken).where(PasswordResetToken.token == token).where(PasswordResetToken.used == False)  # noqa: E712
        )
        reset_token = result.first()
        if not reset_token or reset_token.expires_at < datetime.now(UTC):
            raise InvalidOrExpiredTokenError()

        user = (await self.session.exec(select(User).where(User.id == reset_token.user_id))).first()
        if not user:
            raise UserNotFoundError(user_id=reset_token.user_id)

        user.password = await async_get_password_hash(new_password)
        reset_token.used = True
        self.session.add(user)
        self.session.add(reset_token)
        await self.session.commit()
        return True

    async def send_verification_email(self, user: User, email_service: EmailService) -> bool:
        """Generate verification token and send email."""
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(hours=EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS)
        verify_token = EmailVerificationToken(user_id=user.id, token=token, expires_at=expires_at)
        self.session.add(verify_token)
        await self.session.commit()

        verify_url = f"{self.settings.frontend_url}/auth/verify-email?token={token}"
        await email_service.send_verification_email(user.email_address, user.username, verify_url)
        return True

    async def verify_email(self, token: str) -> bool:
        """Validate verification token and mark email as verified."""
        result = await self.session.exec(
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token == token)
            .where(EmailVerificationToken.used == False)  # noqa: E712
        )
        verify_token = result.first()
        if not verify_token or verify_token.expires_at < datetime.now(UTC):
            raise InvalidOrExpiredTokenError()

        user = (await self.session.exec(select(User).where(User.id == verify_token.user_id))).first()
        if not user:
            raise UserNotFoundError(user_id=verify_token.user_id)

        user.email_verified = True
        verify_token.used = True
        self.session.add(user)
        self.session.add(verify_token)
        await self.session.commit()
        return True

    async def resend_verification(self, email: str, email_service: EmailService) -> bool:
        """Resend verification email."""
        user = await self.get_user_by_email(email)
        if not user or user.email_verified:
            return True  # Don't reveal info
        return await self.send_verification_email(user, email_service)

    async def social_login(
        self,
        social_auth_service: SocialAuthService,
        access_token: str,
    ) -> SocialLoginResponse:
        """Authenticate a user via Google OAuth2.

        Flow:
        1. Verify access token with Google's userinfo API
        2. Look up user by google_sub (fast path for returning users)
        3. If not found, look up by email and link google_sub
        4. If email not found, create new user (auto-verified, sentinel password)
        5. Return JWT pair + is_new_user flag

        :param social_auth_service: Service to verify tokens.
        :param access_token: OAuth2 access token from Google.
        :return: SocialLoginResponse with JWT pair and is_new_user flag.
        :raises InvalidCredentialsError: If token verification fails.
        """
        token_payload = await social_auth_service.verify_google_access_token(access_token)

        # Fast path: look up by google_sub
        user = await self._get_user_by_google_sub(token_payload.sub)
        if user:
            return await self._complete_social_login(user, is_new_user=False)

        # Look up by email and link
        user = await self.get_user_by_email(token_payload.email)
        if user:
            await self._link_google_sub(user, token_payload.sub)
            return await self._complete_social_login(user, is_new_user=False)

        # Create new user
        user = await self._create_social_user(token_payload)
        return await self._complete_social_login(user, is_new_user=True)

    async def _get_user_by_google_sub(self, sub: str) -> User | None:
        """Look up a user by their Google subject identifier."""
        result = await self.session.exec(select(User).where(User.google_sub == sub))
        return result.one_or_none()

    async def _link_google_sub(self, user: User, sub: str) -> None:
        """Link a Google sub to an existing user account."""
        user.google_sub = sub
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        logger.info("Linked Google account to existing user", user_id=str(user.id))

    async def _create_social_user(self, token_payload: SocialTokenPayload) -> User:
        """Create a new user from Google login.

        Username is generated from Google name, with a random suffix if taken.
        Password is a random sentinel that never matches real input.
        """
        username = self._generate_username(token_payload)
        # Ensure uniqueness
        existing = await self.session.exec(select(User).where(User.username == username))
        if existing.one_or_none():
            username = f"{username}_{secrets.token_hex(2)}"

        random_password = secrets.token_urlsafe(48)[:72]
        password_hash = await async_get_password_hash(random_password)

        user = User(
            username=username,
            email_address=token_payload.email,
            password=password_hash,
            email_verified=True,
            google_sub=token_payload.sub,
            auth_provider=AUTH_PROVIDER_GOOGLE,
            profile_picture_url=token_payload.picture,
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        logger.info("Created new user via Google login", user_id=str(user.id), email=token_payload.email)
        return user

    @staticmethod
    def _generate_username(token_payload: SocialTokenPayload) -> str:
        """Generate a username from Google name or email prefix."""
        first = token_payload.first_name or ""
        last = token_payload.last_name or ""
        raw = f"{first}_{last}".strip("_") if (first or last) else token_payload.email.split("@")[0]
        # Lowercase, replace spaces with underscores, strip non-alphanumeric (except underscores)
        username = re.sub(r"[^a-z0-9_]", "", raw.lower().replace(" ", "_"))
        return username or "user"

    async def _complete_social_login(self, user: User, is_new_user: bool) -> SocialLoginResponse:
        """Complete social login: generate tokens and return response."""
        tokens = self.create_token_pair(str(user.id), user.email_address)

        logger.info(
            "Social login successful",
            user_id=str(user.id),
            is_new_user=is_new_user,
        )

        return SocialLoginResponse(
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
            expires_in=self.settings.access_token_expire_minutes * 60,
            is_new_user=is_new_user,
            user=SocialLoginUserData(
                id=str(user.id),
                username=user.username,
                email=user.email_address,
            ),
        )
