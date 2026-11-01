import random

import pycountry
import pydantic
import pytest
from faker import Faker

from majlisna.api.constants import AVATAR_URL_MAX_LENGTH
from majlisna.api.models.user import UserBase, UserUpdate
from majlisna.api.schemas.error import InvalidAvatarUrlError
from majlisna.api.schemas.user import DeleteAccountRequest


def test_valid_username_email_address_country(faker: Faker):
    username = faker.user_name()
    email_address = faker.email()
    country = random.choice([country.alpha_3 for country in pycountry.countries])
    user = UserBase(username=username, email_address=email_address, country=country)
    assert user.username == username
    assert user.email_address == email_address
    assert user.country == country


def test_valid_username_email_address_no_country(faker: Faker):
    username = faker.user_name()
    email_address = faker.email()
    user = UserBase(username=username, email_address=email_address)
    assert user.username == username
    assert user.email_address == email_address
    assert user.country is None


def test_empty_string_username(faker: Faker):
    username = ""
    email_address = faker.email()
    country = random.choice([country.alpha_3 for country in pycountry.countries])
    with pytest.raises(ValueError):
        _ = UserBase(username=username, email_address=email_address, country=country)


def test_empty_string_email_address_invalid_email(faker: Faker):
    username = faker.user_name()
    email_address = "invalid_email"
    country = random.choice([country.alpha_3 for country in pycountry.countries])
    with pytest.raises(pydantic.ValidationError):
        _ = UserBase(username=username, email_address=email_address, country=country)


def test_invalid_country_code(faker: Faker):
    username = faker.user_name()
    email_address = faker.email()
    country = "XYZ"
    with pytest.raises(ValueError):
        _ = UserBase(username=username, email_address=email_address, country=country)


# ========== WP-27, SEC F15: the profile picture is Google's avatar CDN, bounded ==========


@pytest.mark.parametrize(
    "url",
    [
        "https://lh3.googleusercontent.com/a/xyz",
        "https://lh6.googleusercontent.com/-abc/AAAA/photo.jpg?sz=96",
        "HTTPS://LH3.GoogleUserContent.com/a/xyz",
    ],
)
def test_a_google_avatar_url_is_accepted(url: str):
    # Act
    update = UserUpdate(profile_picture_url=url)

    # Assert
    assert update.profile_picture_url == url


@pytest.mark.parametrize(
    "url",
    [
        "http://x",
        "http://lh3.googleusercontent.com/a/xyz",  # https only
        "https://evil.example/a.png",
        "javascript:void(0)",
        "data:image/png;base64,AAAA",
        "//lh3.googleusercontent.com/a/xyz",  # no scheme
        "https://googleusercontent.com/a.png",  # the bare domain is not a suffix match
        "https://evilgoogleusercontent.com/a.png",  # no dot before the suffix
        "https://lh3.googleusercontent.com.evil.example/a.png",
        "https://lh3.googleusercontent.com@evil.example/a.png",  # userinfo
        "https://evil.example\\@lh3.googleusercontent.com/a.png",  # browsers read \ as /
        "https://lh3.googleusercontent.com:8443/a.png",  # another port
        "https://lh3.googleusercontent.com/a b.png",  # whitespace
        "https://lh3.googleusercontent.com/a/" + "x" * AVATAR_URL_MAX_LENGTH,  # too long
        "",
    ],
)
def test_any_other_avatar_url_is_refused(url: str):
    """A third-party image URL tracks every visitor of the profile; javascript: and 20k strings were stored."""
    # Act / Assert
    with pytest.raises(InvalidAvatarUrlError):
        UserUpdate(profile_picture_url=url)


def test_the_avatar_bound_is_inclusive():
    """Exactly AVATAR_URL_MAX_LENGTH characters still fits."""
    # Prepare
    prefix = "https://lh3.googleusercontent.com/a/"
    url = prefix + "x" * (AVATAR_URL_MAX_LENGTH - len(prefix))

    # Act
    update = UserUpdate(profile_picture_url=url)

    # Assert
    assert len(update.profile_picture_url or "") == AVATAR_URL_MAX_LENGTH


def test_clearing_the_avatar_is_allowed():
    # Act
    update = UserUpdate(profile_picture_url=None)

    # Assert
    assert update.profile_picture_url is None


# ========== WP-27, SEC F14: a deletion names exactly one confirmation ==========


def test_a_deletion_is_confirmed_by_a_password_or_a_google_token():
    # Act
    by_password = DeleteAccountRequest(password="password123")
    by_google = DeleteAccountRequest(google_access_token="ya29.token")

    # Assert
    assert (by_password.password, by_password.google_access_token) == ("password123", None)
    assert (by_google.password, by_google.google_access_token) == (None, "ya29.token")


@pytest.mark.parametrize("body", [{}, {"password": "password123", "google_access_token": "ya29.token"}])
def test_a_deletion_without_exactly_one_confirmation_is_invalid(body: dict):
    # Act / Assert
    with pytest.raises(pydantic.ValidationError):
        DeleteAccountRequest(**body)
