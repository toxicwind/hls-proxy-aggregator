#!/usr/bin/env python3
"""
scte_parser.py — SCTE-35 commercial detection and removal from HLS manifests.
"""
import re, base64
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

@dataclass
class CueRange:
    start_line: int
    end_line: int
    duration_sec: float = 0.0
    splice_type: str = "cue"
    raw_tags: List[str] = field(default_factory=list)

class Scte35Parser:
    CUE_OUT_RE = re.compile(r"#EXT-X-CUE-OUT(?::([\d.]+))?")
    CUE_IN_RE = re.compile(r"#EXT-X-CUE-IN")
    CUE_OUT_CONT_RE = re.compile(r"#EXT-X-CUE-OUT-CONT(?::([\d.]+)/([\d.]+))?")
    SCTE35_RE = re.compile(r"#EXT-X-SCTE35:.*?CUE=\"([A-Za-z0-9+/=]+)\"" )
    DATERANGE_RE = re.compile(
        r"#EXT-X-DATERANGE:.*?ID=\"([^\"]+)\".*?START-DATE=\"([^\"]+)\""
        r"(?:.*?DURATION=\"([\d.]+)\")?"
        r"(?:.*?PLANNED-DURATION=\"([\d.]+)\")?"
    )

    def __init__(self, min_ad_sec=5.0, max_ad_sec=300.0):
        self.min_ad_sec = min_ad_sec
        self.max_ad_sec = max_ad_sec

    def strip_manifest(self, manifest_text: str) -> Tuple[str, List[CueRange]]:
        lines = manifest_text.splitlines()
        cue_ranges = self._detect_ranges(lines)
        if not cue_ranges:
            return manifest_text, []
        clean_lines = self._rewrite(lines, cue_ranges)
        return "\n".join(clean_lines) + "\n", cue_ranges

    def _detect_ranges(self, lines: List[str]) -> List[CueRange]:
        ranges = []
        in_break = False
        start_idx = -1
        duration = 0.0
        raw_tags = []

        for idx, line in enumerate(lines):
            m = self.CUE_OUT_RE.match(line)
            if m:
                in_break = True
                start_idx = idx
                duration = float(m.group(1)) if m.group(1) else 0.0
                raw_tags = [line]
                continue

            m2 = self.CUE_OUT_CONT_RE.match(line)
            if m2 and in_break:
                raw_tags.append(line)
                continue

            m3 = self.SCTE35_RE.search(line)
            if m3 and in_break:
                raw_tags.append(line)
                continue

            m4 = self.DATERANGE_RE.match(line)
            if m4 and not in_break:
                planned = m4.group(4)
                actual = m4.group(3)
                dur = float(planned) if planned else (float(actual) if actual else 0.0)
                if dur > 0:
                    in_break = True
                    start_idx = idx
                    duration = dur
                    raw_tags = [line]
                continue

            if self.CUE_IN_RE.match(line):
                if in_break and start_idx >= 0:
                    if self.min_ad_sec <= duration <= self.max_ad_sec:
                        ranges.append(CueRange(
                            start_line=start_idx, end_line=idx,
                            duration_sec=duration, splice_type="cue",
                            raw_tags=raw_tags.copy()
                        ))
                    in_break = False
                    start_idx = -1
                    duration = 0.0
                    raw_tags = []
                continue

        return ranges

    def _rewrite(self, lines: List[str], ranges: List[CueRange]) -> List[str]:
        drop = set()
        for r in ranges:
            for i in range(r.start_line, r.end_line + 1):
                drop.add(i)
        clean = [line for idx, line in enumerate(lines) if idx not in drop]
        clean = self._fix_discontinuity(clean)
        clean = self._fix_media_sequence(clean)
        return clean

    @staticmethod
    def _fix_discontinuity(lines: List[str]) -> List[str]:
        out = []
        disc_seq = 0
        for line in lines:
            if line.startswith("#EXT-X-DISCONTINUITY-SEQUENCE:"):
                out.append(f"#EXT-X-DISCONTINUITY-SEQUENCE:{disc_seq}")
                disc_seq += 1
            else:
                out.append(line)
        return out

    @staticmethod
    def _fix_media_sequence(lines: List[str]) -> List[str]:
        out = []
        for line in lines:
            if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                try:
                    base = int(line.split(":", 1)[1])
                    out.append(f"#EXT-X-MEDIA-SEQUENCE:{base}")
                except ValueError:
                    out.append(line)
            else:
                out.append(line)
        return out
