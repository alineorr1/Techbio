"""Rate-limited async HTTP with on-disk response cache.

Every external call goes through this module. Cache key is method + URL + body.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src.paths import HTTP_CACHE_DIR, ensure_dirs


@dataclass
class RateLimiter:
    requests_per_second: float
    _lock: asyncio.Lock = None  # type: ignore[assignment]
    _last: float = 0.0

    def __post_init__(self) -> None:
        self._lock = asyncio.Lock()
        self.min_interval = 1.0 / max(self.requests_per_second, 0.01)

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last + self.min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class HttpClient:
    def __init__(
        self,
        *,
        requests_per_second: float = 3.0,
        max_concurrency: int = 4,
        timeout: float = 60.0,
        cache_dir: Path | None = None,
        user_agent: str = "wh-failed-asset-triage/0.1 (research; local pipeline)",
    ) -> None:
        ensure_dirs()
        self.limiter = RateLimiter(requests_per_second)
        self.sema = asyncio.Semaphore(max_concurrency)
        self.cache_dir = cache_dir or HTTP_CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.user_agent = user_agent
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "HttpClient":
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent},
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _key(self, method: str, url: str, body: str | None) -> Path:
        blob = f"{method}\n{url}\n{body or ''}".encode()
        digest = hashlib.sha256(blob).hexdigest()
        return self.cache_dir / f"{digest}.json"

    def cache_get(self, method: str, url: str, body: str | None = None) -> Any | None:
        path = self._key(method, url, body)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def cache_put(self, method: str, url: str, body: str | None, payload: Any) -> None:
        path = self._key(method, url, body)
        path.write_text(json.dumps(payload, ensure_ascii=False))

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        skip_cache: bool = False,
    ) -> Any:
        if params:
            req = httpx.Request("GET", url, params=params)
            full = str(req.url)
        else:
            full = url
        if not skip_cache:
            hit = self.cache_get("GET", full)
            if hit is not None:
                return hit
        client = self._require()
        async with self.sema:
            await self.limiter.acquire()
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        self.cache_put("GET", full, None, payload)
        return payload

    async def post_json(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        skip_cache: bool = False,
    ) -> Any:
        body = json.dumps(json_body, sort_keys=True, separators=(",", ":"))
        if not skip_cache:
            hit = self.cache_get("POST", url, body)
            if hit is not None:
                return hit
        client = self._require()
        async with self.sema:
            await self.limiter.acquire()
            resp = await client.post(url, json=json_body)
            resp.raise_for_status()
            payload = resp.json()
        self.cache_put("POST", url, body, payload)
        return payload

    def _require(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("HttpClient must be used as an async context manager")
        return self._client
