import pytest

from majlisna.api.controllers.shared import (
    create_random_public_id,
    create_random_string,
    get_password_hash,
    verify_password,
)


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


# The tests hash at bcrypt's cheapest cost (tests/conftest.py, cheap_bcrypt); this one
# checks what production stores, so it keeps gensalt()'s default.
@pytest.mark.real_bcrypt
@pytest.mark.asyncio
async def test_get_password_hash():
    password = get_password_hash("password")
    assert len(password) == 60
    assert password.startswith("$2b$12$")
    assert password != get_password_hash("password")


@pytest.mark.real_bcrypt
@pytest.mark.asyncio
async def test_verify_password():
    password = "password"
    password_hash = get_password_hash(password)

    assert verify_password(password, password_hash) is True
    assert verify_password("wrong_password", password_hash) is False


@pytest.mark.asyncio
async def test_verify_password_accepts_a_hash_of_another_cost():
    """A hash carries its own cost: one made at the tests' cost 4 verifies like a cost-12 one."""
    # Prepare
    password_hash = get_password_hash("password")

    # Act / Assert
    assert password_hash.startswith("$2b$04$")
    assert verify_password("password", password_hash) is True
    assert verify_password("wrong_password", password_hash) is False
