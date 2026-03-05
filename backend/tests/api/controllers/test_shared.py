import pytest

from ipg.api.controllers.shared import create_random_public_id, create_random_string, get_password_hash, verify_password


@pytest.mark.asyncio
async def test_create_random_string():
    random_string = create_random_string()
    assert len(random_string) == 16
    assert all(
        char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
        for char in random_string
    )


@pytest.mark.asyncio
async def test_create_random_public_id():
    public_id = create_random_public_id()
    assert len(public_id) == 5
    assert all(char in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" for char in public_id)


@pytest.mark.asyncio
async def test_get_password_hash():
    password = get_password_hash("password")
    assert len(password) == 60
    assert password.startswith("$2b$12$")
    assert password != get_password_hash("password")


@pytest.mark.asyncio
async def test_verify_password():
    password = "password"
    password_hash = get_password_hash(password)

    assert verify_password(password, password_hash) is True
    assert verify_password("wrong_password", password_hash) is False
