"""Postgres-backed onboarding storage."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.onboarding import (
    OnboardingStateRow,
    SavedPlaceRow,
    WorkerProfileRow,
    WorkplaceMembershipRow,
)
from app.onboarding.models import (
    MembershipStatus,
    OnboardingState,
    OnboardingStep,
    SavedPlace,
    WorkerProfile,
    WorkerRole,
    WorkplaceMembership,
    WorkplaceMode,
)
from app.onboarding.repository import OnboardingRepository

_PROFILE_FIELDS = (
    "display_name", "role", "photo_url", "email", "degrees", "specialties",
    "nursing_qualifications", "medical_council_reg_no", "nursing_council_reg_no",
    "certification_level", "paramedic_licence_no", "role_description",
)
_MEMBERSHIP_FIELDS = (
    "mode", "status", "invite_code", "organisation_name", "department", "employee_id",
)


class PostgresOnboardingRepository(OnboardingRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def get_profile(self, user_id: str) -> WorkerProfile | None:
        key = _as_uuid(user_id)
        if key is None:
            return None
        async with self._session_factory() as session:
            return _profile_to_domain(await session.get(WorkerProfileRow, key))

    async def save_profile(self, profile: WorkerProfile) -> WorkerProfile:
        key = _as_uuid(profile.user_id)
        async with self._session_factory() as session:
            row = await session.get(WorkerProfileRow, key)
            if row is None:
                row = WorkerProfileRow(user_id=key)
                session.add(row)
            row.display_name = profile.display_name
            row.role = profile.role.value
            row.photo_url = profile.photo_url
            row.email = profile.email
            row.degrees = list(profile.degrees)
            row.specialties = list(profile.specialties)
            row.nursing_qualifications = list(profile.nursing_qualifications)
            row.medical_council_reg_no = profile.medical_council_reg_no
            row.nursing_council_reg_no = profile.nursing_council_reg_no
            row.certification_level = profile.certification_level
            row.paramedic_licence_no = profile.paramedic_licence_no
            row.role_description = profile.role_description
            await session.commit()
            await session.refresh(row)
            return _profile_to_domain(row)

    async def get_membership(self, user_id: str) -> WorkplaceMembership | None:
        key = _as_uuid(user_id)
        if key is None:
            return None
        async with self._session_factory() as session:
            return _membership_to_domain(await session.get(WorkplaceMembershipRow, key))

    async def save_membership(
        self, membership: WorkplaceMembership
    ) -> WorkplaceMembership:
        key = _as_uuid(membership.user_id)
        async with self._session_factory() as session:
            row = await session.get(WorkplaceMembershipRow, key)
            if row is None:
                row = WorkplaceMembershipRow(user_id=key)
                session.add(row)
            row.mode = membership.mode.value
            row.status = membership.status.value
            row.invite_code = membership.invite_code
            row.organisation_name = membership.organisation_name
            row.department = membership.department
            row.employee_id = membership.employee_id
            await session.commit()
            await session.refresh(row)
            return _membership_to_domain(row)

    async def list_places(self, user_id: str) -> list[SavedPlace]:
        key = _as_uuid(user_id)
        if key is None:
            return []
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(SavedPlaceRow)
                .where(SavedPlaceRow.user_id == key)
                .order_by(SavedPlaceRow.is_default.desc(), SavedPlaceRow.label)
            )
            return [_place_to_domain(row) for row in rows]

    async def get_place(self, user_id: str, place_id: str) -> SavedPlace | None:
        key, place_key = _as_uuid(user_id), _as_uuid(place_id)
        if key is None or place_key is None:
            return None
        async with self._session_factory() as session:
            row = await session.get(SavedPlaceRow, place_key)
            return _place_to_domain(row) if row and row.user_id == key else None

    async def save_place(self, place: SavedPlace) -> SavedPlace:
        user_key = _as_uuid(place.user_id)
        place_key = _as_uuid(place.id) if place.id else None
        async with self._session_factory() as session:
            row = await session.get(SavedPlaceRow, place_key) if place_key else None
            if row is None:
                row = SavedPlaceRow(id=place_key or uuid.uuid4(), user_id=user_key)
                session.add(row)
            row.label = place.label
            row.address_line = place.address_line
            row.latitude = place.latitude
            row.longitude = place.longitude
            row.is_default = place.is_default
            row.provider = place.provider
            row.provider_place_id = place.provider_place_id
            await session.commit()
            await session.refresh(row)
            return _place_to_domain(row)

    async def delete_place(self, user_id: str, place_id: str) -> bool:
        user_key, place_key = _as_uuid(user_id), _as_uuid(place_id)
        if user_key is None or place_key is None:
            return False
        async with self._session_factory() as session:
            result = await session.execute(
                delete(SavedPlaceRow).where(
                    SavedPlaceRow.id == place_key, SavedPlaceRow.user_id == user_key
                )
            )
            await session.commit()
            return result.rowcount > 0

    async def clear_default_place(self, user_id: str, *, except_id: str) -> None:
        user_key, keep = _as_uuid(user_id), _as_uuid(except_id)
        async with self._session_factory() as session:
            await session.execute(
                update(SavedPlaceRow)
                .where(SavedPlaceRow.user_id == user_key, SavedPlaceRow.id != keep)
                .values(is_default=False)
            )
            await session.commit()

    async def get_state(self, user_id: str) -> OnboardingState:
        key = _as_uuid(user_id)
        async with self._session_factory() as session:
            row = await session.get(OnboardingStateRow, key) if key else None
        if row is None:
            return OnboardingState(user_id=user_id, current_step=OnboardingStep.ROLE)
        return OnboardingState(
            user_id=user_id,
            current_step=OnboardingStep(row.current_step),
            is_complete=row.is_complete,
        )

    async def save_state(self, state: OnboardingState) -> OnboardingState:
        key = _as_uuid(state.user_id)
        async with self._session_factory() as session:
            row = await session.get(OnboardingStateRow, key)
            if row is None:
                row = OnboardingStateRow(user_id=key)
                session.add(row)
            row.current_step = state.current_step.value
            row.is_complete = state.is_complete
            if state.is_complete and row.completed_at is None:
                row.completed_at = datetime.now(timezone.utc)
            await session.commit()
            return state


def _as_uuid(value: str | None) -> uuid.UUID | None:
    """Tokens and paths are not always well-formed; a bad id must not 500."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _profile_to_domain(row: WorkerProfileRow | None) -> WorkerProfile | None:
    if row is None:
        return None
    return WorkerProfile(
        user_id=str(row.user_id),
        display_name=row.display_name,
        role=WorkerRole(row.role),
        photo_url=row.photo_url,
        email=row.email,
        degrees=list(row.degrees or []),
        specialties=list(row.specialties or []),
        nursing_qualifications=list(row.nursing_qualifications or []),
        medical_council_reg_no=row.medical_council_reg_no,
        nursing_council_reg_no=row.nursing_council_reg_no,
        certification_level=row.certification_level,
        paramedic_licence_no=row.paramedic_licence_no,
        role_description=row.role_description,
    )


def _membership_to_domain(
    row: WorkplaceMembershipRow | None,
) -> WorkplaceMembership | None:
    if row is None:
        return None
    return WorkplaceMembership(
        user_id=str(row.user_id),
        mode=WorkplaceMode(row.mode),
        status=MembershipStatus(row.status),
        invite_code=row.invite_code,
        organisation_name=row.organisation_name,
        department=row.department,
        employee_id=row.employee_id,
    )


def _place_to_domain(row: SavedPlaceRow) -> SavedPlace:
    return SavedPlace(
        id=str(row.id),
        user_id=str(row.user_id),
        label=row.label,
        address_line=row.address_line,
        latitude=row.latitude,
        longitude=row.longitude,
        is_default=row.is_default,
        provider=row.provider,
        provider_place_id=row.provider_place_id,
    )
