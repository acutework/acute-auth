"""The directory in Postgres: one query for the matching ids in order, then one
load of those people. Specialties and tags are JSON arrays, matched element by
element so any script compares as decoded text."""

import math
import uuid

from sqlalchemy import JSON, case, cast, exists, func, literal, literal_column, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.directory.matching import EARTH_RADIUS_KM, bounding_box
from app.directory.models import GeoPoint, Person, SearchQuery, person_from
from app.directory.repository import DirectoryRepository
from app.models.onboarding import (
    OnboardingStateRow,
    SavedPlaceRow,
    WorkerProfileRow,
    WorkplaceMembershipRow,
)
from app.onboarding.postgres import (
    _as_uuid,
    _membership_to_domain,
    _place_to_domain,
    _profile_to_domain,
)


def _like(text: str) -> str:
    escaped = text.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _any_element(column, condition):
    """True when some element of a JSON array column satisfies `condition(value)`."""
    # A JSON null or scalar would make json_array_elements_text raise for the
    # whole query. The guard sits inside a CASE because Postgres does not promise
    # to evaluate an AND left to right; such a row becomes empty and never matches.
    array = case((func.json_typeof(column) == "array", column), else_=cast(literal("[]"), JSON))
    elements = func.json_array_elements_text(array).table_valued("value")
    return exists(select(literal(1)).select_from(elements).where(condition(elements.c.value)))


def _distance(point: GeoPoint):
    place = SavedPlaceRow
    h = func.power(func.sin(func.radians(place.latitude - point.lat) / 2), 2) + math.cos(
        math.radians(point.lat)
    ) * func.cos(func.radians(place.latitude)) * func.power(
        func.sin(func.radians(place.longitude - point.lng) / 2), 2
    )
    return 2 * EARTH_RADIUS_KM * func.asin(func.least(1.0, func.sqrt(h)))


def _by_name(profile):
    # Code-point order, as Python sorts the in-memory directory; the database's
    # locale collation would put names in a different order.
    return func.lower(profile.display_name).collate("C")


class PostgresDirectoryRepository(DirectoryRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def search(self, query: SearchQuery, *, offset: int, limit: int) -> list[Person]:
        profile = WorkerProfileRow
        statement = (
            select(profile.user_id)
            .join(OnboardingStateRow, OnboardingStateRow.user_id == profile.user_id)
            .where(OnboardingStateRow.is_complete.is_(True))
        )
        if query.roles is not None:
            statement = statement.where(profile.role.in_([r.value for r in query.roles]))
        if query.specialty:
            statement = statement.where(
                _any_element(profile.specialties, lambda v: v == query.specialty)
            )
        if query.text:
            like = _like(query.text)
            statement = statement.where(
                or_(
                    func.lower(profile.display_name).like(like, escape="\\"),
                    _any_element(profile.specialties, lambda v: func.lower(v).like(like, escape="\\")),
                    _any_element(profile.tags, lambda v: func.lower(v).like(like, escape="\\")),
                ),
                # Lets the trigram index find candidates; the OR above still
                # decides, so a match spanning two joined values never counts.
                func.directory_search_text(profile.display_name, profile.specialties, profile.tags).like(
                    like, escape="\\"
                ),
            )
        if query.near is not None:
            place = SavedPlaceRow
            radius = (query.radius_km or 0) + 1e-6
            min_lat, max_lat, min_lng, max_lng = bounding_box(query.near, radius)
            in_box = [
                place.user_id == profile.user_id,
                # A literal, not a bound parameter: once Postgres falls back to
                # a generic plan it cannot prove a parameter equals 'practice',
                # and so could no longer use the partial index.
                place.visibility == literal_column("'practice'"),
                place.latitude.is_not(None),
                place.longitude.is_not(None),
                place.latitude.between(min_lat, max_lat),
            ]
            if min_lng is not None:
                in_box.append(place.longitude.between(min_lng, max_lng))
            # Dropping places outside the box cannot change the nearest one in
            # range, since everything outside it is beyond the radius anyway.
            nearest = select(func.min(_distance(query.near))).where(*in_box).scalar_subquery()
            statement = statement.where(exists(select(place.id).where(*in_box)), nearest <= radius).order_by(
                nearest, _by_name(profile), profile.user_id
            )
        else:
            statement = statement.order_by(_by_name(profile), profile.user_id)
        statement = statement.offset(offset).limit(limit)
        async with self._session_factory() as session:
            ids = list(await session.scalars(statement))
            people = await self._load(session, ids)
        return [people[str(i)] for i in ids]

    async def get_person(self, user_id: str) -> Person | None:
        key = _as_uuid(user_id)
        if key is None:
            return None
        async with self._session_factory() as session:
            state = await session.get(OnboardingStateRow, key)
            if state is None or not state.is_complete:
                return None
            return (await self._load(session, [key])).get(str(key))

    async def _load(self, session: AsyncSession, ids: list[uuid.UUID]) -> dict[str, Person]:
        if not ids:
            return {}
        profiles = await session.scalars(select(WorkerProfileRow).where(WorkerProfileRow.user_id.in_(ids)))
        memberships = {
            str(m.user_id): _membership_to_domain(m)
            for m in await session.scalars(
                select(WorkplaceMembershipRow).where(WorkplaceMembershipRow.user_id.in_(ids))
            )
        }
        places: dict[str, list] = {}
        for row in await session.scalars(
            select(SavedPlaceRow).where(
                SavedPlaceRow.user_id.in_(ids), SavedPlaceRow.visibility == "practice"
            )
            # A fixed order, so the profile lists places the same way each time
            # and two equally near places always name the same one.
            .order_by(SavedPlaceRow.created_at, SavedPlaceRow.id)
        ):
            places.setdefault(str(row.user_id), []).append(_place_to_domain(row))
        people = {}
        for row in profiles:
            profile = _profile_to_domain(row)
            people[profile.user_id] = person_from(
                profile, memberships.get(profile.user_id), places.get(profile.user_id, [])
            )
        return people
