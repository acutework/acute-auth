"""The directory's view of a worker: what any signed-in worker may read.

These classes have no fields for a mobile number, email, licence or registration
number, or a private place, so none of those can reach a response by accident.
"""

from dataclasses import dataclass, field

from app.onboarding.models import (
    MembershipStatus,
    PlaceVisibility,
    SavedPlace,
    WorkerProfile,
    WorkerRole,
    WorkplaceMembership,
    WorkplaceMode,
)

MIN_RADIUS_KM = 1
MAX_RADIUS_KM = 50
MAX_QUERY = 80


@dataclass(frozen=True)
class GeoPoint:
    lat: float
    lng: float


@dataclass(frozen=True)
class PracticeLocation:
    label: str
    address_line: str
    lat: float
    lng: float


@dataclass(frozen=True)
class Person:
    user_id: str
    name: str
    role: WorkerRole
    about: str | None = None
    tags: tuple[str, ...] = ()
    degrees: tuple[str, ...] = ()
    specialties: tuple[str, ...] = ()
    nursing_qualifications: tuple[str, ...] = ()
    certification_level: str | None = None
    role_description: str | None = None
    organisation: str | None = None
    department: str | None = None
    practice_locations: tuple[PracticeLocation, ...] = ()


@dataclass(frozen=True)
class SearchQuery:
    text: str | None = None
    # None means every role.
    roles: frozenset[WorkerRole] | None = field(default_factory=lambda: frozenset({WorkerRole.DOCTOR}))
    specialty: str | None = None
    near: GeoPoint | None = None
    radius_km: int | None = None


def person_from(
    profile: WorkerProfile,
    membership: WorkplaceMembership | None,
    places: list[SavedPlace],
) -> Person:
    # A request to join is only the worker's claim until the organisation approves
    # it; an individual's workplace is their own declaration and needs no one's.
    if membership and not (
        membership.status == MembershipStatus.APPROVED or membership.mode == WorkplaceMode.INDIVIDUAL
    ):
        membership = None
    return Person(
        user_id=profile.user_id,
        name=profile.display_name,
        role=profile.role,
        about=profile.about,
        tags=tuple(profile.tags),
        degrees=tuple(profile.degrees),
        specialties=tuple(profile.specialties),
        nursing_qualifications=tuple(profile.nursing_qualifications),
        certification_level=profile.certification_level,
        role_description=profile.role_description,
        organisation=membership.organisation_name if membership else None,
        department=membership.department if membership else None,
        practice_locations=tuple(
            PracticeLocation(p.label, p.address_line, p.latitude, p.longitude)
            for p in places
            if p.visibility == PlaceVisibility.PRACTICE
            and p.latitude is not None
            and p.longitude is not None
        ),
    )
