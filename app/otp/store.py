"""Where a self-hosted OTP provider keeps its live challenges.

Vendors like MSG91 hold the OTP themselves and need none of this. It exists for
providers that generate their own codes - today the fake one, tomorrow any
self-hosted SMS gateway.

Two implementations: in-memory (tests, single process) and Redis (real
deployments, where TTL expiry and atomic attempt counting come for free).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis


@dataclass
class StoredChallenge:
    mobile: str
    code: str
    attempts_left: int


class OtpChallengeStore(ABC):
    @abstractmethod
    async def put(self, request_id: str, challenge: StoredChallenge, ttl: int) -> None:
        """Save a challenge for `ttl` seconds."""

    @abstractmethod
    async def get(self, request_id: str) -> StoredChallenge | None: ...

    @abstractmethod
    async def delete(self, request_id: str) -> None:
        """Burn a challenge - it can never be used again."""

    @abstractmethod
    async def decrement_attempts(self, request_id: str) -> int:
        """Record a wrong code and return how many attempts remain."""


class InMemoryChallengeStore(OtpChallengeStore):
    def __init__(self) -> None:
        self._entries: dict[str, tuple[StoredChallenge, datetime]] = {}

    async def put(self, request_id: str, challenge: StoredChallenge, ttl: int) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        self._entries[request_id] = (challenge, expires_at)

    async def get(self, request_id: str) -> StoredChallenge | None:
        entry = self._entries.get(request_id)
        if entry is None:
            return None
        challenge, expires_at = entry
        if datetime.now(timezone.utc) >= expires_at:
            del self._entries[request_id]
            return None
        return challenge

    async def delete(self, request_id: str) -> None:
        self._entries.pop(request_id, None)

    async def decrement_attempts(self, request_id: str) -> int:
        entry = self._entries.get(request_id)
        if entry is None:
            return 0
        challenge, expires_at = entry
        challenge.attempts_left -= 1
        self._entries[request_id] = (challenge, expires_at)
        return challenge.attempts_left


class RedisChallengeStore(OtpChallengeStore):
    """A hash per challenge, expired by Redis itself.

    Attempt counting uses HINCRBY so two concurrent wrong guesses cannot both
    read the same remaining count.
    """

    def __init__(self, redis: Redis, *, prefix: str = "otp:challenge"):
        self._redis = redis
        self._prefix = prefix

    def _key(self, request_id: str) -> str:
        return f"{self._prefix}:{request_id}"

    async def put(self, request_id: str, challenge: StoredChallenge, ttl: int) -> None:
        key = self._key(request_id)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(
                key,
                mapping={
                    "mobile": challenge.mobile,
                    "code": challenge.code,
                    "attempts_left": challenge.attempts_left,
                },
            )
            pipe.expire(key, ttl)
            await pipe.execute()

    async def get(self, request_id: str) -> StoredChallenge | None:
        data = await self._redis.hgetall(self._key(request_id))
        if not data:
            return None
        return StoredChallenge(
            mobile=data["mobile"],
            code=data["code"],
            attempts_left=int(data["attempts_left"]),
        )

    async def delete(self, request_id: str) -> None:
        await self._redis.delete(self._key(request_id))

    async def decrement_attempts(self, request_id: str) -> int:
        return await self._redis.hincrby(self._key(request_id), "attempts_left", -1)
