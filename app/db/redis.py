"""Redis client factory.

One client is shared by the whole process; redis.asyncio pools connections
internally, so there is nothing to create per request.
"""

from redis.asyncio import Redis


def create_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)
