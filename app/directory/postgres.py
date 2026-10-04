"""The directory in Postgres: one query for the matching ids in order, then one
load of those people. Specialties and tags are JSON arrays, matched element by
element so any script compares as decoded text."""

import math
import uuid

from sqlalchemy import exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.directory.matching import EARTH_RADIUS_KM
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
    elements = func.json_array_elements_text(column).table_valued("value")
    return exists(select(literal(1)).select_from(elements).where(condition(elements.c.value)))


def _distance(point: GeoPoint):
    place = SavedPlaceRow
    h = func.power(func.sin(func.radians(place.latitude - point.lat) / 2), 2) + math.cos(
        math.radians(point.lat)
    ) * func.cos(func.radians(place.latitude)) * func.power(
        func.sin(func.radians(place.longitude - point.lng) / 2), 2
    )
    return 2 * EARTH_RADIUS_KM * func.asin(func.least(1.0, func.sqrt(h)))


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
                )
            )
        if query.near is not None:
            place = SavedPlaceRow
            nearest = (
                select(func.min(_distance(query.near)))
                .where(
                    place.user_id == profile.user_id,
                    place.visibility == "practice",
                    place.latitude.is_not(None),
                    place.longitude.is_not(None),
                )
                .scalar_subquery()
            )
            statement = statement.where(nearest <= (query.radius_km or 0) + 1e-6).order_by(
                nearest, func.lower(profile.display_name), profile.user_id
            )
        else:
            statement = statement.order_by(func.lower(profile.display_name), profile.user_id)
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
        ):
            places.setdefault(str(row.user_id), []).append(_place_to_domain(row))
        people = {}
        for row in profiles:
            profile = _profile_to_domain(row)
            people[profile.user_id] = person_from(
                profile, memberships.get(profile.user_id), places.get(profile.user_id, [])
            )
        return people
