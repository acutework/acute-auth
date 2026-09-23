"""Request and response bodies for onboarding."""

from pydantic import BaseModel, Field

from app.onboarding.models import (
    MembershipStatus,
    OnboardingStep,
    WorkerRole,
    WorkplaceMode,
)


class ProfileIn(BaseModel):
    """Screens 1 and 2. Which fields are required depends on `role`."""

    display_name: str = Field(min_length=1, max_length=120)
    role: WorkerRole
    photo_url: str | None = None
    email: str | None = Field(default=None, max_length=255)

    degrees: list[str] = Field(default_factory=list)
    specialties: list[str] = Field(default_factory=list)
    nursing_qualifications: list[str] = Field(default_factory=list)

    medical_council_reg_no: str | None = None
    nursing_council_reg_no: str | None = None
    certification_level: str | None = None
    paramedic_licence_no: str | None = None
    role_description: str | None = None


class ProfileOut(ProfileIn):
    # Always false. Present so no client ever has to guess whether these
    # self-declared fields were checked by anyone.
    is_verified: bool = False


class WorkplaceIn(BaseModel):
    mode: WorkplaceMode
    invite_code: str | None = None
    organisation_name: str | None = None
    department: str | None = None
    employee_id: str | None = None


class WorkplaceOut(WorkplaceIn):
    status: MembershipStatus


class PlaceIn(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    address_line: str = Field(min_length=1, max_length=400)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    is_default: bool = False
    # Set when the address came from the lookup provider rather than typing.
    provider: str | None = None
    provider_place_id: str | None = None


class PlaceOut(PlaceIn):
    id: str


class PlaceSuggestionOut(BaseModel):
    provider_place_id: str
    title: str
    subtitle: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class PlaceDetailsOut(BaseModel):
    provider_place_id: str
    address_line: str
    latitude: float | None = None
    longitude: float | None = None
    provider: str | None = None


class OnboardingStateOut(BaseModel):
    """What the app reads to decide where to resume."""

    current_step: OnboardingStep
    step_number: int
    total_steps: int = 5
    is_complete: bool


class CompletionItemOut(BaseModel):
    key: str
    label: str
    is_done: bool


class ProfileCompletionOut(BaseModel):
    """Drives the ring on the profile avatar.

    Counts only optional detail the person can fill in themselves, so it can
    always reach 100% - never anything waiting on an organisation's approval.
    """

    percent: int
    items: list[CompletionItemOut] = Field(default_factory=list)


class OnboardingSnapshotOut(BaseModel):
    state: OnboardingStateOut
    profile: ProfileOut | None = None
    workplace: WorkplaceOut | None = None
    places: list[PlaceOut] = Field(default_factory=list)
    completion: ProfileCompletionOut | None = None


class CatalogOut(BaseModel):
    items: list[str]
