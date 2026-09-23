"""Address lookup, behind a contract.

Google Places is wired today, but the cost is per call and the intent is to
move to a free provider later. Nothing outside this package knows which one is
in use: routes and services speak only in [PlaceSuggestion] and [PlaceDetails],
and every pick is stored with its own coordinates, so a change of provider
leaves the saved data intact.

To add one: implement PlaceSearchProvider, register it in registry.py, set
PLACES_PROVIDER.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class PlaceSuggestion:
    """One row in the address autocomplete list."""

    provider_place_id: str
    title: str
    subtitle: str | None = None
    # Some providers return coordinates with the suggestion; Google does not,
    # which is why `details` exists.
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class PlaceDetails:
    provider_place_id: str
    address_line: str
    latitude: float | None
    longitude: float | None


class PlaceSearchProvider(ABC):
    """The provider's name, recorded against saved places."""

    name: str = "unknown"

    @abstractmethod
    async def search(self, query: str, *, session_token: str | None = None) -> list[PlaceSuggestion]:
        """Address suggestions for a partial query."""

    @abstractmethod
    async def details(self, provider_place_id: str, *, session_token: str | None = None) -> PlaceDetails:
        """Resolve a suggestion to a full address and coordinates."""

    async def aclose(self) -> None:
        """Release any held resources. Default: nothing."""
