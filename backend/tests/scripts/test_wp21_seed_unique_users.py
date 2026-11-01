"""The seed never draws one username or email address twice (WP-21).

On PostgreSQL the startup DDL now makes ``lower(username)`` unique
(``ix_user_username_lower``), the backstop behind ``username_claim_lock``. The dev / E2E
seed (``--create-db``) builds the schema first, then draws its random users from Faker,
which repeats a ``user_name()`` in about 0.14 % of 15-user seeds: that seed used to store
two accounts of one name, and with the index it would crash the E2E reseed instead.
"""

from collections.abc import Iterator
from itertools import count

import pytest
from faker import Faker
from faker.providers import BaseProvider
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from majlisna.api.models.table import User
from scripts import generate_fake_data

# A draw that repeats its first name, as Faker sometimes does.
REPEATING_USERNAMES = ("omar.khan", "omar.khan", "layla.haddad", "yusuf12", "zbakri")


class RepeatingDrawProvider(BaseProvider):
    """Faker's user_name() and email(), replaced by a draw known to repeat."""

    def __init__(self, generator: Faker, usernames: Iterator[str]) -> None:
        super().__init__(generator)
        self._usernames = usernames
        self._emails = count()

    def user_name(self) -> str:
        return next(self._usernames)

    def email(self, safe: bool = True, domain: str | None = None) -> str:  # noqa: ARG002
        return f"seed{next(self._emails)}@example.org"


class RepeatingEmailProvider(RepeatingDrawProvider):
    """The same, with the repetition on the email address."""

    def email(self, safe: bool = True, domain: str | None = None) -> str:  # noqa: ARG002
        number = next(self._emails)
        return f"seed{max(number - 1, 0)}@example.org"


def _faker_with(provider_class: type[RepeatingDrawProvider], usernames: Iterator[str]) -> Faker:
    faker = Faker()
    faker.add_provider(provider_class(faker, usernames))
    return faker


@pytest.fixture(autouse=True)
def fast_password_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    """bcrypt is irrelevant here and slow; the stored value only has to be a string."""
    monkeypatch.setattr(generate_fake_data, "get_password_hash", lambda password: f"hashed:{password}")


async def test_random_seed_users_never_share_a_username(session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    # Prepare
    monkeypatch.setattr(generate_fake_data, "fake", _faker_with(RepeatingDrawProvider, iter(REPEATING_USERNAMES)))

    # Act
    await generate_fake_data.create_random_users(session, 3)

    # Assert: re-read from the database, compared the way the unique index compares
    rows = await session.exec(select(func.lower(User.username)))
    usernames = list(rows.all())
    assert len(usernames) == 3
    assert len(set(usernames)) == 3


async def test_random_seed_users_never_share_an_email_address(session: AsyncSession, monkeypatch: pytest.MonkeyPatch):
    # Prepare
    usernames = (f"seed.user{number}" for number in count())
    monkeypatch.setattr(generate_fake_data, "fake", _faker_with(RepeatingEmailProvider, usernames))

    # Act
    await generate_fake_data.create_random_users(session, 3)

    # Assert
    rows = await session.exec(select(func.lower(User.email_address)).order_by(col(User.email_address)))
    emails = list(rows.all())
    assert len(emails) == 3
    assert len(set(emails)) == 3
