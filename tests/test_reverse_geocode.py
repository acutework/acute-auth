"""GET /places/reverse, driven by a stub provider - no network."""

import pytest

from app.deps import build_onboarding_repository, get_onboarding_service
from app.main import app
from app.onboarding.service import OnboardingService
from app.places.base import PlaceSearchProvider, ReverseResult
from tests.conftest_onboarding import auth, sign_in

LINKING_ROAD = ReverseResult(
    title="Linking Road",
    subtitle="Bandra West, Mumbai",
    address_line="14, Linking Road, Bandra West, Mumbai",
    latitude=19.0605,
    longitude=72.8347,
)


class _StubProvider(PlaceSearchProvider):
    name = "stub"

    def __init__(self, result: ReverseResult | None):
        self.result = result
        self.asked: list[tuple[float, float]] = []

    async def search(self, query, *, session_token=None):
        return []

    async def details(self, provider_place_id, *, session_token=None):
        raise NotImplementedError

    async def reverse(self, latitude, longitude):
        self.asked.append((latitude, longitude))
        return self.result


@pytest.fixture
def provider(client, settings) -> _StubProvider:
    stub = _StubProvider(LINKING_ROAD)
    service = OnboardingService(
        repository=build_onboarding_repository(settings), place_provider=stub
    )
    app.dependency_overrides[get_onboarding_service] = lambda: service
    return stub


def test_a_point_is_answered_with_what_it_is_called(client, provider):
    token = sign_in(client)

    response = client.get(
        "/places/reverse?lat=19.0605&lng=72.8347", headers=auth(token)
    )

    assert response.status_code == 200
    assert response.json() == {
        "title": "Linking Road",
        "subtitle": "Bandra West, Mumbai",
        "address_line": "14, Linking Road, Bandra West, Mumbai",
        "latitude": 19.0605,
        "longitude": 72.8347,
    }
    assert provider.asked == [(19.0605, 72.8347)]


def test_a_point_nobody_has_named_answers_not_found(client, provider):
    provider.result = None
    token = sign_in(client)

    response = client.get("/places/reverse?lat=0&lng=0", headers=auth(token))

    assert response.status_code == 404
    assert response.json()["code"] == "address_not_found"


@pytest.mark.parametrize(
    "query",
    ["lat=91&lng=72", "lat=19&lng=181", "lat=nan&lng=72", "lat=19&lng=inf", "lat=19"],
)
def test_coordinates_off_the_globe_never_reach_the_provider(client, provider, query):
    token = sign_in(client)

    response = client.get(f"/places/reverse?{query}", headers=auth(token))

    assert response.status_code == 422
    assert provider.asked == []


def test_reverse_lookup_needs_a_signed_in_user(client, provider):
    response = client.get("/places/reverse?lat=19&lng=72")

    assert response.status_code == 401
    assert provider.asked == []


def test_reverse_lookup_answers_501_when_no_provider_is_configured(client):
    token = sign_in(client)

    response = client.get("/places/reverse?lat=19&lng=72", headers=auth(token))

    assert response.status_code == 501
    assert response.json()["code"] == "place_search_disabled"
