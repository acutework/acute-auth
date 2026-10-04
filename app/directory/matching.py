"""Who a search finds - pure, so the in-memory repository and the SQL agree."""

import math

from app.directory.models import GeoPoint, Person, SearchQuery

EARTH_RADIUS_KM = 6371.0088


def distance_km(a: GeoPoint, b: GeoPoint) -> float:
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(math.radians(b.lng - a.lng) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def nearest(person: Person, point: GeoPoint) -> tuple[float, str] | None:
    best: tuple[float, str] | None = None
    for location in person.practice_locations:
        d = distance_km(point, GeoPoint(location.lat, location.lng))
        if best is None or d < best[0]:
            best = (d, location.label)
    return best


def matches(person: Person, query: SearchQuery) -> bool:
    if query.roles is not None and person.role not in query.roles:
        return False
    if query.specialty and query.specialty not in person.specialties:
        return False
    if query.text:
        needle = query.text.casefold()
        if not any(needle in value.casefold() for value in (person.name, *person.specialties, *person.tags)):
            return False
    if query.near is not None:
        found = nearest(person, query.near)
        # The same hair of tolerance as the Feed, so a point on the radius is inside.
        if found is None or found[0] > (query.radius_km or 0) + 1e-6:
            return False
    return True
