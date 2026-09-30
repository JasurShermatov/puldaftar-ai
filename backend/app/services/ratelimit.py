"""Per-user rate limit: Redis (ko'p instance) yoki xotira (bitta instance)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.config import get_settings

_redis = None
_mem: dict[str, deque] = defaultdict(deque)


async def init_redis():
    global _redis
    url = get_settings().redis_url
    if url and _redis is None:
        from redis.asyncio import from_url

        _redis = from_url(url, encoding="utf-8", decode_responses=True)
    return _redis


def redis():
    return _redis


async def hit(key: str, limit: int, window_sec: int = 60) -> bool:
    """True — ruxsat; False — limitdan oshdi."""
    if _redis is not None:
        bucket = f"rl:{key}:{int(time.time() // window_sec)}"
        n = await _redis.incr(bucket)
        if n == 1:
            await _redis.expire(bucket, window_sec + 1)
        return n <= limit
    now = time.monotonic()
    q = _mem[key]
    while q and now - q[0] > window_sec:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True
