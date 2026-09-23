"""Maps a provider name from config to an address provider.

Adding a free provider (Nominatim, Photon, a self-hosted Pelias) is two steps:
write the class, add a line here. Saved places keep their own coordinates, so
switching does not invalidate what users already saved.
"""

from collections.abc import Callable

from app.config import Settings
from app.places.base import PlaceSearchProvider
from app.places.google import GooglePlacesProvider

ProviderFactory = Callable[[Settings], PlaceSearchProvider]


def _build_google(settings: Settings) -> PlaceSearchProvider:
    return GooglePlacesProvider(
        api_key=settings.google_places_api_key,
        region=settings.places_region_code or None,
        language=settings.places_language_code or None,
    )


_PROVIDERS: dict[str, ProviderFactory] = {
    "google": _build_google,
}


def build_place_provider(settings: Settings) -> PlaceSearchProvider | None:
    """None when no provider is configured - address search is then disabled,
    but a user can still type an address by hand."""
    if not settings.places_provider:
        return None
    try:
        factory = _PROVIDERS[settings.places_provider]
    except KeyError:
        known = ", ".join(sorted(_PROVIDERS))
        raise ValueError(
            f"Unknown places provider {settings.places_provider!r}. "
            f"Known providers: {known}"
        ) from None
    return factory(settings)
