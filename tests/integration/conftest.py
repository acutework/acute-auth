"""Integration tests: real Postgres, real Redis.

Skipped automatically when the services are not reachable, so `pytest` stays
instant for everyone. Bring them up with `docker compose up -d` and run
`pytest -m integration`.
"""

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db.redis import create_redis
from app.db.session import create_engine, create_session_factory
from app.users.postgres import PostgresUserRepository

TEST_DATABASE_URL = "postgresql+asyncpg://acute_auth:acute_auth@localhost:5433/acute_auth"
TEST_REDIS_URL = "redis://localhost:6380/15"  # db 15: never the app's own


@pytest.fixture(scope="session")
def integration_settings() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret="integration-secret",
        otp_provider="fake",
        database_url=TEST_DATABASE_URL,
        redis_url=TEST_REDIS_URL,
    )


@pytest_asyncio.fixture
async def engine(integration_settings: Settings) -> AsyncEngine:
    engine = create_engine(integration_settings.database_url)
    try:
        async with engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001 - any connection failure means skip
        pytest.skip(f"Postgres is not reachable: {exc}")
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def users(engine: AsyncEngine) -> PostgresUserRepository:
    """A repository on a clean users table.

    Truncated on the way in and on the way out, so a test run leaves no rows
    behind in what is usually also your development database.
    """
    from sqlalchemy import text

    async def truncate() -> None:
        async with engine.begin() as connection:
            # CASCADE: the onboarding tables reference users.
            await connection.execute(text("TRUNCATE TABLE users CASCADE"))

    await truncate()
    yield PostgresUserRepository(create_session_factory(engine))
    await truncate()


@pytest_asyncio.fixture
async def onboarding_repo(engine: AsyncEngine):
    """A Postgres onboarding repository over a clean set of tables."""
    from sqlalchemy import text

    from app.onboarding.postgres import PostgresOnboardingRepository

    async def truncate() -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE TABLE saved_places, worker_profiles, "
                    "workplace_memberships, onboarding_states, "
                    "circle_invites, circle_members, circles, users CASCADE"
                )
            )

    await truncate()
    yield PostgresOnboardingRepository(create_session_factory(engine))
    await truncate()


@pytest_asyncio.fixture
async def circles_repo(engine: AsyncEngine):
    """A Postgres circles repository over a clean set of tables."""
    from sqlalchemy import text

    from app.circles.postgres import PostgresCirclesRepository

    async def truncate() -> None:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "TRUNCATE TABLE circle_invites, circle_members, circles, "
                    "users CASCADE"
                )
            )

    await truncate()
    yield PostgresCirclesRepository(create_session_factory(engine))
    await truncate()


@pytest_asyncio.fixture
async def seeded_user(engine: AsyncEngine) -> str:
    """A real users row, since every onboarding table references it."""
    import uuid

    from sqlalchemy import text

    user_id = uuid.uuid4()
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO users (id, mobile, name) "
                "VALUES (:id, :mobile, :name)"
            ),
            {"id": user_id, "mobile": f"9199{user_id.int % 10**8:08d}", "name": "T"},
        )
    return str(user_id)


@pytest_asyncio.fixture
async def redis(integration_settings: Settings) -> Redis:
    client = create_redis(integration_settings.redis_url)
    try:
        await client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Redis is not reachable: {exc}")
    await client.flushdb()
    yield client
    await client.aclose()
