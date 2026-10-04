"""Seeding workers into onboarding storage, for directory tests."""

from app.onboarding.models import (
    MembershipStatus,
    OnboardingState,
    OnboardingStep,
    PlaceVisibility,
    SavedPlace,
    WorkerProfile,
    WorkerRole,
    WorkplaceMembership,
    WorkplaceMode,
)

WARD = (17.4300, 78.4100)


async def seed_person(
    onboarding,
    user_id: str,
    *,
    name: str,
    role: WorkerRole = WorkerRole.DOCTOR,
    specialties=(),
    tags=(),
    places=(),
    complete: bool = True,
    organisation: str | None = None,
    about: str | None = None,
    membership_status: MembershipStatus = MembershipStatus.APPROVED,
) -> None:
    await onboarding.save_profile(
        WorkerProfile(
            user_id=user_id,
            display_name=name,
            role=role,
            degrees=["MBBS"] if role == WorkerRole.DOCTOR else [],
            specialties=list(specialties),
            medical_council_reg_no="MCI-1" if role == WorkerRole.DOCTOR else None,
            nursing_council_reg_no="INC-1" if role == WorkerRole.NURSE else None,
            about=about,
            tags=list(tags),
        )
    )
    await onboarding.save_state(
        OnboardingState(
            user_id=user_id,
            current_step=OnboardingStep.DONE if complete else OnboardingStep.WORKPLACE,
            is_complete=complete,
        )
    )
    if organisation:
        await onboarding.save_membership(
            WorkplaceMembership(
                user_id=user_id,
                mode=WorkplaceMode.JOIN_ORGANISATION,
                status=membership_status,
                organisation_name=organisation,
                department="Emergency Department",
            )
        )
    for label, lat, lng, visibility in places:
        await onboarding.save_place(
            SavedPlace(
                id="",
                user_id=user_id,
                label=label,
                address_line=f"{label}, Hyderabad",
                latitude=lat,
                longitude=lng,
                visibility=visibility,
            )
        )
