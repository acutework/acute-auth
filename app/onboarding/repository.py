"""Storage contract for everything onboarding collects.

One interface for the four aggregates because they are always read and written
together, by one user, in one flow - splitting them would buy nothing but more
wiring.
"""

from abc import ABC, abstractmethod

from app.onboarding.models import (
    OnboardingState,
    SavedPlace,
    WorkerProfile,
    WorkplaceMembership,
)


class OnboardingRepository(ABC):
    # Profile
    @abstractmethod
    async def get_profile(self, user_id: str) -> WorkerProfile | None: ...

    @abstractmethod
    async def save_profile(self, profile: WorkerProfile) -> WorkerProfile: ...

    # Workplace
    @abstractmethod
    async def get_membership(self, user_id: str) -> WorkplaceMembership | None: ...

    @abstractmethod
    async def save_membership(
        self, membership: WorkplaceMembership
    ) -> WorkplaceMembership: ...

    # Places
    @abstractmethod
    async def list_places(self, user_id: str) -> list[SavedPlace]: ...

    @abstractmethod
    async def get_place(self, user_id: str, place_id: str) -> SavedPlace | None: ...

    @abstractmethod
    async def save_place(self, place: SavedPlace) -> SavedPlace: ...

    @abstractmethod
    async def delete_place(self, user_id: str, place_id: str) -> bool: ...

    @abstractmethod
    async def clear_default_place(self, user_id: str, *, except_id: str) -> None:
        """Only one place is the default; setting one clears the others."""

    # Progress
    @abstractmethod
    async def get_state(self, user_id: str) -> OnboardingState: ...

    @abstractmethod
    async def save_state(self, state: OnboardingState) -> OnboardingState: ...
