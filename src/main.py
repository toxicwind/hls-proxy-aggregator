#!/usr/bin/env python3
"""JMP2-Uber-Max — Netflix-grade HLS proxy aggregator.

Usage:
    python3 -m src.main --config config.yaml --source ../source/Dji-you-main
    python3 -m src.main --port 9223 --host 0.0.0.0
"""
from __future__ import annotations
import argparse, asyncio, logging, sys, os
from pathlib import Path

import yaml

from m3u_loader import M3uLoader
from playlist_engine import PlaylistEngine
from proxy_server import ProxyServer


def setup_logging(cfg: dict) -> None:
    fmt = cfg.get("format", "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    level = cfg.get("level", "INFO")
    log_file = cfg.get("file")
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        from logging.handlers import RotatingFileHandler
        handlers.append(RotatingFileHandler(
            log_file,
            maxBytes=cfg.get("max_bytes", 10_485_760),
            backupCount=cfg.get("backup_count", 5),
        ))
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=fmt,
        handlers=handlers,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="JMP2-Uber-Max HLS Proxy")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    parser.add_argument("--source", default="../source/Dji-you-main", help="M3U source directory")
    parser.add_argument("--host", default=None, help="Bind host")
    parser.add_argument("--port", type=int, default=None, help="Bind port")
    args = parser.parse_args()

    # Load config
    with open(args.config, "r") as fh:
        config = yaml.safe_load(fh)

    setup_logging(config.get("logging", {}))
    logger = logging.getLogger("main")
    logger.info("🐸 JMP2-Uber-Max starting...")

    # Resolve source path
    src_dir = Path(args.source).resolve()
    if not src_dir.exists():
        logger.error("Source directory not found: %s", src_dir)
        sys.exit(1)

    # Load M3U files
    logger.info("Loading M3U files from %s", src_dir)
    loader = M3uLoader()
    records = loader.to_dicts(loader.load_directory(str(src_dir), "*.m3u"))
    logger.info("Loaded %d unique records", len(records))

    # Build playlist engine
    engine = PlaylistEngine()
    engine.ingest_records(records)

    # Build proxy server
    srv = ProxyServer(config)
    srv.engine = engine  # inject the loaded engine

    # Start background health checker
    asyncio.create_task(srv.background_health_check())

    host = args.host or config["server"]["host"]
    port = args.port or config["server"]["port"]

    logger.info("Serving on http://%s:%d", host, port)
    logger.info("Endpoints:")
    logger.info("  GET  /playlist.m3u8")
    logger.info("  GET  /category/{Movies|News|Sports|...}.m3u8")
    logger.info("  GET  /proxy/{encoded_url}")
    logger.info("  GET  /health")
    logger.info("  GET  /metrics")

    runner = web.AppRunner(srv.app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()

    # Run forever
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🐸 JMP2-Uber-Max stopped.")
