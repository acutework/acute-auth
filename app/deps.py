"""Dependency wiring.

`build_auth_service` assembles the service from settings; everything optional
degrades to an in-memory equivalent, which is what makes Postgres and Redis
genuinely optional rather than assumed. The module-level instance is what the
running app uses; tests build their own and override `get_auth_service`.
"""

from typing import Annotated

from fastapi import Depends, Header
from redis.asyncio import Redis

from app.catalog.repository import (
    CatalogRepository,
    PostgresCatalogRepository,
    StaticCatalogRepository,
)
from app.config import Settings, get_settings
from app.core.errors import InvalidToken
from app.core.security import TokenService
from app.db.redis import create_redis
from app.db.session import create_engine, create_session_factory
from app.onboarding.memory import InMemoryOnboardingRepository
from app.onboarding.postgres import PostgresOnboardingRepository
from app.onboarding.repository import OnboardingRepository
from app.onboarding.service import OnboardingService
from app.otp.challenge import ChallengeCodec
from app.otp.registry import build_otp_provider
from app.otp.store import InMemoryChallengeStore, OtpChallengeStore, RedisChallengeStore
from app.ratelimit.limiter import (
    InMemoryRateLimiter,
    RateLimit,
    RateLimiter,
    RedisRateLimiter,
)
from app.places.registry import build_place_provider
from app.services.auth_service import AuthService
from app.tokens.denylist import (
    InMemoryTokenDenylist,
    RedisTokenDenylist,
    TokenDenylist,
)
from app.users.memory import InMemoryUserRepository, demo_users
from app.users.models import User
from app.users.postgres import PostgresUserRepository
from app.users.repository import UserRepository


def build_session_factory(settings: Settings):
    """One engine per process; every Postgres repository shares it."""
    return create_session_factory(create_engine(settings.database_url))


def build_user_repository(settings: Settings, session_factory=None) -> UserRepository:
    if settings.uses_postgres:
        return PostgresUserRepository(session_factory or build_session_factory(settings))
    return InMemoryUserRepository(seed=demo_users())


def build_onboarding_repository(
    settings: Settings, session_factory=None
) -> OnboardingRepository:
    if settings.uses_postgres:
        return PostgresOnboardingRepository(
            session_factory or build_session_factory(settings)
        )
    return InMemoryOnboardingRepository()


def build_catalog_repository(settings: Settings, session_factory=None) -> CatalogRepository:
    if settings.uses_postgres:
        return PostgresCatalogRepository(
            session_factory or build_session_factory(settings)
        )
    return StaticCatalogRepository()


def build_onboarding_service(
    settings: Settings, *, repository: OnboardingRepository | None = None
) -> OnboardingService:
    return OnboardingService(
        repository=repository or build_onboarding_repository(settings),
        # None when no key is configured: address search is then disabled, but
        # a user can still type an address by hand.
        place_provider=build_place_provider(settings)
        if settings.uses_place_search
        else None,
    )


def build_challenge_store(redis: Redis | None) -> OtpChallengeStore:
    return RedisChallengeStore(redis) if redis else InMemoryChallengeStore()


def build_rate_limiter(redis: Redis | None) -> RateLimiter:
    # Without Redis the counters are per-process, so they hold for a single
    # instance but are not shared across a deployment.
    return RedisRateLimiter(redis) if redis else InMemoryRateLimiter()


def build_denylist(redis: Redis | None) -> TokenDenylist:
    return RedisTokenDenylist(redis) if redis else InMemoryTokenDenylist()


def build_auth_service(
    settings: Settings,
    *,
    redis: Redis | None = None,
    users: UserRepository | None = None,
) -> AuthService:
    codec = ChallengeCodec(settings.jwt_secret, ttl_seconds=settings.otp_ttl_seconds)
    return AuthService(
        otp_provider=build_otp_provider(
            settings, codec, store=build_challenge_store(redis)
        ),
        users=users or build_user_repository(settings),
        tokens=TokenService(settings),
        rate_limiter=build_rate_limiter(redis),
        denylist=build_denylist(redis),
        send_limit=RateLimit(
            limit=settings.otp_send_limit,
            window_seconds=settings.otp_send_window_seconds,
        ),
        verify_limit=RateLimit(
            limit=settings.otp_verify_limit,
            window_seconds=settings.otp_verify_window_seconds,
        ),
    )


# Built on first use rather than at import, so importing the app never opens a
# connection or validates a provider's credentials. That keeps `import app.main`
# safe in tests and tooling regardless of what the local .env says.
_singletons: dict[str, object] = {}


def _singleton(key: str, factory):
    if key not in _singletons:
        _singletons[key] = factory()
    return _singletons[key]


def _redis_client() -> Redis | None:
    settings = get_settings()
    if not settings.uses_redis:
        return None
    return _singleton("redis", lambda: create_redis(settings.redis_url))


def _shared_session_factory():
    settings = get_settings()
    if not settings.uses_postgres:
        return None
    return _singleton("session_factory", lambda: build_session_factory(settings))


def get_auth_service() -> AuthService:
    settings = get_settings()
    return _singleton(
        "auth_service",
        lambda: build_auth_service(
            settings,
            redis=_redis_client(),
            users=build_user_repository(settings, _shared_session_factory()),
        ),
    )


def get_onboarding_service() -> OnboardingService:
    settings = get_settings()
    return _singleton(
        "onboarding_service",
        lambda: build_onboarding_service(
            settings,
            repository=build_onboarding_repository(
                settings, _shared_session_factory()
            ),
        ),
    )


def get_catalog_repository() -> CatalogRepository:
    settings = get_settings()
    return _singleton(
        "catalog",
        lambda: build_catalog_repository(settings, _shared_session_factory()),
    )


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


OnboardingServiceDep = Annotated[OnboardingService, Depends(get_onboarding_service)]


CatalogDep = Annotated[CatalogRepository, Depends(get_catalog_repository)]


def bearer_token(authorization: Annotated[str | None, Header()] = None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise InvalidToken("Missing bearer token.")
    return authorization.split(" ", 1)[1].strip()


BearerTokenDep = Annotated[str, Depends(bearer_token)]


async def current_user(auth: AuthServiceDep, token: BearerTokenDep) -> User:
    return await auth.current_user(token)


CurrentUserDep = Annotated[User, Depends(current_user)]


async def aclose() -> None:
    """Release whatever was actually built: HTTP clients, Redis, DB pools."""
    for key in ("auth_service", "onboarding_service"):
        service = _singletons.get(key)
        if service is not None:
            await service.aclose()
    redis = _singletons.get("redis")
    if redis is not None:
        await redis.aclose()
    _singletons.clear()
