import random

import pycountry
import pydantic
import pytest
from faker import Faker

from ipg.api.models.user import UserBase


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
