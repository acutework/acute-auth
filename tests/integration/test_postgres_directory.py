"""The directory against a real Postgres. Needs `docker compose up`.

Uses the `onboarding_repo` fixture, which truncates the onboarding tables and
users - acute-auth's dev data. Confirm with the user before the first run."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.db.session import create_session_factory
from app.directory.postgres import PostgresDirectoryRepository
from tests.directory_contract import DirectoryContract
from tests.directory_helpers import seed_person

pytestmark = pytest.mark.integration


class TestPostgresDirectory(DirectoryContract):
    @pytest_asyncio.fixture
    async def directory(self, engine, onboarding_repo):
        return PostgresDirectoryRepository(create_session_factory(engine))

    @pytest.fixture
    def seed(self, engine, onboarding_repo):
        async def make(name: str, **kwargs) -> str:
            user_id = str(uuid.uuid4())
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO users (id, mobile, name) VALUES (:id, :mobile, :name)"),
                    {"id": user_id, "mobile": "91" + str(uuid.uuid4().int)[:10], "name": name},
                )
            await seed_person(onboarding_repo, user_id, name=name, **kwargs)
            return user_id

        return make
