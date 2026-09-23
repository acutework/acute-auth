"""Google Places provider, driven by a stubbed transport.

No network. Pins the Places API (New) contract: the key travels as a header
and never as a query parameter, and a details call asks for exactly the fields
we store.
"""

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
