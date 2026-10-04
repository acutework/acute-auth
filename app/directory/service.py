"""Searching and reading the directory. Knows nothing about HTTP or SQL."""

import base64
import binascii
import math
from dataclasses import dataclass

from app.core.errors import InvalidCursor, InvalidLocation, PersonNotFound
from app.directory.matching import distance_km, nearest
from app.directory.models import (
    MAX_QUERY,
    MAX_RADIUS_KM,
    MIN_RADIUS_KM,
    GeoPoint,
    Person,
    SearchQuery,
)
from app.directory.repository import DirectoryRepository
from app.onboarding.models import WorkerRole


@dataclass(frozen=True)
class Hit:
    person: Person
    distance_km: float | None
    nearest_place: str | None


@dataclass(frozen=True)
class SearchPage:
    items: list[Hit]
    next_cursor: str | None


@dataclass(frozen=True)
class PersonView:
    person: Person
    # One per practice location, in order; None when no point was given.
    distances: tuple[float | None, ...]


def _point(lat: float | None, lng: float | None) -> GeoPoint | None:
    if lat is None and lng is None:
        return None
    if lat is None or lng is None or not (math.isfinite(lat) and math.isfinite(lng)):
        raise InvalidLocation()
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        raise InvalidLocation()
    return GeoPoint(lat, lng)


def _encode(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode()).decode().rstrip("=")


def _decode(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        offset = int(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode())
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidCursor() from exc
    if offset < 0:
        raise InvalidCursor()
    return offset


class DirectoryService:
    def __init__(self, repository: DirectoryRepository) -> None:
        self._repo = repository

    async def search(
        self,
        *,
        text: str | None,
        role: str,
        specialty: str | None,
        lat: float | None,
        lng: float | None,
        radius_km: int | None,
        cursor: str | None,
        limit: int,
    ) -> SearchPage:
        near = _point(lat, lng)
        if (near is None) != (radius_km is None):
            raise InvalidLocation()
        if radius_km is not None and not MIN_RADIUS_KM <= radius_km <= MAX_RADIUS_KM:
            raise InvalidLocation()
        query = SearchQuery(
            text=(text or "").strip()[:MAX_QUERY] or None,
            roles=None if role == "all" else frozenset({WorkerRole(role)}),
            specialty=(specialty or "").strip() or None,
            near=near,
            radius_km=radius_km,
        )
        offset = _decode(cursor)
        people = await self._repo.search(query, offset=offset, limit=limit + 1)
        more, people = len(people) > limit, people[:limit]
        items = []
        for person in people:
            found = nearest(person, near) if near else None
            items.append(Hit(person, found[0] if found else None, found[1] if found else None))
        return SearchPage(items, _encode(offset + limit) if more else None)

    async def person(self, user_id: str, *, lat: float | None, lng: float | None) -> PersonView:
        person = await self._repo.get_person(user_id)
        if person is None:
            raise PersonNotFound()
        point = _point(lat, lng)
        return PersonView(
            person,
            tuple(
                distance_km(point, GeoPoint(p.lat, p.lng)) if point else None
                for p in person.practice_locations
            ),
        )
