"""Directory storage: reads profiles, workplaces and practice locations, writes nothing."""

from abc import ABC, abstractmethod

from app.directory.models import Person, SearchQuery


class DirectoryRepository(ABC):
    @abstractmethod
    async def search(self, query: SearchQuery, *, offset: int, limit: int) -> list[Person]:
        """Onboarding-complete workers matching the query, nearest first when
        located, otherwise by name; ties by user id."""

    @abstractmethod
    async def get_person(self, user_id: str) -> Person | None:
        """None for an unknown user or one who has not finished onboarding."""
