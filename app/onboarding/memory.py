"""In-memory onboarding storage, for tests and infra-free local runs."""

import uuid
from dataclasses import replace

from app.onboarding.models import (
    OnboardingState,
    OnboardingStep,
    SavedPlace,
    WorkerProfile,
    WorkplaceMembership,
)
from app.onboarding.repository import OnboardingRepository


class InMemoryOnboardingRepository(OnboardingRepository):
    def __init__(self) -> None:
        self._profiles: dict[str, WorkerProfile] = {}
        self._memberships: dict[str, WorkplaceMembership] = {}
        self._places: dict[str, SavedPlace] = {}
        self._states: dict[str, OnboardingState] = {}

    async def get_profile(self, user_id: str) -> WorkerProfile | None:
        return self._profiles.get(user_id)

    async def save_profile(self, profile: WorkerProfile) -> WorkerProfile:
        self._profiles[profile.user_id] = profile
        return profile

    async def get_membership(self, user_id: str) -> WorkplaceMembership | None:
        return self._memberships.get(user_id)

    async def save_membership(
        self, membership: WorkplaceMembership
    ) -> WorkplaceMembership:
        self._memberships[membership.user_id] = membership
        return membership

    async def list_places(self, user_id: str) -> list[SavedPlace]:
        places = [p for p in self._places.values() if p.user_id == user_id]
        # Default first, then alphabetical - the order the app shows them in.
        return sorted(places, key=lambda p: (not p.is_default, p.label.lower()))

    async def get_place(self, user_id: str, place_id: str) -> SavedPlace | None:
        place = self._places.get(place_id)
        return place if place and place.user_id == user_id else None

    async def save_place(self, place: SavedPlace) -> SavedPlace:
        if not place.id:
            place = replace(place, id=uuid.uuid4().hex)
        self._places[place.id] = place
        return place

    async def delete_place(self, user_id: str, place_id: str) -> bool:
        place = await self.get_place(user_id, place_id)
        if place is None:
            return False
        del self._places[place_id]
        return True

    async def clear_default_place(self, user_id: str, *, except_id: str) -> None:
        for place_id, place in self._places.items():
            if place.user_id == user_id and place_id != except_id and place.is_default:
                self._places[place_id] = replace(place, is_default=False)

    async def get_state(self, user_id: str) -> OnboardingState:
        return self._states.get(
            user_id, OnboardingState(user_id=user_id, current_step=OnboardingStep.ROLE)
        )

    async def save_state(self, state: OnboardingState) -> OnboardingState:
        self._states[state.user_id] = state
        return state
