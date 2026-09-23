"""Onboarding endpoints.

Everything here is scoped to the signed-in user, taken from the access token -
no endpoint accepts a user id, so one worker can never read or write another's
profile or places.
"""

from fastapi import APIRouter, Query, status

from app.api.onboarding_schemas import (
    CatalogOut,
    CompletionItemOut,
    OnboardingSnapshotOut,
    OnboardingStateOut,
    PlaceDetailsOut,
    PlaceIn,
    PlaceOut,
    PlaceSuggestionOut,
    ProfileCompletionOut,
    ProfileIn,
    ProfileOut,
    WorkplaceIn,
    WorkplaceOut,
)
from app.catalog.data import CatalogKind
from app.deps import CatalogDep, CurrentUserDep, OnboardingServiceDep
from app.onboarding.models import (
    OnboardingState,
    SavedPlace,
    WorkerProfile,
    WorkplaceMembership,
)
from app.onboarding.service import OnboardingSnapshot

router = APIRouter(prefix="/onboarding", tags=["onboarding"])
places_router = APIRouter(prefix="/places", tags=["places"])
catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])


# --------------------------------------------------------------------- mapping

def _state_out(state: OnboardingState) -> OnboardingStateOut:
    return OnboardingStateOut(
        current_step=state.current_step,
        step_number=state.current_step.index,
        is_complete=state.is_complete,
    )


def _profile_out(profile: WorkerProfile | None) -> ProfileOut | None:
    if profile is None:
        return None
    return ProfileOut(
        display_name=profile.display_name,
        role=profile.role,
        photo_url=profile.photo_url,
        email=profile.email,
        degrees=profile.degrees,
        specialties=profile.specialties,
        nursing_qualifications=profile.nursing_qualifications,
        medical_council_reg_no=profile.medical_council_reg_no,
        nursing_council_reg_no=profile.nursing_council_reg_no,
        certification_level=profile.certification_level,
        paramedic_licence_no=profile.paramedic_licence_no,
        role_description=profile.role_description,
    )


def _workplace_out(membership: WorkplaceMembership | None) -> WorkplaceOut | None:
    if membership is None:
        return None
    return WorkplaceOut(
        mode=membership.mode,
        status=membership.status,
        invite_code=membership.invite_code,
        organisation_name=membership.organisation_name,
        department=membership.department,
        employee_id=membership.employee_id,
    )


def _place_out(place: SavedPlace) -> PlaceOut:
    return PlaceOut(
        id=place.id,
        label=place.label,
        address_line=place.address_line,
        latitude=place.latitude,
        longitude=place.longitude,
        is_default=place.is_default,
        provider=place.provider,
        provider_place_id=place.provider_place_id,
    )


def _snapshot_out(snapshot: OnboardingSnapshot) -> OnboardingSnapshotOut:
    completion = snapshot.completion
    return OnboardingSnapshotOut(
        state=_state_out(snapshot.state),
        profile=_profile_out(snapshot.profile),
        workplace=_workplace_out(snapshot.membership),
        places=[_place_out(p) for p in snapshot.places],
        completion=None
        if completion is None
        else ProfileCompletionOut(
            percent=completion.percent,
            items=[
                CompletionItemOut(key=i.key, label=i.label, is_done=i.is_done)
                for i in completion.items
            ],
        ),
    )


# ----------------------------------------------------------------- onboarding

@router.get("", response_model=OnboardingSnapshotOut)
async def get_onboarding(
    user: CurrentUserDep, service: OnboardingServiceDep
) -> OnboardingSnapshotOut:
    """Everything already entered, plus where to resume.

    A reinstall or a second device reads this and picks up where the user left
    off rather than starting again.
    """
    return _snapshot_out(await service.snapshot(user.id))


@router.put("/profile", response_model=ProfileOut)
async def save_profile(
    body: ProfileIn,
    user: CurrentUserDep,
    service: OnboardingServiceDep,
    advance: bool = True,
) -> ProfileOut:
    """Screens 1 and 2, and later edits from the profile menu.

    Rejects with 422 when the role's required fields are missing. Pass
    `?advance=false` when editing an already-onboarded profile, so saving a
    detail does not re-drive the onboarding flow.
    """
    saved = await service.save_profile(
        WorkerProfile(user_id=user.id, **body.model_dump()), advance=advance
    )
    return _profile_out(saved)


@router.put("/workplace", response_model=WorkplaceOut)
async def save_workplace(
    body: WorkplaceIn, user: CurrentUserDep, service: OnboardingServiceDep
) -> WorkplaceOut:
    """Screen 3.

    Joining records a membership with `status: pending` - only the organisation
    can approve it. Individual mode requires at least one saved place.
    """
    saved = await service.save_workplace(
        WorkplaceMembership(user_id=user.id, **body.model_dump())
    )
    return _workplace_out(saved)


@router.post("/permissions-seen", response_model=OnboardingStateOut)
async def permissions_seen(
    user: CurrentUserDep, service: OnboardingServiceDep
) -> OnboardingStateOut:
    """Screen 4. Records that the screen was shown - never which permissions were granted."""
    return _state_out(await service.mark_permissions_seen(user.id))


@router.post("/complete", response_model=OnboardingStateOut)
async def complete(
    user: CurrentUserDep, service: OnboardingServiceDep
) -> OnboardingStateOut:
    """Screen 5. Both "Finish setup" and "Skip practice for now" land here."""
    return _state_out(await service.complete(user.id))


# --------------------------------------------------------------------- places

@places_router.get("", response_model=list[PlaceOut])
async def list_places(
    user: CurrentUserDep, service: OnboardingServiceDep
) -> list[PlaceOut]:
    return [_place_out(p) for p in await service.list_places(user.id)]


@places_router.post("", response_model=PlaceOut, status_code=status.HTTP_201_CREATED)
async def create_place(
    body: PlaceIn, user: CurrentUserDep, service: OnboardingServiceDep
) -> PlaceOut:
    saved = await service.save_place(
        SavedPlace(id="", user_id=user.id, **body.model_dump())
    )
    return _place_out(saved)


@places_router.put("/{place_id}", response_model=PlaceOut)
async def update_place(
    place_id: str,
    body: PlaceIn,
    user: CurrentUserDep,
    service: OnboardingServiceDep,
) -> PlaceOut:
    saved = await service.save_place(
        SavedPlace(id=place_id, user_id=user.id, **body.model_dump())
    )
    return _place_out(saved)


@places_router.delete("/{place_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_place(
    place_id: str, user: CurrentUserDep, service: OnboardingServiceDep
) -> None:
    await service.delete_place(user.id, place_id)


@places_router.get("/search", response_model=list[PlaceSuggestionOut])
async def search_places(
    user: CurrentUserDep,
    service: OnboardingServiceDep,
    q: str = Query(min_length=1, max_length=200),
    session_token: str | None = Query(
        default=None,
        description="Reuse one token across a typing run and its details call "
        "so the provider bills it as a single session.",
    ),
) -> list[PlaceSuggestionOut]:
    """Address autocomplete, proxied so the provider key never reaches the app."""
    suggestions = await service.search_addresses(q, session_token=session_token)
    return [PlaceSuggestionOut(**s.__dict__) for s in suggestions]


@places_router.get("/details/{provider_place_id}", response_model=PlaceDetailsOut)
async def place_details(
    provider_place_id: str,
    user: CurrentUserDep,
    service: OnboardingServiceDep,
    session_token: str | None = Query(default=None),
) -> PlaceDetailsOut:
    """Resolve a suggestion to a full address and coordinates.

    The app stores the coordinates with the place, so an SOS can match the
    nearest saved place without calling the provider again.
    """
    details = await service.address_details(
        provider_place_id, session_token=session_token
    )
    return PlaceDetailsOut(
        provider_place_id=details.provider_place_id,
        address_line=details.address_line,
        latitude=details.latitude,
        longitude=details.longitude,
        provider=service.place_provider_name,
    )


# -------------------------------------------------------------------- catalog

@catalog_router.get("", response_model=dict[str, list[str]])
async def all_catalogs(catalog: CatalogDep) -> dict[str, list[str]]:
    """Every option list in one call, so the app can cache them together."""
    return await catalog.list_all()


@catalog_router.get("/{kind}", response_model=CatalogOut)
async def one_catalog(kind: CatalogKind, catalog: CatalogDep) -> CatalogOut:
    return CatalogOut(items=await catalog.list_items(kind))
