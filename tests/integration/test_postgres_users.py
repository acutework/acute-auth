"""PostgresUserRepository against a real database."""

import asyncio

import pytest

from app.core.errors import UserAlreadyExists

pytestmark = pytest.mark.integration

MOBILE = "919999900001"


async def test_a_created_user_can_be_read_back(users):
    created = await users.create(mobile=MOBILE, name="Asha", email="a@example.com")

    by_mobile = await users.get_by_mobile(MOBILE)
    by_id = await users.get_by_id(created.id)

    assert by_mobile.id == created.id
    assert by_id.name == "Asha"
    assert by_id.email == "a@example.com"


async def test_an_unknown_mobile_returns_none(users):
    assert await users.get_by_mobile("910000000000") is None


async def test_a_malformed_user_id_returns_none_rather_than_raising(users):
    """Tokens are not always well-formed; a bad subject must not 500."""
    assert await users.get_by_id("not-a-uuid") is None


async def test_the_unique_index_stops_a_duplicate_number(users):
    await users.create(mobile=MOBILE, name="Asha")

    with pytest.raises(UserAlreadyExists):
        await users.create(mobile=MOBILE, name="Someone Else")


async def test_two_racing_registrations_produce_one_user(users):
    """The service checks before inserting, but only the index can settle a race."""
    results = await asyncio.gather(
        users.create(mobile=MOBILE, name="First"),
        users.create(mobile=MOBILE, name="Second"),
        return_exceptions=True,
    )

    created = [r for r in results if not isinstance(r, Exception)]
    rejected = [r for r in results if isinstance(r, UserAlreadyExists)]
    assert len(created) == 1
    assert len(rejected) == 1
