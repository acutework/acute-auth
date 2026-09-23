"""Onboarding domain types.

Everything a worker declares about themselves is **self-declared**: it is
stored as entered, never marked verified, and no certificate, Aadhaar or
medical document is ever requested.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class WorkerRole(StrEnum):
    DOCTOR = "doctor"
    NURSE = "nurse"
    PARAMEDIC = "paramedic"
    FRONT_DESK = "front_desk"
    SECURITY = "security"
    OTHER = "other"


class WorkplaceMode(StrEnum):
    JOIN_ORGANISATION = "join_organisation"
    INDIVIDUAL = "individual"


class MembershipStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class OnboardingStep(StrEnum):
    """The step a returning user resumes at."""

    ROLE = "role"
    PROFILE = "profile"
    WORKPLACE = "workplace"
    PERMISSIONS = "permissions"
    FIRST_SETUP = "first_setup"
    DONE = "done"

    @property
    def index(self) -> int:
        """1-based position, for the "Step n of 5" indicator."""
        order = list(OnboardingStep)
        return min(order.index(self) + 1, 5)


@dataclass
class WorkerProfile:
    user_id: str
    display_name: str
    role: WorkerRole
    photo_url: str | None = None
    email: str | None = None

    # Doctor
    degrees: list[str] = field(default_factory=list)
    medical_council_reg_no: str | None = None

    # Doctor and nurse
    specialties: list[str] = field(default_factory=list)

    # Nurse
    nursing_qualifications: list[str] = field(default_factory=list)
    nursing_council_reg_no: str | None = None

    # Paramedic
    certification_level: str | None = None
    paramedic_licence_no: str | None = None

    # Other staff
    role_description: str | None = None


@dataclass
class WorkplaceMembership:
    user_id: str
    mode: WorkplaceMode
    status: MembershipStatus = MembershipStatus.PENDING
    invite_code: str | None = None
    organisation_name: str | None = None
    department: str | None = None
    employee_id: str | None = None


@dataclass
class SavedPlace:
    """A place the worker works from.

    Coordinates are stored whenever we have them, so the app can pick the
    nearest saved place during an SOS without another provider call - and so
    the data survives a change of mapping provider. `provider` and
    `provider_place_id` record where a pick came from, nothing more.
    """

    id: str
    user_id: str
    label: str
    address_line: str
    latitude: float | None = None
    longitude: float | None = None
    is_default: bool = False
    provider: str | None = None
    provider_place_id: str | None = None


@dataclass
class OnboardingState:
    user_id: str
    current_step: OnboardingStep = OnboardingStep.ROLE
    is_complete: bool = False
