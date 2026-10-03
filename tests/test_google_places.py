"""Google Places provider, driven by a stubbed transport.

No network. Pins the Places API (New) contract: the key travels as a header
and never as a query parameter, and a details call asks for exactly the fields
we store.
"""

import logging

import httpx
import pytest

from app.core.errors import PlaceLookupFailed, PlaceProviderUnavailable
from app.places.google import GooglePlacesProvider

AUTOCOMPLETE_RESPONSE = {
    "suggestions": [
        {
            "placePrediction": {
                "placeId": "ChIJ-abc",
                "structuredFormat": {
                    "mainText": {"text": "Example City Hospital"},
                    "secondaryText": {"text": "Andheri East, Mumbai"},
                },
            }
        },
        # Query predictions are searches, not places - they must be dropped.
        {"queryPrediction": {"text": {"text": "hospitals near me"}}},
    ]
}

DETAILS_RESPONSE = {
    "id": "ChIJ-abc",
    "formattedAddress": "Example City Hospital, Andheri East, Mumbai 400069",
    "location": {"latitude": 19.1136, "longitude": 72.8697},
}


def make_provider(handler) -> GooglePlacesProvider:
    return GooglePlacesProvider(
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def responder(payload: dict, status_code: int = 200):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status_code, json=payload)

    return handler, seen


class TestSearch:
    async def test_suggestions_are_mapped(self):
        handler, _ = responder(AUTOCOMPLETE_RESPONSE)
        provider = make_provider(handler)

        suggestions = await provider.search("example city")

        assert len(suggestions) == 1
        assert suggestions[0].provider_place_id == "ChIJ-abc"
        assert suggestions[0].title == "Example City Hospital"
        assert suggestions[0].subtitle == "Andheri East, Mumbai"

    async def test_the_key_goes_in_a_header_never_the_query_string(self):
        handler, seen = responder(AUTOCOMPLETE_RESPONSE)
        provider = make_provider(handler)

        await provider.search("example")

        request = seen[0]
        assert request.headers["X-Goog-Api-Key"] == "test-key"
        assert "key" not in request.url.params
        assert "test-key" not in str(request.url)

    async def test_an_empty_query_costs_no_call(self):
        handler, seen = responder(AUTOCOMPLETE_RESPONSE)
        provider = make_provider(handler)

        assert await provider.search("   ") == []
        assert seen == []

    async def test_a_session_token_is_forwarded(self):
        """It is what makes Google bill a typing run as one session."""
        handler, seen = responder(AUTOCOMPLETE_RESPONSE)
        provider = make_provider(handler)

        await provider.search("example", session_token="tok-1")

        import json

        assert json.loads(seen[0].content)["sessionToken"] == "tok-1"


class TestDetails:
    async def test_details_carry_coordinates(self):
        handler, seen = responder(DETAILS_RESPONSE)
        provider = make_provider(handler)

        details = await provider.details("ChIJ-abc")

        assert details.address_line.startswith("Example City Hospital")
        assert details.latitude == pytest.approx(19.1136)
        assert details.longitude == pytest.approx(72.8697)
        assert "places/ChIJ-abc" in str(seen[0].url)

    async def test_only_the_fields_we_store_are_requested(self):
        """The field mask is what Google bills on; asking for less costs less."""
        handler, seen = responder(DETAILS_RESPONSE)
        provider = make_provider(handler)

        await provider.details("ChIJ-abc")

        assert seen[0].headers["X-Goog-FieldMask"] == "id,formattedAddress,location"

    async def test_a_place_without_coordinates_still_resolves(self):
        handler, _ = responder({"id": "x", "formattedAddress": "Somewhere"})
        provider = make_provider(handler)

        details = await provider.details("x")

        assert details.latitude is None
        assert details.address_line == "Somewhere"


class TestFailures:
    async def test_a_rejected_key_becomes_lookup_failed(self):
        handler, _ = responder({"error": {"status": "PERMISSION_DENIED"}}, 403)
        provider = make_provider(handler)

        with pytest.raises(PlaceLookupFailed):
            await provider.search("example")

    async def test_a_transport_error_becomes_provider_unavailable(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route", request=request)

        provider = make_provider(handler)

        with pytest.raises(PlaceProviderUnavailable):
            await provider.search("example")

    async def test_a_missing_key_fails_at_construction(self):
        with pytest.raises(ValueError, match="GOOGLE_PLACES_API_KEY"):
            GooglePlacesProvider(api_key="")


class TestSearchDisabled:
    def test_search_answers_501_when_no_provider_is_configured(self, client):
        """Users can always type an address; search is an optional convenience."""
        from tests.conftest_onboarding import auth, sign_in

        token = sign_in(client)

        response = client.get("/places/search?q=example", headers=auth(token))

        assert response.status_code == 501
        assert response.json()["code"] == "place_search_disabled"


GEOCODE_RESPONSE = {
    "status": "OK",
    "results": [
        # Plus codes are grid references, not addresses - they must be skipped.
        {
            "types": ["plus_code"],
            "formatted_address": "3V8G+JW Mumbai",
            "address_components": [],
            "geometry": {"location": {"lat": 19.06, "lng": 72.83}},
        },
        {
            "types": ["street_address"],
            "formatted_address": "14, Linking Road, Bandra West, Mumbai, Maharashtra 400050, India",
            "address_components": [
                {"long_name": "14", "types": ["street_number"]},
                {"long_name": "Linking Road", "types": ["route"]},
                {
                    "long_name": "Bandra West",
                    "types": ["sublocality_level_1", "sublocality", "political"],
                },
                {"long_name": "Mumbai", "types": ["locality", "political"]},
                {"long_name": "400050", "types": ["postal_code"]},
            ],
            "geometry": {"location": {"lat": 19.0605, "lng": 72.8347}},
        },
    ],
}


class TestReverse:
    async def test_the_most_specific_name_becomes_the_title(self):
        handler, _ = responder(GEOCODE_RESPONSE)
        provider = make_provider(handler)

        result = await provider.reverse(19.0605, 72.8347)

        assert result is not None
        assert result.title == "Linking Road"
        assert result.subtitle == "Bandra West, Mumbai"
        assert result.address_line.startswith("14, Linking Road")
        assert (result.latitude, result.longitude) == (19.0605, 72.8347)

    async def test_the_lookup_asks_for_the_point_in_the_configured_region(self):
        handler, seen = responder(GEOCODE_RESPONSE)
        provider = make_provider(handler)

        await provider.reverse(19.0605, 72.8347)

        params = seen[0].url.params
        assert params["latlng"] == "19.0605,72.8347"
        assert params["language"] == "en"
        assert params["region"] == "in"

    async def test_a_point_with_no_address_is_none(self):
        handler, _ = responder({"status": "ZERO_RESULTS", "results": []})
        provider = make_provider(handler)

        assert await provider.reverse(0.0, 0.0) is None

    async def test_a_refused_key_is_a_lookup_failure(self):
        handler, _ = responder(
            {"status": "REQUEST_DENIED", "error_message": "API not enabled"}
        )
        provider = make_provider(handler)

        with pytest.raises(PlaceLookupFailed):
            await provider.reverse(19.0605, 72.8347)

    async def test_the_key_never_reaches_the_logs(self, caplog):
        # Geocoding takes the key as a query parameter, and httpx logs URLs.
        caplog.set_level(logging.DEBUG)
        handler, _ = responder(GEOCODE_RESPONSE)
        provider = make_provider(handler)

        await provider.reverse(19.0605, 72.8347)

        assert "test-key" not in caplog.text

    async def test_the_postal_code_comes_from_its_own_component(self):
        handler, _ = responder(GEOCODE_RESPONSE)
        provider = make_provider(handler)

        result = await provider.reverse(19.0605, 72.8347)

        assert result.postal_code == "400050"

    async def test_a_result_without_a_postal_code_has_none(self):
        no_pin = {
            "status": "OK",
            "results": [
                {
                    "types": ["route"],
                    "formatted_address": "Linking Road, Mumbai",
                    "address_components": [
                        {"long_name": "Linking Road", "types": ["route"]}
                    ],
                    "geometry": {"location": {"lat": 19.06, "lng": 72.83}},
                }
            ],
        }
        handler, _ = responder(no_pin)
        provider = make_provider(handler)

        result = await provider.reverse(19.06, 72.83)

        assert result.postal_code is None

    async def test_a_leading_plus_code_is_dropped_from_the_address(self):
        # Google sometimes opens an address with a grid reference, which
        # means nothing to a responder reading it.
        coded = {
            "status": "OK",
            "results": [
                {
                    "types": ["street_address"],
                    "formatted_address": "XQGW+J6V, Vardhman Nagar, Gondal, Gujarat 360311, India",
                    "address_components": [
                        {"long_name": "Vardhman Nagar", "types": ["sublocality_level_1"]},
                        {"long_name": "360311", "types": ["postal_code"]},
                    ],
                    "geometry": {"location": {"lat": 21.9766, "lng": 70.7955}},
                }
            ],
        }
        handler, _ = responder(coded)
        provider = make_provider(handler)

        result = await provider.reverse(21.9766, 70.7955)

        assert result.address_line == "Vardhman Nagar, Gondal, Gujarat 360311, India"

