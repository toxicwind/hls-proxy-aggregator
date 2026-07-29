# 🎬 HLS Proxy Aggregator

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)]()
[![GitHub Pages](https://img.shields.io/badge/GitHub%20Pages-live-brightgreen.svg)]()

> **Netflix-grade HLS proxy aggregator with real-time SCTE-35 commercial removal.**

```
┌─────────────────────────────────────────────────────────────┐
│                    HLS PROXY AGGREGATOR                     │
├─────────────────────────────────────────────────────────────┤
│  Raw M3U ──▶ Parser ──▶ Deduplicator ──▶ Quality Scorer    │
│                              │                              │
│                              ▼                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  SCTE-35 Parser (binary splice_info_section)        │  │
│  │  CUE-OUT/IN Detection ──▶ Manifest Rewrite         │  │
│  │  Sequence Number Fix ──▶ Clean M3U8 Output         │  │
│  └─────────────────────────────────────────────────────┘  │
│                              │                              │
│                              ▼                              │
│  ┌─────────────────────────────────────────────────────┐  │
│  │  Async Upstream Validator (aiohttp, 100 concurrent)│  │
│  │  Retry + Cache + Latency Tracking                   │  │
│  └─────────────────────────────────────────────────────┘  │
│                              │                              │
│                              ▼                              │
│                    /playlist.m3u8  /category/*.m3u8       │
└─────────────────────────────────────────────────────────────┘
```

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🎥 **SCTE-35 Parsing** | Binary `splice_info_section` decoder with PTS duration extraction |
| 🧹 **Commercial Removal** | Real-time CUE-OUT/IN stripping with sequence rewriting |
| ⚡ **Async Validation** | 100-concurrent URL health checks with exponential backoff |
| 🏆 **Quality Scoring** | FHD (100pts) > HD (70pts) > SD (40pts) > Low (10pts) |
| 🌍 **CDN Detection** | Akamai, CloudFront, Fastly header analysis |
| 📊 **Prometheus Metrics** | `/metrics` endpoint with request/response/latency stats |

## 🚀 Quick Start

```bash
# Clone
git clone https://github.com/toxicwind/hls-proxy-aggregator.git
cd hls-proxy-aggregator

# Install (uses Alibaba mirrors by default)
pip install -r requirements.txt

# Run
python3 -m src.main --port 9223

# Test
curl http://localhost:9223/playlist.m3u8
curl http://localhost:9223/health
```

## 📁 Structure

```
hls-proxy-aggregator/
├── src/
│   ├── main.py              # Entry point
│   ├── scte_parser.py       # SCTE-35 binary parser
│   ├── url_validator.py     # Async health checker
│   ├── playlist_engine.py   # Consolidator / deduplicator
│   ├── proxy_server.py      # aiohttp server
│   ├── m3u_loader.py        # Streaming M3U parser
│   └── db_builder.py        # JSONL DB builder
├── helpers/
│   └── auto_lint.py         # Syntax validator + auto-fixer
├── config.yaml              # Central configuration
├── requirements.txt         # Dependencies
├── run.sh                   # Auto-venv launcher
└── tests/                   # pytest suite
```

## 🔧 Configuration

Edit `config.yaml` to adjust:
- Server bind host/port
- SCTE-35 marker detection
- URL validation timeouts
- Quality scoring tiers
- Cache TTLs

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## 📜 License

MIT License — see [LICENSE](LICENSE).
