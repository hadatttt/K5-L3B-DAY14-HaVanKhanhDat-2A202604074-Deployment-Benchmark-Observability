"""
Rate limiting (tiêu chí 7).

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429 kèm header Retry-After
  • State lưu trong Redis (sorted set) → dùng chung giữa worker/instance, còn sau restart
"""
import hashlib
import time
import uuid

import redis
from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60

# Chạy atomic trong Redis để nhiều worker không vượt giới hạn cùng lúc.
_SLIDING_WINDOW = r.register_script(
    """
    local key = KEYS[1]
    local now = tonumber(ARGV[1])
    local window = tonumber(ARGV[2])
    local limit = tonumber(ARGV[3])
    redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
    local count = redis.call('ZCARD', key)
    if count >= limit then
        local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
        return {0, tostring(oldest[2] or now)}
    end
    redis.call('ZADD', key, now, ARGV[4])
    redis.call('EXPIRE', key, window)
    return {1, '0'}
    """
)


def check_rate_limit(key: str) -> None:
    # Không lưu API key thô trong Redis
    bucket = "ratelimit:" + hashlib.sha256(key.encode()).hexdigest()[:32]
    now = time.time()
    try:
        allowed, oldest = _SLIDING_WINDOW(
            keys=[bucket],
            args=[now, WINDOW_SECONDS, settings.rate_limit_per_minute, f"{now}-{uuid.uuid4().hex}"],
        )
    except redis.RedisError:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")
    if int(allowed) == 0:
        retry_after = max(1, int(float(oldest) + WINDOW_SECONDS - now) + 1)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
