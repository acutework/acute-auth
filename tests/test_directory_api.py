"""The directory over HTTP."""

import asyncio
import uuid

import pytest

from app.onboarding.models import PlaceVisibility, WorkerRole
from tests.conftest_onboarding import auth, sign_in
from tests.directory_helpers import seed_person

HERE = (17.43, 78.41)


@pytest.fixture
def token(client) -> str:
    return sign_in(client)


@pytest.fixture
def seed(profiles):
    def make(name: str, **kwargs) -> str:
        user_id = str(uuid.uuid4())
        asyncio.run(seed_person(profiles, user_id, name=name, **kwargs))
        return user_id

    return make


def search(client, token, query: str = "") -> dict:
    response = client.get(f"/directory/search{query}", headers=auth(token))
    assert response.status_code == 200, response.text
    return response.json()


def test_search_needs_a_token(client):
    assert client.get("/directory/search").status_code == 401


def test_doctors_are_listed_by_default_with_what_a_row_needs(client, token, seed):
    seed("Dr Rao", specialties=["Emergency Medicine"], organisation="Apollo Hospital")
    seed("Priya Nair", role=WorkerRole.NURSE, specialties=["Critical care"])

    [item] = search(client, token)["items"]

    assert item["name"] == "Dr Rao"
    assert item["specialties"] == ["Emergency Medicine"]
    assert item["organisation"] == "Apollo Hospital"
    assert item["is_you"] is False and item["distance_km"] is None


def test_a_located_search_reports_whole_kilometres_to_the_nearest_practice_location(client, token, seed):
    seed("Dr Near", places=[("Apollo", HERE[0] + 0.03, HERE[1], PlaceVisibility.PRACTICE)])

    [item] = search(client, token, f"?lat={HERE[0]}&lng={HERE[1]}&radius_km=10")["items"]

    assert item["nearest_place"] == "Apollo"
    assert item["distance_km"] == 3.0


@pytest.mark.parametrize(
    "query",
    ["?lat=17.4&lng=78.4", "?lat=17.4&radius_km=5", "?lat=17.4&lng=78.4&radius_km=0", "?lat=17.4&lng=78.4&radius_km=51", "?lat=91&lng=78.4&radius_km=5"],
)
def test_an_incomplete_or_impossible_location_is_refused(client, token, query):
    response = client.get(f"/directory/search{query}", headers=auth(token))

    assert response.status_code == 422 and response.json()["code"] == "invalid_location"


def test_an_unknown_role_and_a_mangled_cursor_are_refused(client, token):
    assert client.get("/directory/search?role=surgeon", headers=auth(token)).status_code == 422
    response = client.get("/directory/search?cursor=zzz", headers=auth(token))
    assert response.json()["code"] == "invalid_cursor"


def test_pages_end_with_no_cursor(client, token, seed):
    for name in ("Dr A", "Dr B", "Dr C"):
        seed(name)

    first = search(client, token, "?limit=2")
    rest = search(client, token, f"?limit=2&cursor={first['next_cursor']}")

    assert [i["name"] for i in first["items"] + rest["items"]] == ["Dr A", "Dr B", "Dr C"]
    assert rest["next_cursor"] is None


def test_a_profile_shows_public_details_only(client, token, seed):
    user = seed(
        "Dr Rao",
        about="Emergency physician.",
        tags=["trauma"],
        organisation="Apollo Hospital",
        places=[("Apollo", *HERE, PlaceVisibility.PRACTICE), ("Home", 17.5, 78.5, PlaceVisibility.PRIVATE)],
    )

    body = client.get(f"/directory/people/{user}?lat={HERE[0]}&lng={HERE[1]}", headers=auth(token)).json()

    assert body["about"] == "Emergency physician." and body["tags"] == ["trauma"]
    assert [p["label"] for p in body["practice_locations"]] == ["Apollo"]
    assert body["practice_locations"][0]["distance_km"] == 0.0
    assert body["is_verified"] is False
    forbidden = {"mobile", "email", "medical_council_reg_no", "nursing_council_reg_no", "paramedic_licence_no"}
    assert forbidden.isdisjoint(body)


def test_an_unknown_or_unfinished_person_is_not_found(client, token, seed):
    unfinished = seed("Dr Halfway", complete=False)

    for user_id in (unfinished, str(uuid.uuid4()), "not-a-uuid"):
        response = client.get(f"/directory/people/{user_id}", headers=auth(token))
        assert response.status_code == 404 and response.json()["code"] == "person_not_found"
