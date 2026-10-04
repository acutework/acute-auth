import uuid

import pytest

from app.directory.memory import InMemoryDirectoryRepository
from app.onboarding.memory import InMemoryOnboardingRepository
from tests.directory_contract import DirectoryContract
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
