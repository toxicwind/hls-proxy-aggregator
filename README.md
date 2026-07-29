# 🐸 JMP2-Uber-Max
## Netflix-Grade HLS Proxy Aggregator & Commercial Stripper

### What This Is
A production-grade replacement for `jmp2.uk` that:
- **Consolidates** 180,000+ stream URLs from raw M3U playlists
- **Deduplicates** by channel name, keeping highest-quality URL
- **Filters** for English-language content only
- **Scores** streams by resolution (FHD > HD > SD)
- **Strips** SCTE-35 commercial markers from HLS manifests in real-time
- **Proxies** segment requests with caching
- **Serves** clean M3U8 playlists at `/playlist.m3u8`

### Architecture
```
Raw M3U files → M3uLoader → PlaylistEngine → dedup/filter/score → ProxyServer
                                    ↓
Upstream HLS ← Scte35Parser (strip ads) ← UrlValidator (health check)
```

### Quick Start
```bash
cd jmp2_uber_max
./run.sh
# Or manually:
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m src.main --source source/Dji-you-main --port 9223
```

### Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /playlist.m3u8` | Consolidated English playlist |
| `GET /category/Movies.m3u8` | Per-category playlist |
| `GET /category/News.m3u8` | News channels only |
| `GET /category/Sports.m3u8` | Sports channels only |
| `GET /proxy/{url}` | Proxy any URL with SCTE-35 stripping |
| `GET /health` | Health check |
| `GET /metrics` | Prometheus metrics |

### Modules
- `scte_parser.py` — SCTE-35 binary splice_info_section parser + manifest rewriter
- `url_validator.py` — Async concurrent URL health checker with retry
- `playlist_engine.py` — Consolidator, deduplicator, quality scorer
- `m3u_loader.py` — Streaming M3U parser with URL hashing
- `proxy_server.py` — aiohttp server with manifest caching

### Configuration
Edit `config.yaml` to adjust:
- Server bind host/port
- SCTE-35 marker detection
- URL validation timeouts
- English filter keywords
- Quality scoring tiers
- Cache TTLs

### SCTE-35 Stripping
The proxy automatically detects and removes:
- `#EXT-X-CUE-OUT` / `#EXT-X-CUE-IN` ranges
- `#EXT-X-SCTE35` binary splice commands (parsed)
- `#EXT-X-DATERANGE` planned ad breaks
- Rewrites sequence numbers to prevent player discontinuity

### License
GREY NINJA YAKUZA GRADE — For authorized security research only.
