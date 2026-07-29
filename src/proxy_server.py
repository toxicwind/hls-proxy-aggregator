"""Proxy Server — JMP2-Uber-Max HLS aggregator & commercial stripper.

Endpoints:
  GET  /playlist.m3u8           — Consolidated English playlist
  GET  /category/{name}.m3u8    — Per-category playlist
  GET  /proxy/*                 — Proxy any URL through (with SCTE-35 stripping)
  GET  /health                  — Health check
  GET  /metrics                 — Prometheus-style metrics
"""
from __future__ import annotations
import asyncio, logging, time, json
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

import aiohttp
from aiohttp import web

from scte_parser import Scte35Parser
from url_validator import UrlValidator, ProbeResult
from playlist_engine import PlaylistEngine, ChannelEntry

logger = logging.getLogger("proxy")


class ProxyServer:
    """Production-grade HLS proxy with manifest rewriting."""

    def __init__(self, config: dict):
        self.cfg = config
        self.scte = Scte35Parser(
            min_ad_sec=config["scte35"]["min_ad_duration_sec"],
            max_ad_sec=config["scte35"]["max_ad_duration_sec"],
        )
        self.validator = UrlValidator(
            timeout_sec=config["validation"]["timeout_sec"],
            retry_count=config["validation"]["retry_count"],
            retry_delay_sec=config["validation"]["retry_delay_sec"],
            acceptable_status=set(config["validation"]["acceptable_status"]),
            acceptable_content_types=set(config["validation"]["acceptable_content_types"]),
            max_concurrent=config["validation"]["concurrency"],
        )
        self.engine = PlaylistEngine()
        self.manifest_cache: Dict[str, tuple[str, float]] = {}  # url → (body, timestamp)
        self.cache_ttl = config["cache"]["manifest_ttl_sec"]
        self.segment_cache: Dict[str, bytes] = {}
        self.segment_ttl = config["cache"]["segment_ttl_sec"]
        self.app = web.Application()
        self._setup_routes()
        self._metrics = {
            "requests_total": 0,
            "manifests_served": 0,
            "manifests_rewritten": 0,
            "segments_proxied": 0,
            "ads_stripped": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------

    def _setup_routes(self) -> None:
        self.app.router.add_get("/playlist.m3u8", self.handle_playlist)
        self.app.router.add_get("/category/{name}.m3u8", self.handle_category)
        self.app.router.add_get("/proxy/{tail:.*}", self.handle_proxy)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/metrics", self.handle_metrics)
        self.app.router.add_get("/", self.handle_index)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def handle_index(self, request: web.Request) -> web.Response:
        self._metrics["requests_total"] += 1
        html = """<!DOCTYPE html>
<html><head><title>JMP2-Uber-Max</title></head>
<body style="font-family:monospace;background:#0a0a0a;color:#0f0;padding:40px">
<h1>🐸 JMP2-Uber-Max</h1>
<p>Netflix-grade HLS proxy aggregator</p>
<ul>
<li><a href="/playlist.m3u8">/playlist.m3u8</a> — Consolidated English playlist</li>
<li><a href="/category/Movies.m3u8">/category/Movies.m3u8</a> — Per-category</li>
<li><a href="/health">/health</a> — Health check</li>
<li><a href="/metrics">/metrics</a> — Prometheus metrics</li>
</ul>
</body></html>"""
        return web.Response(text=html, content_type="text/html")

    async def handle_playlist(self, request: web.Request) -> web.Response:
        self._metrics["requests_total"] += 1
        try:
            body = self.engine.build_consolidated(english_only=True)
            self._metrics["manifests_served"] += 1
            return web.Response(
                text=body,
                content_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": f"max-age={self.cache_ttl}"},
            )
        except Exception as exc:
            logger.error("Playlist error: %s", exc)
            self._metrics["errors"] += 1
            return web.Response(status=500, text=f"Error: {exc}")

    async def handle_category(self, request: web.Request) -> web.Response:
        self._metrics["requests_total"] += 1
        name = request.match_info["name"]
        try:
            cats = self.engine.build_by_category(english_only=True)
            body = cats.get(name)
            if not body:
                available = ", ".join(sorted(cats.keys()))
                return web.Response(
                    status=404,
                    text=f"Category '{name}' not found. Available: {available}",
                )
            self._metrics["manifests_served"] += 1
            return web.Response(
                text=body,
                content_type="application/vnd.apple.mpegurl",
                headers={"Cache-Control": f"max-age={self.cache_ttl}"},
            )
        except Exception as exc:
            logger.error("Category error: %s", exc)
            self._metrics["errors"] += 1
            return web.Response(status=500, text=f"Error: {exc}")

    async def handle_proxy(self, request: web.Request) -> web.Response:
        """Proxy any URL with optional SCTE-35 stripping."""
        self._metrics["requests_total"] += 1
        tail = request.match_info["tail"]
        target_url = unquote(tail)

        if not target_url.startswith("http"):
            return web.Response(status=400, text="URL must start with http(s)")

        # Check cache for manifests
        cached = self.manifest_cache.get(target_url)
        if cached and (time.time() - cached[1]) < self.cache_ttl:
            return web.Response(
                text=cached[0],
                content_type="application/vnd.apple.mpegurl",
            )

        try:
            body, content_type = await self._fetch_upstream(target_url)

            # If it's an M3U8, strip SCTE-35
            if "mpegurl" in content_type or "m3u8" in target_url.lower():
                clean_body, cue_ranges = self.scte.strip_manifest(body)
                if cue_ranges:
                    self._metrics["manifests_rewritten"] += 1
                    self._metrics["ads_stripped"] += sum(
                        1 for r in cue_ranges
                    )
                    logger.info(
                        "Stripped %d ad ranges from %s",
                        len(cue_ranges), target_url,
                    )
                body = clean_body
                self.manifest_cache[target_url] = (body, time.time())
                return web.Response(
                    text=body,
                    content_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": f"max-age={self.cache_ttl}"},
                )

            # Segment proxy
            self._metrics["segments_proxied"] += 1
            return web.Response(
                body=body.encode() if isinstance(body, str) else body,
                content_type=content_type or "application/octet-stream",
                headers={"Cache-Control": f"max-age={self.segment_ttl}"},
            )

        except Exception as exc:
            logger.error("Proxy error for %s: %s", target_url, exc)
            self._metrics["errors"] += 1
            return web.Response(status=502, text=f"Upstream error: {exc}")

    async def handle_health(self, request: web.Request) -> web.Response:
        return web.json_response({
            "status": "ok",
            "timestamp": time.time(),
            "manifest_cache_size": len(self.manifest_cache),
            "segment_cache_size": len(self.segment_cache),
        })

    async def handle_metrics(self, request: web.Request) -> web.Response:
        lines = []
        for key, val in self._metrics.items():
            lines.append(f"jmp2_{key} {val}")
        lines.append(f"jmp2_manifest_cache_size {len(self.manifest_cache)}")
        lines.append(f"jmp2_segment_cache_size {len(self.segment_cache)}")
        return web.Response(text="\n".join(lines) + "\n", content_type="text/plain")

    # ------------------------------------------------------------------
    # Internal: upstream fetch
    # ------------------------------------------------------------------

    async def _fetch_upstream(self, url: str) -> tuple[str, str]:
        timeout = aiohttp.ClientTimeout(total=self.cfg["proxy"]["upstream_timeout"])
        connector = aiohttp.TCPConnector(limit=100, ssl=False)
        headers = dict(self.cfg["proxy"]["add_headers"])
        headers["User-Agent"] = self.cfg["proxy"]["user_agent"]

        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout
        ) as session:
            async with session.get(url, headers=headers, allow_redirects=True) as resp:
                ct = resp.headers.get("Content-Type", "application/octet-stream")
                body = await resp.text()
                return body, ct

    # ------------------------------------------------------------------
    # Background tasks
    # ------------------------------------------------------------------

    async def background_health_check(self) -> None:
        """Periodically validate URLs and invalidate bad ones."""
        interval = self.cfg["validation"]["health_check_interval_sec"]
        while True:
            await asyncio.sleep(interval)
            logger.info("Starting background health check...")
            # In a full implementation, we'd check all known URLs
            # For now, just clear old cache entries
            now = time.time()
            expired = [
                k for k, v in self.manifest_cache.items()
                if now - v[1] > self.cache_ttl * 2
            ]
            for k in expired:
                del self.manifest_cache[k]
            logger.info("Cleared %d expired manifest cache entries", len(expired))
