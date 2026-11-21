"""Per-client-IP sliding-window rate limiter for GitHub clone requests.

The limiter keeps a log of counted POSIX timestamps per client IP in a
``dict[str, deque[float]]`` guarded by one ``threading.Lock``. A request counted at time
``t`` stays inside the window at a later time ``t'`` while ``t' - t < window_seconds``.

``check_and_count(client_ip, now)`` takes ``now`` as a timezone-aware ``datetime`` (one
reading of the injected Clock); the limiter never reads the system clock. A rejected
request is not recorded. The decision depends only on the limit, the window, the IP, and
the counted timestamps, so replaying the same sequence gives the same decisions.

The caller passes the direct peer address (``request.client.host``); ``X-Forwarded-For``
is never consulted here.
"""

import math
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime

__all__ = ["RateDecision", "RateLimiter"]


@dataclass(frozen=True)
class RateDecision:
    """Outcome of one ``check_and_count`` call."""

    allowed: bool
    retry_after_seconds: int  # 0 when allowed


class RateLimiter:
    """Allow at most ``limit`` counted requests per client IP inside ``window_seconds``."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, int)
            or window_seconds < 1
        ):
            raise ValueError("window_seconds must be a positive integer")
        self._limit = limit
        self._window = float(window_seconds)
        self._log: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def window_seconds(self) -> int:
        return int(self._window)

    def check_and_count(self, client_ip: str, now: datetime) -> RateDecision:
        """Count one request from ``client_ip`` at ``now`` if it is inside the allowance.

        ``now`` must be a timezone-aware ``datetime``; a naive value raises ``ValueError``
        and nothing is counted.
        """
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be a timezone-aware datetime")
        now_ts = now.timestamp()
        with self._lock:
            entries = self._log.get(client_ip)
            if entries is not None:
                while entries and now_ts - entries[0] >= self._window:
                    entries.popleft()
                if not entries:
                    del self._log[client_ip]
                    entries = None
            if entries is None or len(entries) < self._limit:
                if entries is None:
                    entries = deque()
                    self._log[client_ip] = entries
                entries.append(now_ts)
                return RateDecision(allowed=True, retry_after_seconds=0)
            oldest = entries[0]
            retry_after = max(1, math.ceil(self._window - (now_ts - oldest)))
            return RateDecision(allowed=False, retry_after_seconds=retry_after)
