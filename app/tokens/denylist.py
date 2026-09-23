"""Revoked refresh tokens.

Refresh tokens are JWTs, so nothing server-side is consulted when one is used -
which means signing out cannot invalidate one. Each refresh token carries a
`jti`; revoking it records that id until the token would have expired anyway,
so the list can never grow without bound.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis


class TokenDenylist(ABC):
    @abstractmethod
    async def revoke(self, jti: str, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def is_revoked(self, jti: str) -> bool: ...


class InMemoryTokenDenylist(TokenDenylist):
    def __init__(self) -> None:
        self._revoked: dict[str, datetime] = {}

    async def revoke(self, jti: str, ttl_seconds: int) -> None:
        self._revoked[jti] = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)

    async def is_revoked(self, jti: str) -> bool:
        expires_at = self._revoked.get(jti)
        if expires_at is None:
            return False
        if datetime.now(timezone.utc) >= expires_at:
            del self._revoked[jti]
            return False
        return True


class RedisTokenDenylist(TokenDenylist):
    def __init__(self, redis: Redis, *, prefix: str = "token:revoked"):
        self._redis = redis
        self._prefix = prefix

    async def revoke(self, jti: str, ttl_seconds: int) -> None:
        # A token already past its expiry needs no record.
        if ttl_seconds > 0:
            await self._redis.set(f"{self._prefix}:{jti}", "1", ex=ttl_seconds)

    async def is_revoked(self, jti: str) -> bool:
        return await self._redis.exists(f"{self._prefix}:{jti}") == 1


class NoTokenDenylist(TokenDenylist):
    """Used when Redis is not configured; sign-out cannot revoke anything."""

    async def revoke(self, jti: str, ttl_seconds: int) -> None:
        return None

    async def is_revoked(self, jti: str) -> bool:
        return False
