from quota import get_redis

GENERATE_LIMIT_PER_HOUR = 10
SCORE_LIMIT_PER_HOUR = 20


def _check_window(key: str, limit: int) -> tuple[bool, int]:
    redis = get_redis()
    count = int(redis.incr(key))
    if count == 1:
        redis.expire(key, 3600)
    if count > limit:
        return False, max(limit - count, 0)
    return True, max(limit - count, 0)


def allow_generate(user_id: str) -> tuple[bool, int]:
    return _check_window(f"ideagen:rl:generate:{user_id}", GENERATE_LIMIT_PER_HOUR)


def allow_score(user_id: str) -> tuple[bool, int]:
    return _check_window(f"ideagen:rl:score:{user_id}", SCORE_LIMIT_PER_HOUR)
