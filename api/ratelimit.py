from quota import get_redis

GENERATE_LIMIT_PER_HOUR = 10
SCORE_LIMIT_PER_HOUR = 20
WINDOW_SECONDS = 3600

_INCR_WITH_EXPIRE_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
else
  local ttl = redis.call('TTL', KEYS[1])
  if ttl < 0 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
  end
end
return count
"""


def _check_window(key: str, limit: int) -> tuple[bool, int]:
    redis = get_redis()
    count = int(
        redis.eval(
            _INCR_WITH_EXPIRE_LUA,
            keys=[key],
            args=[str(WINDOW_SECONDS)],
        )
    )
    if count > limit:
        return False, 0
    return True, max(limit - count, 0)


def allow_generate(user_id: str) -> tuple[bool, int]:
    return _check_window(f"ideagen:rl:generate:{user_id}", GENERATE_LIMIT_PER_HOUR)


def allow_score(user_id: str) -> tuple[bool, int]:
    return _check_window(f"ideagen:rl:score:{user_id}", SCORE_LIMIT_PER_HOUR)
