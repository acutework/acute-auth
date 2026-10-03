"""Where an SOS is, for acute-core: its pincode and a name for responders.

Asked during an SOS - often one raised with the app closed, which sends no
name of its own - so it must answer something useful even when Google
cannot, from the worker's own saved place there.
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

    assert (await service.place_at("u1", *GONDAL)).pincode == "360311"


async def test_when_google_fails_the_saved_place_there_answers():
    service = await service_with(
        _Provider(error=PlaceLookupFailed()), ram_gondaa()
    )

    assert (await service.place_at("u1", *GONDAL)).pincode == "360311"


async def test_when_google_has_no_pincode_the_saved_place_there_answers():
    service = await service_with(_Provider(street(None)), ram_gondaa())

    assert (await service.place_at("u1", *GONDAL)).pincode == "360311"


async def test_without_a_provider_the_saved_place_there_answers():
    service = await service_with(None, ram_gondaa())

    assert (await service.place_at("u1", *GONDAL)).pincode == "360311"


async def test_a_saved_place_further_than_500_m_does_not_count():
    # About 1.1 km north.
    far = ram_gondaa(lat=GONDAL[0] + 0.01)
    service = await service_with(_Provider(error=PlaceLookupFailed()), far)

    assert (await service.place_at("u1", *GONDAL)).pincode is None


async def test_another_workers_saved_place_does_not_count():
    service = await service_with(
        _Provider(error=PlaceLookupFailed()), ram_gondaa(user_id="someone-else")
    )

    assert (await service.place_at("u1", *GONDAL)).pincode is None


async def test_an_address_without_a_six_digit_pincode_gives_none():
    place = ram_gondaa()
    place.address_line = "Kashi Vishavanath Road, Gondal"
    service = await service_with(_Provider(error=PlaceLookupFailed()), place)

    assert (await service.place_at("u1", *GONDAL)).pincode is None


class TestEndpoint:
    def test_answers_only_the_pincode_and_a_name(self):
        client, _ = make_client()

        response = client.get(
            "/internal/places/at",
            params={"user_id": "u1", "lat": GONDAL[0], "lng": GONDAL[1]},
            headers={"X-Internal-Key": KEY},
        )

        assert response.status_code == 200
        # No provider in tests and no saved place: nothing to say.
        assert response.json() == {"pincode": None, "label": None}

    @pytest.mark.parametrize("headers", [{}, {"X-Internal-Key": "wrong"}])
    def test_needs_the_internal_key(self, headers):
        client, _ = make_client()

        response = client.get(
            "/internal/places/at",
            params={"user_id": "u1", "lat": GONDAL[0], "lng": GONDAL[1]},
            headers=headers,
        )

        assert response.status_code == 401

    def test_is_closed_when_no_internal_key_is_configured(self):
        client, _ = make_client(internal_api_key="")

        response = client.get(
            "/internal/places/at",
            params={"user_id": "u1", "lat": GONDAL[0], "lng": GONDAL[1]},
            headers={"X-Internal-Key": ""},
        )

        assert response.status_code == 401


class TestName:
    async def test_at_a_saved_place_it_is_named_after_it(self):
        service = await service_with(_Provider(street("360311")), ram_gondaa())

        place = await service.place_at("u1", *GONDAL)

        assert place.label == (
            "Ram Gondaa, Kashi Vishavanath Road, Gondal, Gujarat 360311, India"
        )

    async def test_away_from_saved_places_it_is_the_street_address(self):
        service = await service_with(_Provider(street("360311")))

        place = await service.place_at("u1", *GONDAL)

        assert place.label == "Vardhman Nagar, Gondal"

    async def test_a_saved_place_300_m_away_names_nothing_but_still_gives_its_pincode(
        self,
    ):
        # About 330 m north: too far to say "at Ram Gondaa", near enough that
        # its pincode is right.
        near = ram_gondaa(lat=GONDAL[0] + 0.003)
        service = await service_with(_Provider(error=PlaceLookupFailed()), near)

        place = await service.place_at("u1", *GONDAL)

        assert place.label is None
        assert place.pincode == "360311"

    async def test_a_long_name_is_cut_to_what_an_sos_accepts(self):
        long = ram_gondaa()
        long.address_line = "x" * 400 + " 360311"
        service = await service_with(_Provider(street("360311")), long)

        place = await service.place_at("u1", *GONDAL)

        assert len(place.label) == 160

