"""The pincode at a point, for acute-core to match a worker's associations.

Asked during an SOS, so it must answer something useful even when Google
cannot: the pincode in the address of the worker's own saved place there.
"""

import pytest

from app.core.errors import PlaceLookupFailed
from app.onboarding.memory import InMemoryOnboardingRepository
from app.onboarding.models import SavedPlace
from app.onboarding.service import OnboardingService
from app.places.base import PlaceSearchProvider, ReverseResult
from tests.test_internal_routes import KEY, make_client

GONDAL = (21.9766, 70.7955)


class _Provider(PlaceSearchProvider):
    name = "stub"

    def __init__(self, result=None, error: Exception | None = None):
        self.result = result
        self.error = error

    async def search(self, query, *, session_token=None):
        return []

    async def details(self, provider_place_id, *, session_token=None):
        raise NotImplementedError

    async def reverse(self, latitude, longitude):
        if self.error:
            raise self.error
        return self.result


def street(postal_code):
    return ReverseResult(
        title="Vardhman Nagar",
        subtitle="Gondal",
        address_line="Vardhman Nagar, Gondal",
        latitude=GONDAL[0],
        longitude=GONDAL[1],
        postal_code=postal_code,
    )


async def service_with(provider, *places: SavedPlace) -> OnboardingService:
    repo = InMemoryOnboardingRepository()
    for place in places:
        await repo.save_place(place)
    return OnboardingService(repository=repo, place_provider=provider)


def ram_gondaa(user_id="u1", lat=GONDAL[0], lng=GONDAL[1]) -> SavedPlace:
    return SavedPlace(
        id="",
        user_id=user_id,
        label="Ram Gondaa",
        address_line="Kashi Vishavanath Road, Gondal, Gujarat 360311, India",
        latitude=lat,
        longitude=lng,
    )


async def test_google_names_the_pincode():
    service = await service_with(_Provider(street("360311")))

    assert await service.pincode_at("u1", *GONDAL) == "360311"


async def test_when_google_fails_the_saved_place_there_answers():
    service = await service_with(
        _Provider(error=PlaceLookupFailed()), ram_gondaa()
    )

    assert await service.pincode_at("u1", *GONDAL) == "360311"


async def test_when_google_has_no_pincode_the_saved_place_there_answers():
    service = await service_with(_Provider(street(None)), ram_gondaa())

    assert await service.pincode_at("u1", *GONDAL) == "360311"


async def test_without_a_provider_the_saved_place_there_answers():
    service = await service_with(None, ram_gondaa())

    assert await service.pincode_at("u1", *GONDAL) == "360311"


async def test_a_saved_place_further_than_500_m_does_not_count():
    # About 1.1 km north.
    far = ram_gondaa(lat=GONDAL[0] + 0.01)
    service = await service_with(_Provider(error=PlaceLookupFailed()), far)

    assert await service.pincode_at("u1", *GONDAL) is None


async def test_another_workers_saved_place_does_not_count():
    service = await service_with(
        _Provider(error=PlaceLookupFailed()), ram_gondaa(user_id="someone-else")
    )

    assert await service.pincode_at("u1", *GONDAL) is None


async def test_an_address_without_a_six_digit_pincode_gives_none():
    place = ram_gondaa()
    place.address_line = "Kashi Vishavanath Road, Gondal"
    service = await service_with(_Provider(error=PlaceLookupFailed()), place)

    assert await service.pincode_at("u1", *GONDAL) is None


class TestEndpoint:
    def test_answers_only_the_pincode(self):
        client, _ = make_client()

        response = client.get(
            "/internal/places/pincode",
            params={"user_id": "u1", "lat": GONDAL[0], "lng": GONDAL[1]},
            headers={"X-Internal-Key": KEY},
        )

        assert response.status_code == 200
        # No provider in tests and no saved place: nothing to say.
        assert response.json() == {"pincode": None}

    @pytest.mark.parametrize("headers", [{}, {"X-Internal-Key": "wrong"}])
    def test_needs_the_internal_key(self, headers):
        client, _ = make_client()

        response = client.get(
            "/internal/places/pincode",
            params={"user_id": "u1", "lat": GONDAL[0], "lng": GONDAL[1]},
            headers=headers,
        )

        assert response.status_code == 401

    def test_is_closed_when_no_internal_key_is_configured(self):
        client, _ = make_client(internal_api_key="")

        response = client.get(
            "/internal/places/pincode",
            params={"user_id": "u1", "lat": GONDAL[0], "lng": GONDAL[1]},
            headers={"X-Internal-Key": ""},
        )

        assert response.status_code == 401
