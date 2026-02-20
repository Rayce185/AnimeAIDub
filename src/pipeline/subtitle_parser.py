"""Subtitle parser for SRT and ASS/SSA formats.

Extracts dialogue entries with timestamps, filtering out non-dialogue content
like signs, typesetting, and karaoke effects common in fansubs.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("animedub.subtitle_parser")

# ASS styles that typically contain typesetting/signs, not dialogue
DEFAULT_EXCLUDED_STYLES = frozenset({
    "sign", "signs", "sign2", "sign3",
    "title", "title2",
    "op", "op1", "op2", "opening",
    "ed", "ed1", "ed2", "ending",
    "karaoke", "kara",
    "note", "notes",
    "flashback",
    "top", "top-i",
    "insert", "insert song",
    "typeset", "typesetting", "ts",
    "staff", "credit", "credits",
    "song", "lyrics",
})


@dataclass
class SubtitleEntry:
    """A single parsed subtitle/dialogue line."""

    start_ms: int  # Start time in milliseconds
    end_ms: int  # End time in milliseconds
    text: str  # Cleaned dialogue text
    style: str = ""  # ASS style name (empty for SRT)
    speaker: str = ""  # ASS Name field or detected speaker
    original_index: int = 0  # Position in the original file

    @property
    def start_seconds(self) -> float:
        return self.start_ms / 1000.0

    @property
    def end_seconds(self) -> float:
        return self.end_ms / 1000.0

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def __repr__(self) -> str:
        start = _ms_to_timestamp(self.start_ms)
        end = _ms_to_timestamp(self.end_ms)
        text_preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"SubtitleEntry({start} -> {end}, {text_preview!r})"


@dataclass
class ParseResult:
    """Result of parsing a subtitle file."""

    entries: list[SubtitleEntry] = field(default_factory=list)
    format: str = ""  # "srt" or "ass"
    total_raw_lines: int = 0  # Lines before filtering
    filtered_lines: int = 0  # Lines removed by style/dedup filtering
    styles_found: set[str] = field(default_factory=set)
    source_path: Optional[Path] = None

    @property
    def dialogue_count(self) -> int:
        return len(self.entries)

    def summary(self) -> str:
        return (
            f"Format: {self.format} | "
            f"Dialogue: {self.dialogue_count} lines | "
            f"Filtered: {self.filtered_lines} non-dialogue | "
            f"Styles: {sorted(self.styles_found) if self.styles_found else 'N/A'}"
        )


def parse_subtitles(
    path: Path,
    exclude_styles: Optional[set[str]] = None,
    min_duration_ms: int = 100,
    deduplicate: bool = True,
) -> ParseResult:
    """Parse a subtitle file (SRT or ASS/SSA).

    Args:
        path: Path to the subtitle file.
        exclude_styles: ASS styles to exclude (uses defaults if None).
        min_duration_ms: Skip entries shorter than this (catches frame-by-frame signs).
        deduplicate: Collapse sequential entries with identical text.

    Returns:
        ParseResult with filtered dialogue entries.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {path}")

    content = path.read_text(encoding="utf-8-sig")  # utf-8-sig handles BOM
    suffix = path.suffix.lower()

    if suffix in (".ass", ".ssa"):
        result = _parse_ass(content, exclude_styles)
    elif suffix == ".srt":
        result = _parse_srt(content)
    else:
        # Try to detect format from content
        if "[Script Info]" in content or "[V4+ Styles]" in content:
            result = _parse_ass(content, exclude_styles)
        elif re.search(r"^\d+\s*\n\d{2}:\d{2}:\d{2}", content, re.MULTILINE):
            result = _parse_srt(content)
        else:
            raise ValueError(f"Unsupported subtitle format: {suffix}")

    result.source_path = path

    # Filter short entries (frame-by-frame typesetting)
    pre_count = len(result.entries)
    result.entries = [e for e in result.entries if e.duration_ms >= min_duration_ms]
    result.filtered_lines += pre_count - len(result.entries)

    # Deduplicate sequential entries with same text
    if deduplicate:
        pre_count = len(result.entries)
        result.entries = _deduplicate_sequential(result.entries)
        result.filtered_lines += pre_count - len(result.entries)

    # Re-index after filtering
    for i, entry in enumerate(result.entries):
        entry.original_index = i

    logger.info(
        f"Parsed {path.name}: {result.dialogue_count} dialogue lines "
        f"({result.filtered_lines} filtered from {result.total_raw_lines} raw)"
    )
    return result


# ---------------------------------------------------------------------------
# SRT Parser
# ---------------------------------------------------------------------------

# Matches: 00:01:23,456 --> 00:01:25,789
_SRT_TIMESTAMP_RE = re.compile(
    r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})"
)


def _parse_srt(content: str) -> ParseResult:
    """Parse SRT subtitle content."""
    result = ParseResult(format="srt")
    blocks = re.split(r"\n\s*\n", content.strip())

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue

        result.total_raw_lines += 1

        # Find the timestamp line (might not be line index 1 if index is missing)
        timestamp_match = None
        text_start = 0
        for i, line in enumerate(lines):
            timestamp_match = _SRT_TIMESTAMP_RE.search(line)
            if timestamp_match:
                text_start = i + 1
                break

        if not timestamp_match or text_start >= len(lines):
            continue

        start_ms = _srt_time_to_ms(timestamp_match, offset=0)
        end_ms = _srt_time_to_ms(timestamp_match, offset=4)

        # Join remaining lines as text, strip HTML-style tags
        text = " ".join(lines[text_start:])
        text = _strip_srt_tags(text)
        text = text.strip()

        if not text:
            continue

        result.entries.append(
            SubtitleEntry(
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
            )
        )

    return result


def _srt_time_to_ms(match: re.Match, offset: int) -> int:
    """Convert SRT timestamp regex groups to milliseconds."""
    h = int(match.group(offset + 1))
    m = int(match.group(offset + 2))
    s = int(match.group(offset + 3))
    ms = int(match.group(offset + 4))
    return h * 3600000 + m * 60000 + s * 1000 + ms


def _strip_srt_tags(text: str) -> str:
    """Remove HTML-style tags from SRT text."""
    text = re.sub(r"<[^>]+>", "", text)
    return text


# ---------------------------------------------------------------------------
# ASS/SSA Parser
# ---------------------------------------------------------------------------

# Matches ASS override tags: {\tag}, {\tag(value)}, {\tag&Hvalue&}
_ASS_OVERRIDE_RE = re.compile(r"\{[^}]*\}")


def _parse_ass(content: str, exclude_styles: Optional[set[str]] = None) -> ParseResult:
    """Parse ASS/SSA subtitle content."""
    result = ParseResult(format="ass")

    if exclude_styles is None:
        excluded = DEFAULT_EXCLUDED_STYLES
    else:
        excluded = {s.lower().strip() for s in exclude_styles}

    # Parse the [Events] section
    in_events = False
    format_fields: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()

        if stripped.lower().startswith("[events]"):
            in_events = True
            continue

        if stripped.startswith("[") and in_events:
            break  # Hit next section

        if not in_events:
            continue

        # Parse Format line
        if stripped.lower().startswith("format:"):
            format_str = stripped.split(":", 1)[1]
            format_fields = [f.strip().lower() for f in format_str.split(",")]
            continue

        # Parse Dialogue lines
        if not stripped.startswith("Dialogue:"):
            continue

        result.total_raw_lines += 1

        if not format_fields:
            logger.warning("Dialogue line found before Format line — skipping")
            continue

        entry = _parse_ass_dialogue_line(stripped, format_fields, excluded, result)
        if entry:
            result.entries.append(entry)

    return result


def _parse_ass_dialogue_line(
    line: str,
    format_fields: list[str],
    excluded_styles: frozenset[str] | set[str],
    result: ParseResult,
) -> Optional[SubtitleEntry]:
    """Parse a single ASS Dialogue line into a SubtitleEntry."""
    # Strip "Dialogue: " prefix
    data = line.split(":", 1)[1].strip()

    # Split into fields — Text field (last) may contain commas, so limit splits
    parts = data.split(",", len(format_fields) - 1)
    if len(parts) < len(format_fields):
        return None

    fields = dict(zip(format_fields, parts))

    # Extract style and check exclusion
    style = fields.get("style", "").strip()
    result.styles_found.add(style)

    if style.lower() in excluded_styles:
        result.filtered_lines += 1
        return None

    # Extract timestamps
    start_str = fields.get("start", "").strip()
    end_str = fields.get("end", "").strip()
    if not start_str or not end_str:
        return None

    start_ms = _ass_time_to_ms(start_str)
    end_ms = _ass_time_to_ms(end_str)
    if start_ms is None or end_ms is None:
        return None

    # Extract speaker name
    speaker = fields.get("name", "").strip()

    # Extract and clean text
    text = fields.get("text", "").strip()
    text = _clean_ass_text(text)

    if not text:
        result.filtered_lines += 1
        return None

    return SubtitleEntry(
        start_ms=start_ms,
        end_ms=end_ms,
        text=text,
        style=style,
        speaker=speaker,
    )


def _ass_time_to_ms(time_str: str) -> Optional[int]:
    """Convert ASS timestamp (H:MM:SS.cc) to milliseconds.

    ASS uses centiseconds (1/100s), not milliseconds.
    """
    match = re.match(r"(\d+):(\d{2}):(\d{2})\.(\d{2,3})", time_str)
    if not match:
        return None

    h = int(match.group(1))
    m = int(match.group(2))
    s = int(match.group(3))
    cs_str = match.group(4)

    # Handle both centiseconds (2 digits) and milliseconds (3 digits)
    if len(cs_str) == 2:
        ms = int(cs_str) * 10
    else:
        ms = int(cs_str)

    return h * 3600000 + m * 60000 + s * 1000 + ms


def _clean_ass_text(text: str) -> str:
    """Remove ASS override tags and clean up dialogue text."""
    # Remove override blocks: {\anything}
    text = _ASS_OVERRIDE_RE.sub("", text)
    # Replace ASS line break with space
    text = text.replace("\\N", " ")
    text = text.replace("\\n", " ")
    # Remove ASS hard space
    text = text.replace("\\h", " ")
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    # Strip BOM and whitespace
    text = text.strip().strip("\ufeff")
    return text


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _deduplicate_sequential(entries: list[SubtitleEntry]) -> list[SubtitleEntry]:
    """Collapse sequential entries with identical text.

    Fansub sign typesetting often repeats the same text across many
    frame-by-frame entries. This merges them into one entry spanning
    the full time range.
    """
    if not entries:
        return []

    deduplicated: list[SubtitleEntry] = []
    current = entries[0]

    for next_entry in entries[1:]:
        # Same text and close in time (gap < 500ms)?
        if (
            next_entry.text == current.text
            and next_entry.start_ms - current.end_ms < 500
        ):
            # Extend current entry to cover both
            current = SubtitleEntry(
                start_ms=current.start_ms,
                end_ms=max(current.end_ms, next_entry.end_ms),
                text=current.text,
                style=current.style,
                speaker=current.speaker,
            )
        else:
            deduplicated.append(current)
            current = next_entry

    deduplicated.append(current)
    return deduplicated


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------


def _ms_to_timestamp(ms: int) -> str:
    """Format milliseconds as HH:MM:SS.mmm for display."""
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    rem = ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{rem:03d}"
