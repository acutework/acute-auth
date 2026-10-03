"""Onboarding rules.

Holds what each role must declare, what a workplace choice requires, and how
far through the flow a user is. Knows nothing about HTTP or storage.

Every credential here is self-declared. Nothing is verified, and no document is
ever requested - the rules below check only that required fields are present.
"""

import logging
import math
import re
import uuid
from dataclasses import dataclass, field

from app.core.errors import (
    AddressNotFound,
    OnboardingIncomplete,
    PlaceNotFound,
    ProfileRequired,
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
from app.onboarding.completion import ProfileCompletion, compute_completion
from app.onboarding.repository import OnboardingRepository
from app.places.base import (
    PlaceDetails,
    PlaceSearchProvider,
    PlaceSuggestion,
    ReverseResult,
)


logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class PlaceAt:
    """Where an SOS is, as acute-core needs it. Either part may be unknown."""

    pincode: str | None
    label: str | None


@dataclass
class OnboardingSnapshot:
    """Everything the app needs to decide where to resume."""

    state: OnboardingState
    profile: WorkerProfile | None = None
    membership: WorkplaceMembership | None = None
    places: list[SavedPlace] = field(default_factory=list)
    completion: ProfileCompletion | None = None


class OnboardingService:
    def __init__(
        self,
        *,
        repository: OnboardingRepository,
        place_provider: PlaceSearchProvider | None = None,
    ):
        self._repo = repository
        self._places = place_provider

    # ---------------------------------------------------------------- progress

    async def snapshot(self, user_id: str) -> OnboardingSnapshot:
        profile = await self._repo.get_profile(user_id)
        membership = await self._repo.get_membership(user_id)
        places = await self._repo.list_places(user_id)
        return OnboardingSnapshot(
            state=await self._repo.get_state(user_id),
            profile=profile,
            membership=membership,
            places=places,
            completion=compute_completion(profile, membership, places),
        )

    async def save_profile(
        self, profile: WorkerProfile, *, advance: bool = True
    ) -> WorkerProfile:
        """Screens 1 and 2, and later edits from the profile menu.

        `advance=False` is used when editing an already-onboarded profile, so
        saving a detail does not rewind or re-drive the onboarding flow.
        """
        _validate_profile(profile)
        saved = await self._repo.save_profile(profile)
        if advance:
            await self._advance(profile.user_id, OnboardingStep.WORKPLACE)
        return saved

    async def save_workplace(
        self, membership: WorkplaceMembership
    ) -> WorkplaceMembership:
        """Screen 3. Joining creates a pending membership; the organisation approves it."""
        if await self._repo.get_profile(membership.user_id) is None:
            raise ProfileRequired()

        if membership.mode is WorkplaceMode.JOIN_ORGANISATION:
            missing = [
                name
                for name, value in (
                    ("invite_code", membership.invite_code),
                    ("department", membership.department),
                )
                if not (value or "").strip()
            ]
            if missing:
                raise OnboardingIncomplete(
                    f"Joining a workplace needs: {', '.join(missing)}."
                )
            # Never approved by us - only the organisation can do that.
            membership.status = MembershipStatus.PENDING
        else:
            # An individual has no organisation to alert, so a saved place is
            # the only way an SOS can say where they are.
            if not await self._repo.list_places(membership.user_id):
                raise OnboardingIncomplete(
                    "Save at least one place before continuing as an individual."
                )
            membership.invite_code = None
            membership.department = None
            membership.employee_id = None
            membership.status = MembershipStatus.APPROVED

        saved = await self._repo.save_membership(membership)
        await self._advance(membership.user_id, OnboardingStep.PERMISSIONS)
        return saved

    async def mark_permissions_seen(self, user_id: str) -> OnboardingState:
        """Screen 4. Deliberately not gated on any permission being granted."""
        return await self._advance(user_id, OnboardingStep.FIRST_SETUP)

    async def complete(self, user_id: str) -> OnboardingState:
        """Screen 5. Refuses only if the earlier required steps are unfinished."""
        if await self._repo.get_profile(user_id) is None:
            raise ProfileRequired()
        if await self._repo.get_membership(user_id) is None:
            raise OnboardingIncomplete("Choose a workplace option first.")

        return await self._repo.save_state(
            OnboardingState(
                user_id=user_id, current_step=OnboardingStep.DONE, is_complete=True
            )
        )

    # ------------------------------------------------------------------ places

    async def list_places(self, user_id: str) -> list[SavedPlace]:
        return await self._repo.list_places(user_id)

    async def save_place(self, place: SavedPlace) -> SavedPlace:
        if not (place.label or "").strip():
            raise OnboardingIncomplete("A place needs a label.")
        if not (place.address_line or "").strip():
            raise OnboardingIncomplete("A place needs an address.")

        if not place.id:
            place.id = str(uuid.uuid4())
        # The first place a user saves is their default; there is nothing else
        # for an SOS to fall back to.
        if not place.is_default and not await self._repo.list_places(place.user_id):
            place.is_default = True

        saved = await self._repo.save_place(place)
        if saved.is_default:
            await self._repo.clear_default_place(place.user_id, except_id=saved.id)
        return saved

    async def delete_place(self, user_id: str, place_id: str) -> None:
        if not await self._repo.delete_place(user_id, place_id):
            raise PlaceNotFound()
        # Losing the default leaves an SOS with nothing to suggest, so promote
        # whatever remains.
        remaining = await self._repo.list_places(user_id)
        if remaining and not any(p.is_default for p in remaining):
            remaining[0].is_default = True
            await self._repo.save_place(remaining[0])

    # ---------------------------------------------------------- address lookup

    async def search_addresses(
        self, query: str, *, session_token: str | None = None
    ) -> list[PlaceSuggestion]:
        if self._places is None:
            from app.core.errors import PlaceSearchDisabled

            raise PlaceSearchDisabled()
        return await self._places.search(query, session_token=session_token)

    async def address_details(
        self, provider_place_id: str, *, session_token: str | None = None
    ) -> PlaceDetails:
        if self._places is None:
            from app.core.errors import PlaceSearchDisabled

            raise PlaceSearchDisabled()
        return await self._places.details(
            provider_place_id, session_token=session_token
        )

    async def reverse_geocode(self, latitude: float, longitude: float) -> ReverseResult:
        if self._places is None:
            from app.core.errors import PlaceSearchDisabled

            raise PlaceSearchDisabled()
        result = await self._places.reverse(latitude, longitude)
        if result is None:
            raise AddressNotFound()
        return result

    async def place_at(
        self, user_id: str, latitude: float, longitude: float
    ) -> PlaceAt:
        """Where an SOS is: its pincode, for the sender's associations, and a
        name for responders, for an SOS that came without one.

        Google first. When it cannot answer - down, refused, or no postal code
        - the pincode in the address of the worker's own saved place within
        500 m. The name is that saved place when within 150 m, as the app's
        header would say, else Google's address. Nothing is never an error.
        """
        found: ReverseResult | None = None
        if self._places is not None:
            try:
                found = await self._places.reverse(latitude, longitude)
            except Exception as exc:  # noqa: BLE001 - any failure falls back
                logger.warning("Place lookup fell back to saved places: %r", exc)

        nearest, nearest_m = None, math.inf
        for place in await self._repo.list_places(user_id):
            if place.latitude is None or place.longitude is None:
                continue
            metres = _distance_m(latitude, longitude, place.latitude, place.longitude)
            if metres < nearest_m:
                nearest, nearest_m = place, metres

        pincode = found.postal_code if found and found.postal_code else None
        if pincode is None and nearest is not None and nearest_m <= _PINCODE_RADIUS_M:
            # The last one: Indian addresses end "..., State 360311, India".
            pincodes = _PINCODE.findall(nearest.address_line or "")
            pincode = pincodes[-1] if pincodes else None

        if nearest is not None and nearest_m <= _NAME_RADIUS_M:
            label = f"{nearest.label}, {nearest.address_line}"
        else:
            label = found.address_line if found and found.address_line else None
        return PlaceAt(pincode=pincode, label=_trim(label) if label else None)

    @property
    def place_provider_name(self) -> str | None:
        return self._places.name if self._places else None

    async def aclose(self) -> None:
        if self._places:
            await self._places.aclose()

    # ----------------------------------------------------------------- private

    async def _advance(self, user_id: str, step: OnboardingStep) -> OnboardingState:
        """Move forward, never backward - going back a screen must not lose progress."""
        state = await self._repo.get_state(user_id)
        if state.is_complete:
            return state
        order = list(OnboardingStep)
        if order.index(step) > order.index(state.current_step):
            state.current_step = step
            return await self._repo.save_state(state)
        return state


def _validate_profile(profile: WorkerProfile) -> None:
    if not (profile.display_name or "").strip():
        raise OnboardingIncomplete("A display name is required.")

    missing: list[str] = []
    match profile.role:
        case WorkerRole.DOCTOR:
            if not profile.degrees:
                missing.append("at least one degree")
            if not profile.specialties:
                missing.append("at least one specialty")
            if not (profile.medical_council_reg_no or "").strip():
                missing.append("a medical council registration number")
        case WorkerRole.NURSE:
            if not profile.nursing_qualifications:
                missing.append("at least one qualification")
            if not profile.specialties:
                missing.append("at least one specialty")
            if not (profile.nursing_council_reg_no or "").strip():
                missing.append("a nursing council registration number")
        case WorkerRole.PARAMEDIC:
            if not (profile.certification_level or "").strip():
                missing.append("a certification level")
        case WorkerRole.OTHER:
            if not (profile.role_description or "").strip():
                missing.append("a description of your role")
        case _:
            pass  # front desk and security need only a display name

    if missing:
        raise OnboardingIncomplete(f"Still needed: {', '.join(missing)}.")


# Near enough a saved place for its pincode to be right.
_PINCODE_RADIUS_M = 500.0
# Near enough to say the worker is at it - the app's header uses the same.
_NAME_RADIUS_M = 150.0
# acute-core's limit on an SOS place label, in code points.
_MAX_LABEL = 160
_PINCODE = re.compile(r"(?<!\d)\d{6}(?!\d)")


def _distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Flat-earth metres: plenty to tell whether someone is at a building."""
    rad = math.pi / 180
    scale = math.cos((lat1 + lat2) / 2 * rad)
    d_lat = (lat2 - lat1) * rad
    d_lng = (lng2 - lng1) * rad * scale
    return math.hypot(d_lat, d_lng) * 6_371_000


def _trim(label: str) -> str:
    return label[:_MAX_LABEL]

