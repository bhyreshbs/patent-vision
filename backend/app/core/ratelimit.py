import threading
import time
from collections import defaultdict, deque

from fastapi import Depends

from app.core.config import get_settings
from app.core.errors import ApiError


class RateLimiter:
    """Sliding one-minute window per (bucket, key). In-memory: fine for a single-process prototype."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, int], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()

    def check(self, bucket: str, key: int, limit: int, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[(bucket, key)]
            while hits and now - hits[0] >= 60:
                hits.popleft()
            if len(hits) >= limit:
                raise ApiError(
                    429,
                    "rate_limited",
                    f"Too many {bucket} requests. Limit is {limit} per minute.",
                    "Wait a moment and try again.",
                )
            hits.append(now)


limiter = RateLimiter()


def rate_limit(bucket: str):
    from app.api.deps import get_current_user  # local import avoids a cycle

    def _dep(user=Depends(get_current_user)):
        limiter.check(bucket, user.id, get_settings().rate_limit_per_minute)

    return _dep
