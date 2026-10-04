"""The directory over the in-memory onboarding store.

Reads that store's dictionaries directly: it is a test double for the Postgres
version, which reads the same tables the onboarding repository writes.
"""

from app.directory.matching import matches, nearest
from app.directory.models import Person, SearchQuery, person_from
from app.directory.repository import DirectoryRepository
from app.onboarding.memory import InMemoryOnboardingRepository


class InMemoryDirectoryRepository(DirectoryRepository):
    def __init__(self, onboarding: InMemoryOnboardingRepository) -> None:
        self._onboarding = onboarding

    def _people(self) -> list[Person]:
        store = self._onboarding
        people = []
        for user_id, profile in store._profiles.items():
            state = store._states.get(user_id)
            if state is None or not state.is_complete:
                continue
            places = [p for p in store._places.values() if p.user_id == user_id]
            people.append(person_from(profile, store._memberships.get(user_id), places))
        return people

    async def search(self, query: SearchQuery, *, offset: int, limit: int) -> list[Person]:
        found = [p for p in self._people() if matches(p, query)]
        if query.near is not None:
            found.sort(key=lambda p: (nearest(p, query.near)[0], p.name.casefold(), p.user_id))
        else:
            found.sort(key=lambda p: (p.name.casefold(), p.user_id))
        return found[offset : offset + limit]

    async def get_person(self, user_id: str) -> Person | None:
        return next((p for p in self._people() if p.user_id == user_id), None)
