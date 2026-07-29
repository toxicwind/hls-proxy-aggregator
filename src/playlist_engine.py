"""Playlist Engine — Consolidate, deduplicate, score, and build clean M3U8.

Reads raw M3U files, applies English filter, quality scoring, deduplication,
and emits a single consolidated manifest plus per-category manifests.
"""
from __future__ import annotations
import re, logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

logger = logging.getLogger("playlist")


@dataclass
class ChannelEntry:
    """Normalized channel/stream entry."""
    title: str
    url: str
    group: str
    category: str
    logo: str = ""
    tvg_id: str = ""
    tvg_name: str = ""
    language: str = ""
    quality_score: int = 0
    is_radio: bool = False
    source_file: str = ""


class PlaylistEngine:
    """Consolidates raw M3U data into clean, deduplicated playlists."""

    QUALITY_KEYWORDS: List[Tuple[List[str], int]] = [
        (["1080p", "fhd", "full hd", "1920x1080"], 100),
        (["720p", "hd", "high definition", "1280x720"], 70),
        (["480p", "sd", "standard", "640x480"], 40),
        (["360p", "240p", "144p", "low"], 10),
    ]

    ENGLISH_POSITIVE: Set[str] = {
        "uk", "us", "usa", "british", "american", "cnn", "bbc", "fox",
        "nbc", "abc", "cbs", "hbo", "showtime", "amc", "fx", "sky",
        "espn", "discovery", "nat geo", "history", "animal planet",
        "cartoon network", "disney", "nick", "pbs", "boomerang",
        "comedy central", "tnt", "tbs", "syfy", "sci-fi",
    }

    ENGLISH_NEGATIVE: Set[str] = {
        "espanol", "spanish", "latino", "latam", "mexico", "televisa",
        "francais", "france", "deutsch", "german", "rtl", "russkiy",
        "russia", "chinese", "china", "cctv", "arabic", "aljazeera",
        "mbc", "hindi", "india", "bollywood", "portugues", "italiano",
        "turkce", "polski", "greek", "dutch", "swedish", "norwegian",
    }

    PREFERRED_DOMAINS: List[str] = [
        "jmp2.uk", "1tv41.icu", "p2premium.club", "flixtv.uk",
        "dplatino.net", "mundo2.pro", "mundo2.vip", "ceoapps.org",
    ]

    def __init__(self):
        self.entries: List[ChannelEntry] = []

    # ------------------------------------------------------------------
    # Public: build from raw records
    # ------------------------------------------------------------------

    def ingest_records(self, records: List[dict]) -> None:
        """Ingest a list of raw dict records (from dataframe)."""
        for rec in records:
            entry = self._record_to_entry(rec)
            if entry:
                self.entries.append(entry)
        logger.info("Ingested %d entries", len(self.entries))

    def build_consolidated(self, english_only: bool = True) -> str:
        """Build a single consolidated M3U8 string."""
        filtered = self._filter_and_dedup(english_only=english_only)
        return self._render_m3u8(filtered, header="JMP2-Uber-Max Consolidated")

    def build_by_category(self, english_only: bool = True) -> Dict[str, str]:
        """Build per-category M3U8 strings."""
        filtered = self._filter_and_dedup(english_only=english_only)
        by_cat: Dict[str, List[ChannelEntry]] = {}
        for ent in filtered:
            by_cat.setdefault(ent.category, []).append(ent)
        return {
            cat: self._render_m3u8(items, header=f"JMP2-Uber-Max | {cat}")
            for cat, items in sorted(by_cat.items())
        }

    # ------------------------------------------------------------------
    # Internal: record → entry
    # ------------------------------------------------------------------

    def _record_to_entry(self, rec: dict) -> Optional[ChannelEntry]:
        url = rec.get("url", "")
        if not url or not url.startswith("http"):
            return None

        title = rec.get("title", "")
        group = rec.get("group_title", "")
        logo = rec.get("tvg_logo", "")
        tvg_id = rec.get("tvg_id", "")
        tvg_name = rec.get("tvg_name", "")
        content_type = rec.get("content_type", "")
        domain = rec.get("domain", "")

        # Detect radio
        is_radio = content_type == "audio" or "radio" in title.lower()

        # Detect category
        category = self._infer_category(title, group, is_radio)

        # Detect language
        language = self._detect_language(title, group)

        # Score quality
        quality = self._score_quality(title, domain)

        return ChannelEntry(
            title=title,
            url=url,
            group=group or category,
            category=category,
            logo=logo,
            tvg_id=tvg_id,
            tvg_name=tvg_name or title,
            language=language,
            quality_score=quality,
            is_radio=is_radio,
            source_file=rec.get("source_m3u", ""),
        )

    # ------------------------------------------------------------------
    # Internal: filtering & deduplication
    # ------------------------------------------------------------------

    def _filter_and_dedup(self, english_only: bool) -> List[ChannelEntry]:
        # Filter
        filtered = self.entries
        if english_only:
            filtered = [e for e in filtered if e.language == "en"]

        # Deduplicate by normalized title → keep highest quality
        buckets: Dict[str, List[ChannelEntry]] = {}
        for ent in filtered:
            key = self._normalize_title(ent.title)
            buckets.setdefault(key, []).append(ent)

        winners: List[ChannelEntry] = []
        for key, group in buckets.items():
            # Sort by quality desc, prefer preferred domains
            group.sort(key=lambda e: (
                e.quality_score,
                self._domain_preference(e.url),
            ), reverse=True)
            winners.append(group[0])

        # Sort by category then title
        winners.sort(key=lambda e: (e.category, e.title.lower()))
        logger.info("After dedup: %d channels", len(winners))
        return winners

    # ------------------------------------------------------------------
    # Internal: inference helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalize_title(title: str) -> str:
        """Normalize title for deduplication."""
        t = title.lower()
        # Strip quality suffixes
        t = re.sub(r"\s*\(?\d{3,4}p\)?\s*", " ", t)
        t = re.sub(r"\s*\(fhd|hd|sd|uhd\)\s*", " ", t, flags=re.I)
        # Strip common prefixes
        t = re.sub(r"^(uk\s*\||us\s*\||ca\s*\||mx\s*\|)\s*", "", t)
        t = re.sub(r"^\s*la\s*\|\s*", "", t)
        t = re.sub(r"[^a-z0-9]", "", t)
        return t.strip()

    def _infer_category(self, title: str, group: str, is_radio: bool) -> str:
        t = title.lower()
        g = group.lower()

        if is_radio:
            return "Radio"

        if any(x in t for x in ["movie", "film", "cinema", "hbo", "showtime", "starz"]):
            return "Movies"
        if any(x in t for x in ["news", "cnn", "bbc", "fox news", "msnbc", "aljazeera", "sky news", "bloomberg", "cnbc"]):
            return "News"
        if any(x in t for x in ["sport", "espn", "sky sport", "bt sport", "bein sport", "fox sport", "nba", "nfl", "ufc", "wwe", "mlb", "nhl", "golf", "tennis", "f1", "formula 1"]):
            return "Sports"
        if any(x in t for x in ["music", "mtv", "vh1", "bet", "mtv base", "mtv hits", "trace"]):
            return "Music"
        if any(x in t for x in ["kid", "cartoon", "nick", "disney", "pbs", "boomerang", "nick jr", "disney jr", "cbeebies"]):
            return "Kids"
        if any(x in t for x in ["doc", "discovery", "nat geo", "history", "animal planet", "science", " Investigation"]):
            return "Documentary"
        if any(x in t for x in ["adult", "xxx", "playboy", "hustler", "penthouse", "brazzers"]):
            return "Adult"
        if any(x in t for x in ["comedy", "laugh", "funny", "stand-up"]):
            return "Comedy"
        if any(x in t for x in ["horror", "scream", "terror", "fear"]):
            return "Horror"

        # Fallback to group
        if any(x in g for x in ["movie", "film", "vod", "cinema"]):
            return "Movies"
        if any(x in g for x in ["sport", "espn", "football", "soccer", "basketball", "baseball"]):
            return "Sports"
        if any(x in g for x in ["news", "information"]):
            return "News"
        if any(x in g for x in ["music", "audio"]):
            return "Music"
        if any(x in g for x in ["kid", "child", "family", "animation"]):
            return "Kids"
        if any(x in g for x in ["doc", "educational", "knowledge"]):
            return "Documentary"
        if any(x in g for x in ["adult", "xxx", "mature"]):
            return "Adult"

        return "General"

    def _detect_language(self, title: str, group: str) -> str:
        t = title.lower()
        g = group.lower()
        combined = t + " " + g

        for neg in self.ENGLISH_NEGATIVE:
            if neg in combined:
                return "other"

        for pos in self.ENGLISH_POSITIVE:
            if pos in combined:
                return "en"

        # Heuristic: if title has lots of non-ASCII, probably not English
        ascii_ratio = sum(1 for c in title if ord(c) < 128) / max(len(title), 1)
        if ascii_ratio < 0.8:
            return "other"

        # Default to English for unknown (optimistic for this use case)
        return "en"

    def _score_quality(self, title: str, domain: str) -> int:
        t = title.lower()
        score = 25  # default

        for keywords, points in self.QUALITY_KEYWORDS:
            if any(kw in t for kw in keywords):
                score = max(score, points)
                break

        # Domain bonus
        for idx, pref in enumerate(self.PREFERRED_DOMAINS):
            if pref in domain:
                score += max(0, 20 - idx * 3)
                break

        return score

    def _domain_preference(self, url: str) -> int:
        domain = urlparse(url).netloc.lower()
        for idx, pref in enumerate(self.PREFERRED_DOMAINS):
            if pref in domain:
                return idx
        return 999

    # ------------------------------------------------------------------
    # Internal: M3U8 renderer
    # ------------------------------------------------------------------

    def _render_m3u8(self, entries: List[ChannelEntry], header: str) -> str:
        lines = [
            "#EXTM3U",
            f"#PLAYLIST:{header}",
            "#EXT-X-VERSION:3",
            f"#EXT-X-PLAYLIST-TYPE:VOD",
            f"# Generated by JMP2-Uber-Max",
            f"# Total channels: {len(entries)}",
            "",
        ]

        current_group = ""
        for ent in entries:
            if ent.group != current_group:
                current_group = ent.group
                lines.append(f"## {current_group}")

            attrs = []
            if ent.tvg_id:
                attrs.append(f'tvg-id="{self._escape_attr(ent.tvg_id)}"')
            if ent.tvg_name:
                attrs.append(f'tvg-name="{self._escape_attr(ent.tvg_name)}"')
            if ent.logo:
                attrs.append(f'tvg-logo="{self._escape_attr(ent.logo)}"')
            attrs.append(f'group-title="{self._escape_attr(ent.group)}"')

            extinf = f"#EXTINF:-1 {' '.join(attrs)},{ent.title}"
            lines.append(extinf)
            lines.append(ent.url)
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _escape_attr(value: str) -> str:
        return value.replace('"', '&quot;')
