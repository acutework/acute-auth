"""The Redis-backed challenge store, rate limiter and denylist."""

import asyncio

import pytest

from app.core.errors import TooManyRequests
from app.otp.store import RedisChallengeStore, StoredChallenge
from app.ratelimit.limiter import RateLimit, RedisRateLimiter
from app.tokens.denylist import RedisTokenDenylist

pytestmark = pytest.mark.integration


class TestChallengeStore:
    async def test_a_stored_challenge_comes_back(self, redis):
        store = RedisChallengeStore(redis)
        await store.put(
            "r1", StoredChallenge(mobile="91999", code="4732", attempts_left=3), 60
        )

        challenge = await store.get("r1")

        assert challenge.mobile == "91999"
        assert challenge.code == "4732"
        assert challenge.attempts_left == 3

    async def test_redis_expires_the_challenge_itself(self, redis):
        store = RedisChallengeStore(redis)
        await store.put(
            "r1", StoredChallenge(mobile="91999", code="4732", attempts_left=3), 1
        )

        await asyncio.sleep(1.2)

        assert await store.get("r1") is None

    async def test_a_deleted_challenge_is_gone(self, redis):
        store = RedisChallengeStore(redis)
        await store.put(
            "r1", StoredChallenge(mobile="91999", code="4732", attempts_left=3), 60
        )

        await store.delete("r1")

        assert await store.get("r1") is None

    async def test_concurrent_wrong_guesses_each_cost_one_attempt(self, redis):
        """HINCRBY is atomic, so three racing guesses cannot all read '2 left'."""
        store = RedisChallengeStore(redis)
        await store.put(
            "r1", StoredChallenge(mobile="91999", code="4732", attempts_left=3), 60
        )

        remaining = await asyncio.gather(*[store.decrement_attempts("r1") for _ in range(3)])

        assert sorted(remaining) == [0, 1, 2]


class TestRateLimiter:
    async def test_counts_rise_within_a_window(self, redis):
        limiter = RedisRateLimiter(redis)
        rule = RateLimit(limit=3, window_seconds=60)

        counts = [await limiter.hit("mobile:1", rule) for _ in range(3)]

        assert counts == [1, 2, 3]

    async def test_check_raises_once_the_limit_is_passed(self, redis):
        limiter = RedisRateLimiter(redis)
        rule = RateLimit(limit=2, window_seconds=60)

        await limiter.check("mobile:1", rule)
        await limiter.check("mobile:1", rule)

        with pytest.raises(TooManyRequests):
            await limiter.check("mobile:1", rule)

    async def test_keys_do_not_share_a_budget(self, redis):
        limiter = RedisRateLimiter(redis)
        rule = RateLimit(limit=1, window_seconds=60)

        await limiter.check("mobile:1", rule)
        await limiter.check("mobile:2", rule)

    async def test_the_window_is_not_extended_by_later_hits(self, redis):
        """EXPIRE NX - otherwise a steady stream of requests would never reset."""
        limiter = RedisRateLimiter(redis)
        rule = RateLimit(limit=10, window_seconds=2)

        await limiter.hit("mobile:1", rule)
        await asyncio.sleep(1)
        await limiter.hit("mobile:1", rule)
        await asyncio.sleep(1.2)

        assert await limiter.hit("mobile:1", rule) == 1


class TestDenylist:
    async def test_a_revoked_token_is_reported_revoked(self, redis):
        denylist = RedisTokenDenylist(redis)

        await denylist.revoke("jti-1", 60)

        assert await denylist.is_revoked("jti-1") is True
        assert await denylist.is_revoked("jti-2") is False

    async def test_the_record_expires_with_the_token(self, redis):
        denylist = RedisTokenDenylist(redis)

        await denylist.revoke("jti-1", 1)
        await asyncio.sleep(1.2)

        assert await denylist.is_revoked("jti-1") is False

    async def test_an_already_expired_token_is_not_stored(self, redis):
        """No point holding a record for a token that can no longer be used."""
        denylist = RedisTokenDenylist(redis)

        await denylist.revoke("jti-1", 0)

        assert await redis.exists("token:revoked:jti-1") == 0
