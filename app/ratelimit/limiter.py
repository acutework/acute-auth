"""How often a mobile number may ask for an OTP.

Without this, anyone can loop /auth/otp/request and burn SMS credits. The
window is fixed rather than sliding: simple, one Redis key, and precise enough
for a limit measured in sends per hour.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimit:
    """`limit` actions allowed per `window_seconds`."""

    limit: int
    window_seconds: int


class RateLimiter(ABC):
    @abstractmethod
    async def hit(self, key: str, rule: RateLimit) -> int:
        """Record one action and return how many have happened in this window."""

    async def check(self, key: str, rule: RateLimit) -> None:
        """Raise TooManyRequests once the limit is exceeded."""
        from app.core.errors import TooManyRequests

        count = await self.hit(key, rule)
        if count > rule.limit:
            raise TooManyRequests(
                f"Too many attempts. Try again in "
                f"{max(1, rule.window_seconds // 60)} minutes."
            )


class InMemoryRateLimiter(RateLimiter):
    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, datetime]] = {}

    async def hit(self, key: str, rule: RateLimit) -> int:
        now = datetime.now(timezone.utc)
        count, expires_at = self._windows.get(key, (0, now))
        if now >= expires_at:
            count, expires_at = 0, now + timedelta(seconds=rule.window_seconds)
        count += 1
        self._windows[key] = (count, expires_at)
        return count


class RedisRateLimiter(RateLimiter):
    """INCR plus an EXPIRE on first write - two commands, one round trip."""

    def __init__(self, redis: Redis, *, prefix: str = "ratelimit"):
        self._redis = redis
        self._prefix = prefix

    async def hit(self, key: str, rule: RateLimit) -> int:
        redis_key = f"{self._prefix}:{key}"
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            # NX so a running window is never extended by later hits.
            pipe.expire(redis_key, rule.window_seconds, nx=True)
            count, _ = await pipe.execute()
        return int(count)


class NoRateLimiter(RateLimiter):
    """Used when rate limiting is switched off."""

    async def hit(self, key: str, rule: RateLimit) -> int:
        return 0
