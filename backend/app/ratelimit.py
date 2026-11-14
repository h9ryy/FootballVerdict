import hashlib
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque] = defaultdict(deque)
WINDOW = 60  # секунд


def _key(request: Request) -> str:
    data = request.headers.get("x-init-data") or request.headers.get("x-dev-user")
    if data:
        return "u:" + hashlib.sha1(data.encode()).hexdigest()[:16]
    return "ip:" + (request.client.host if request.client else "?")


def _check(key: str, limit: int) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Слишком много запросов, попробуй через минуту")
    q.append(now)
    if len(_hits) > 20000:   # чистим память от давно неактивных ключей
        for k in [k for k, v in _hits.items() if not v or now - v[-1] > WINDOW]:
            _hits.pop(k, None)


def rate_limit(request: Request) -> None:
    _check("g:" + _key(request), 240)


def strict_limit(request: Request) -> None:
    _check("s:" + _key(request), 10)