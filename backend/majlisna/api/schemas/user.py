from typing import Self
from uuid import UUID

import pydantic
from pydantic_core import PydanticCustomError

from majlisna.api.models.user import refuse_password_over_bcrypt_limit
from majlisna.api.schemas.shared import BaseModel


class DeleteAccountRequest(BaseModel):
    """How the owner confirms a deletion: EXACTLY one of the two (SEC F14).

    - ``password``: an account with a password (checked in bytes, SEC F10);
    - ``google_access_token``: a fresh Google access token, verified like a sign-in
      (``SocialAuthService``, the same audience check), whose ``sub`` must be the
      account's ``google_sub``. A Google-only account's password is a random value its
      owner never saw, so it could only delete after a password reset.
    """

    password: str | None = None
    google_access_token: str | None = None

    _password_fits_bcrypt = pydantic.field_validator("password", mode="before")(refuse_password_over_bcrypt_limit)

    @pydantic.model_validator(mode="after")
    def exactly_one_confirmation(self) -> Self:
        """Neither or both: a 422. A ``PydanticCustomError``, not a ``ValueError``: the
        latter puts the exception object in the error's ``ctx``, which the app's
        validation handler cannot serialise (it answered a 500)."""
        if (self.password is None) == (self.google_access_token is None):
            raise PydanticCustomError(
                "confirmation_required", "Confirm the deletion with either password or google_access_token"
            )
        return self


class DepartedRoom(BaseModel):
    """A room an account deletion left, for the route's socket detach and notification.

    ``game_id`` is the room's active game read BEFORE the departure (which can end it
    and clear ``Room.active_game_id``), as ``notify_member_removed`` needs.
    """

    room_id: UUID
    game_id: UUID | None = None
