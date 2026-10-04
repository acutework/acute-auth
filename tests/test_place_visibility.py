"""Which saved places are public. Some saved places are homes, so private is the default."""

import pytest

from tests.conftest import NEW_MOBILE
from tests.conftest_onboarding import auth, sign_in

WARD = {"label": "Apollo Hospital", "address_line": "Road No. 72", "latitude": 17.43, "longitude": 78.41}


@pytest.fixture
def token(client) -> str:
    return sign_in(client)


def test_a_new_place_is_private_by_default(client, token):
    response = client.post("/places", json=WARD, headers=auth(token))

    assert response.status_code == 201, response.text
    assert response.json()["visibility"] == "private"


def test_a_place_can_be_made_a_practice_location_and_back(client, token):
    place = client.post("/places", json=WARD, headers=auth(token)).json()

    made_public = client.put(
        f"/places/{place['id']}", json={**WARD, "visibility": "practice"}, headers=auth(token)
    )
    listed = client.get("/places", headers=auth(token)).json()

    assert made_public.json()["visibility"] == "practice"
    assert listed[0]["visibility"] == "practice"


def test_an_unknown_visibility_is_refused(client, token):
    response = client.post("/places", json={**WARD, "visibility": "public"}, headers=auth(token))

    assert response.status_code == 422


def test_nobody_can_update_someone_elses_place(client, token):
    place = client.post("/places", json=WARD, headers=auth(token)).json()
    stranger = sign_in(client, NEW_MOBILE)

    response = client.put(
        f"/places/{place['id']}", json={**WARD, "label": "Mine now", "visibility": "practice"},
        headers=auth(stranger),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "place_not_found"
    mine = client.get("/places", headers=auth(token)).json()[0]
    assert (mine["label"], mine["visibility"]) == ("Apollo Hospital", "private")
