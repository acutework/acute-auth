"""Which photo a profile uses. The image itself is in acute-core's bucket."""

import asyncio
import uuid

import pytest

from app.onboarding.models import OnboardingState, OnboardingStep
from tests.conftest_onboarding import DOCTOR, auth, sign_in
from tests.directory_helpers import seed_person


# A fresh number, not the seeded demo user, whose id is not a real one.
MOBILE = "917000000001"


def new_worker(client) -> str:
    return sign_in(client, MOBILE)


def my_id(client, token) -> str:
    return client.get("/auth/me", headers=auth(token)).json()["id"]


def photo_key(user_id: str) -> str:
    return f"profiles/{user_id}/{uuid.uuid4()}.jpg"


def save(client, token, **fields):
    return client.put("/onboarding/profile", json={**DOCTOR, **fields}, headers=auth(token))


def test_a_worker_can_save_a_photo_they_uploaded_and_read_it_back(client):
    token = new_worker(client)
    key = photo_key(my_id(client, token))

    response = save(client, token, photo_url=key)

    assert response.status_code == 200, response.text
    assert response.json()["photo_url"] == key
    assert client.get("/onboarding", headers=auth(token)).json()["profile"]["photo_url"] == key


def test_a_worker_can_remove_their_photo(client):
    token = new_worker(client)
    save(client, token, photo_url=photo_key(my_id(client, token)))

    response = save(client, token, photo_url=None)

    assert response.status_code == 200
    assert response.json()["photo_url"] is None


@pytest.mark.parametrize(
    "photo_url",
    [
        "https://example.com/me.jpg",
        "profiles/../feeds/x.jpg",
        "feeds/{me}/0f0f0f0f-0000-4000-8000-000000000000.jpg",
    ],
)
def test_a_photo_that_is_not_an_uploaded_profile_photo_is_refused(client, photo_url):
    token = new_worker(client)

    response = save(client, token, photo_url=photo_url.format(me=my_id(client, token)))

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_profile"


def test_a_worker_cannot_use_another_workers_photo_as_their_own(client):
    token = new_worker(client)

    response = save(client, token, photo_url=photo_key(str(uuid.uuid4())))

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_profile"


def test_the_directory_shows_a_workers_photo_in_search_and_on_their_profile(client, profiles):
    token = new_worker(client)
    asyncio.run(
        profiles.save_state(
            OnboardingState(user_id=my_id(client, token), current_step=OnboardingStep.DONE, is_complete=True)
        )
    )
    someone = str(uuid.uuid4())
    key = photo_key(someone)
    asyncio.run(seed_person(profiles, someone, name="Dr Rao", photo_url=key))

    [row] = [i for i in client.get("/directory/search", headers=auth(token)).json()["items"] if i["user_id"] == someone]
    person = client.get(f"/directory/people/{someone}", headers=auth(token)).json()

    assert row["photo_url"] == key
    assert person["photo_url"] == key
