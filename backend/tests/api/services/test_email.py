"""Tests for EmailService.

The whole point of `_send` returning a bool is that a mail problem must never
break the request that triggered it. It did not hold: the handler named
`resend.exceptions.ApiError`, which does not exist in the SDK.
"""

from unittest.mock import patch

import pytest
import resend

from majlisna.api.services.email import EmailService
from majlisna.settings import Settings


def _service() -> EmailService:
    return EmailService(Settings(database_url="sqlite+aiosqlite:///:memory:", resend_api_key="re_test_key"))  # type: ignore[call-arg]


@pytest.mark.asyncio
async def test_send_returns_false_when_the_sdk_raises():
    """A failed send is reported, not raised.

    An `except` tuple naming a missing attribute is only evaluated once something
    actually raises — so the happy path never noticed, while every real failure
    raised `AttributeError` out of the handler. On the registration path that
    surfaced as a 500 *after* the user row had been committed: the account
    existed and the caller was told it had failed.
    """
    # Prepare
    service = _service()

    # Act
    with patch.object(resend.Emails, "send", side_effect=resend.exceptions.ResendError("boom", "", "", 500)):
        sent = await service.send_verification_email("a@b.com", "tester", "https://example.com/v")

    # Assert
    assert sent is False


@pytest.mark.asyncio
async def test_send_returns_false_on_a_network_error():
    """Network failures are the other half of "must not break the caller"."""
    # Prepare
    service = _service()

    # Act
    with patch.object(resend.Emails, "send", side_effect=TimeoutError):
        sent = await service.send_password_reset_email("a@b.com", "tester", "https://example.com/r")

    # Assert
    assert sent is False


def test_the_handled_exception_classes_all_exist():
    """Pins the names themselves — a typo here is invisible until a send fails.

    `NoContentError` is listed separately on purpose: it is the one class in the
    SDK that does not inherit from `ResendError`.
    """
    assert issubclass(resend.exceptions.ResendError, Exception)
    assert issubclass(resend.exceptions.NoContentError, Exception)
    assert not issubclass(resend.exceptions.NoContentError, resend.exceptions.ResendError)


@pytest.mark.asyncio
async def test_send_is_skipped_without_an_api_key():
    """No key configured is a no-op, not an error."""
    # Prepare
    service = EmailService(Settings(database_url="sqlite+aiosqlite:///:memory:", resend_api_key=""))  # type: ignore[call-arg]

    # Act
    sent = await service.send_verification_email("a@b.com", "tester", "https://example.com/v")

    # Assert
    assert sent is False
