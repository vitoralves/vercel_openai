import os
from typing import Optional

from upstash_redis import Redis

FREE_LIFETIME_LIMIT = 1
PREMIUM_LIFETIME_LIMIT = 5
USAGE_KEY_PREFIX = "ideagen:usage:"

_redis: Optional[Redis] = None


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        url = os.getenv("UPSTASH_REDIS_REST_URL")
        token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
        if not url or not token:
            raise RuntimeError(
                "UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN must be set"
            )
        _redis = Redis(url=url, token=token)
    return _redis


def usage_key(user_id: str) -> str:
    return f"{USAGE_KEY_PREFIX}{user_id}"


def get_usage(user_id: str) -> int:
    value = get_redis().get(usage_key(user_id))
    if value is None:
        return 0
    return int(value)


def limit_for_plan(premium: bool) -> int:
    return PREMIUM_LIFETIME_LIMIT if premium else FREE_LIFETIME_LIMIT


def reserve_request(user_id: str, limit: int) -> tuple[bool, int]:
    """
    Atomically consume one request credit (generate or score).
    Returns (allowed, used_after).
    """
    redis = get_redis()
    key = usage_key(user_id)
    used = int(redis.incr(key))
    if used > limit:
        redis.decr(key)
        return False, limit
    return True, used


def refund_request(user_id: str) -> None:
    redis = get_redis()
    key = usage_key(user_id)
    used = get_usage(user_id)
    if used > 0:
        redis.decr(key)
