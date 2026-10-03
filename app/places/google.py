"""Google Places provider.

Proxied rather than called from the app, so the API key stays in acute-auth's
environment and is never shipped in an app binary.

Uses the Places API (New): POST :autocomplete and GET /v1/places/{id}. A
`session_token` groups an autocomplete run with the details call that follows,
which is how Google bills a lookup as one session instead of many.
"""

import logging

import httpx

from app.core.errors import PlaceLookupFailed, PlaceProviderUnavailable
from app.places.base import (
    PlaceDetails,
    PlaceSearchProvider,
    PlaceSuggestion,
    ReverseResult,
)

logger = logging.getLogger(__name__)

AUTOCOMPLETE_URL = "https://places.googleapis.com/v1/places:autocomplete"
DETAILS_URL = "https://places.googleapis.com/v1/places"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

# The Geocoding API takes its key as a query parameter, and httpx logs every
# request URL at INFO. Left alone, the key would be written to the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Most specific first: a building's name beats its street, and a street beats
# the neighbourhood around it.
_TITLE_TYPES = (
    "premise",
    "point_of_interest",
    "establishment",
    "route",
    "neighborhood",
    "sublocality_level_2",
    "sublocality_level_1",
    "locality",
)
_SUBTITLE_TYPES = ("sublocality_level_1", "locality")


class GooglePlacesProvider(PlaceSearchProvider):
    name = "google"

    def __init__(
        self,
        *,
        api_key: str,
        region: str | None = "in",
        language: str | None = "en",
        client: httpx.AsyncClient | None = None,
    ):
        if not api_key:
            raise ValueError(
                "Google Places needs GOOGLE_PLACES_API_KEY to be set."
            )
        self._api_key = api_key
        self._region = region
        self._language = language
        self._client = client or httpx.AsyncClient(timeout=10.0)

    async def search(
        self, query: str, *, session_token: str | None = None
    ) -> list[PlaceSuggestion]:
        if not query.strip():
            return []

        body: dict = {"input": query}
        if self._region:
            body["regionCode"] = self._region
        if self._language:
            body["languageCode"] = self._language
        if session_token:
            body["sessionToken"] = session_token

        data = await self._request("POST", AUTOCOMPLETE_URL, json=body)

        suggestions = []
        for item in data.get("suggestions", []):
            prediction = item.get("placePrediction")
            if not prediction:
                continue  # queryPredictions are searches, not places
            suggestions.append(
                PlaceSuggestion(
                    provider_place_id=prediction["placeId"],
                    title=prediction.get("structuredFormat", {})
                    .get("mainText", {})
                    .get("text", ""),
                    subtitle=prediction.get("structuredFormat", {})
                    .get("secondaryText", {})
                    .get("text"),
                )
            )
        return suggestions

    async def details(
        self, provider_place_id: str, *, session_token: str | None = None
    ) -> PlaceDetails:
        params = {"sessionToken": session_token} if session_token else None
        data = await self._request(
            "GET",
            f"{DETAILS_URL}/{provider_place_id}",
            params=params,
            field_mask="id,formattedAddress,location",
        )

        location = data.get("location") or {}
        return PlaceDetails(
            provider_place_id=data.get("id", provider_place_id),
            address_line=data.get("formattedAddress", ""),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
        )

    async def reverse(
        self, latitude: float, longitude: float
    ) -> ReverseResult | None:
        params = {"latlng": f"{latitude},{longitude}", "key": self._api_key}
        if self._language:
            params["language"] = self._language
        if self._region:
            params["region"] = self._region

        data = await self._send("GET", GEOCODE_URL, params=params)

        status = data.get("status")
        if status == "ZERO_RESULTS":
            return None
        if status != "OK":
            # Geocoding answers 200 with the refusal in the body.
            logger.warning(
                "Google Geocoding refused a lookup: %s %s",
                status,
                str(data.get("error_message", ""))[:300],
            )
            raise PlaceLookupFailed("Address lookup is unavailable.")

        results = [
            r for r in data.get("results", []) if "plus_code" not in r.get("types", [])
        ]
        if not results:
            return None
        best = results[0]
        components = best.get("address_components", [])

        def named(kind: str) -> str | None:
            return next(
                (c["long_name"] for c in components if kind in c.get("types", [])),
                None,
            )

        address_line = best.get("formatted_address", "")
        title = next((n for n in map(named, _TITLE_TYPES) if n), None)
        if title is None:
            title, _, rest = address_line.partition(", ")
            subtitle = rest or None
        else:
            parts = [n for n in map(named, _SUBTITLE_TYPES) if n and n != title]
            subtitle = ", ".join(dict.fromkeys(parts)) or None
        if not title:
            return None

        location = best.get("geometry", {}).get("location", {})
        return ReverseResult(
            title=title,
            subtitle=subtitle,
            address_line=address_line,
            latitude=location.get("lat", latitude),
            longitude=location.get("lng", longitude),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        field_mask: str = "suggestions.placePrediction",
    ) -> dict:
        headers = {
            "X-Goog-Api-Key": self._api_key,
            "X-Goog-FieldMask": field_mask,
        }
        return await self._send(
            method, url, json=json, params=params, headers=headers
        )

    async def _send(self, method: str, url: str, **kwargs) -> dict:
        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            # A 4xx here is nearly always a key, billing or quota problem -
            # ours to fix, not the caller's, so it is logged loudly.
            logger.warning(
                "Google Places rejected a request: %s %s",
                exc.response.status_code,
                exc.response.text[:300],
            )
            raise PlaceLookupFailed("Address lookup is unavailable.") from exc
        except httpx.HTTPError as exc:
            logger.warning("Google Places is unreachable: %r", exc)
            raise PlaceProviderUnavailable() from exc
        except ValueError as exc:
            raise PlaceProviderUnavailable("Unreadable response.") from exc
