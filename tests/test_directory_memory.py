import uuid

import pytest

from app.directory.memory import InMemoryDirectoryRepository
from app.directory.models import GeoPoint, SearchQuery
from app.onboarding.memory import InMemoryOnboardingRepository
from tests.directory_contract import PRACTICE, DirectoryContract
from tests.directory_helpers import seed_person


class TestInMemoryDirectory(DirectoryContract):
    @pytest.fixture
    def onboarding(self):
        return InMemoryOnboardingRepository()

    @pytest.fixture
    def directory(self, onboarding):
        return InMemoryDirectoryRepository(onboarding)

    @pytest.fixture
    def seed(self, onboarding):
        async def make(name: str, **kwargs) -> str:
            user_id = str(uuid.uuid4())
            await seed_person(onboarding, user_id, name=name, **kwargs)
            return user_id

        return make

    async def test_practice_locations_are_listed_by_label_so_ties_break_the_same_way_each_time(
        self, directory, seed
    ):
        user = await seed("Dr Two", places=[("Zeta", 17.43, 78.41, PRACTICE), ("Alpha", 17.43, 78.41, PRACTICE)])

        person = await directory.get_person(user)
        [found] = await directory.search(SearchQuery(near=GeoPoint(17.43, 78.41), radius_km=1), offset=0, limit=5)

        assert [p.label for p in person.practice_locations] == ["Alpha", "Zeta"]
        assert [p.label for p in found.practice_locations] == ["Alpha", "Zeta"]
