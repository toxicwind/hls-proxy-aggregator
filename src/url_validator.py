#!/usr/bin/env python3
"""
url_validator.py — Async URL health checker with retry and caching.
"""
import asyncio, time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
import aiohttp

@dataclass
class ProbeResult:
    url: str
    status: int = 0
    ok: bool = False
    content_type: str = ""
    latency_ms: float = 0.0
    redirect_url: Optional[str] = None
    error: Optional[str] = None
    checked_at: float = 0.0

class UrlValidator:
    GOOD_STATUS = {200, 204, 301, 302, 307, 308}
    GOOD_CT = {
        "application/vnd.apple.mpegurl", "application/x-mpegurl",
        "audio/mpegurl", "video/mp2t", "video/mp4", "audio/aac",
        "audio/mp3", "application/octet-stream", "text/plain",
    }

    def __init__(self, timeout_sec=10.0, retry_count=2, retry_delay_sec=1.0,
                 max_concurrent=50):
        self.timeout_sec = timeout_sec
        self.retry_count = retry_count
        self.retry_delay_sec = retry_delay_sec
        self.max_concurrent = max_concurrent
        self._cache: Dict[str, ProbeResult] = {}
        self._cache_ttl_sec = 60.0
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def validate_batch(self, urls: List[str]) -> List[ProbeResult]:
        tasks = [self._probe_with_cache(u) for u in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def validate_single(self, url: str) -> ProbeResult:
        return await self._probe_with_cache(url)

    async def _probe_with_cache(self, url: str) -> ProbeResult:
        cached = self._cache.get(url)
        if cached and (time.time() - cached.checked_at) < self._cache_ttl_sec:
            return cached
        result = await self._probe(url)
        self._cache[url] = result
        return result

    async def _probe(self, url: str) -> ProbeResult:
        async with self._semaphore:
            for attempt in range(self.retry_count + 1):
                t0 = time.perf_counter()
                try:
                    result = await self._do_request(url)
                    result.latency_ms = (time.perf_counter() - t0) * 1000
                    if result.ok or attempt == self.retry_count:
                        return result
                    await asyncio.sleep(self.retry_delay_sec * (attempt + 1))
                except Exception as exc:
                    latency = (time.perf_counter() - t0) * 1000
                    if attempt == self.retry_count:
                        return ProbeResult(
                            url=url, status=0, ok=False,
                            latency_ms=latency, error=str(exc),
                            checked_at=time.time()
                        )
                    await asyncio.sleep(self.retry_delay_sec * (attempt + 1))
            return ProbeResult(url=url, ok=False, error="exhausted", checked_at=time.time())

    async def _do_request(self, url: str) -> ProbeResult:
        timeout = aiohttp.ClientTimeout(total=self.timeout_sec)
        connector = aiohttp.TCPConnector(limit=100, ssl=False, enable_cleanup_closed=True)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
            "Connection": "keep-alive",
        }
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
            async with session.head(url, headers=headers, allow_redirects=True, ssl=False) as resp:
                ct = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                redirect = str(resp.url) if str(resp.url) != url else None
                ok = resp.status in self.GOOD_STATUS
                if ok and ct:
                    ok = any(ct.startswith(g) for g in self.GOOD_CT) or ct == ""
                return ProbeResult(
                    url=url, status=resp.status, ok=ok, content_type=ct,
                    redirect_url=redirect, checked_at=time.time()
                )
