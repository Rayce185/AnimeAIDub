"""Stage 1: Extract audio and subtitles from media files using FFmpeg."""

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("animedub.extractor")


def extract_audio_track(
    media_path: Path,
    output_path: Path,
    language: str = "ja",
    track_index: Optional[int] = None,
) -> Path:
    """Extract a specific audio track from a media file."""
    output_path.mkdir(parents=True, exist_ok=True)
    audio_file = output_path / f"{media_path.stem}_audio_{language}.wav"

    probe = probe_media(media_path)

    if track_index is not None:
        stream_spec = f"0:a:{track_index}"
    else:
        stream_spec = find_audio_stream(probe, language)
        if stream_spec is None:
            raise ValueError(f"No audio track with language '{language}' found in {media_path}")

    cmd = [
        "ffmpeg", "-i", str(media_path),
        "-map", stream_spec,
        "-acodec", "pcm_s16le",
        "-ar", "44100",
        "-ac", "2",
        "-y",
        str(audio_file)
    ]

    logger.info(f"Extracting audio: {media_path.name} -> {audio_file.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")

    return audio_file


def extract_subtitles(
    media_path: Path,
    output_path: Path,
    language: str = "en",
) -> Optional[Path]:
    """Extract subtitle track from media file."""
    output_path.mkdir(parents=True, exist_ok=True)

    probe = probe_media(media_path)
    stream_spec = find_subtitle_stream(probe, language)

    if stream_spec is None:
        logger.warning(f"No embedded {language} subtitles in {media_path.name}")
        return find_external_subtitles(media_path, language)

    # Detect subtitle codec to preserve native format (ASS style metadata matters)
    sub_ext = _detect_subtitle_extension(probe, language)
    sub_file = output_path / f"{media_path.stem}_subs_{language}{sub_ext}"

    cmd = [
        "ffmpeg", "-i", str(media_path),
        "-map", stream_spec,
        "-c:s", "copy",  # Copy subtitle stream without transcoding
        "-y",
        str(sub_file)
    ]

    logger.info(f"Extracting subtitles: {media_path.name} -> {sub_file.name}")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error(f"FFmpeg subtitle extraction failed: {result.stderr}")
        return None

    return sub_file


def probe_media(media_path: Path) -> dict:
    """Probe media file for stream information."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(media_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        raise RuntimeError(f"FFprobe failed: {result.stderr}")

    return json.loads(result.stdout)


def find_audio_stream(probe: dict, language: str) -> Optional[str]:
    """Find audio stream index by language tag."""
    audio_idx = 0
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "audio":
            tags = stream.get("tags", {})
            if tags.get("language", "").startswith(language):
                return f"0:a:{audio_idx}"
            audio_idx += 1
    return None


def find_subtitle_stream(probe: dict, language: str) -> Optional[str]:
    """Find subtitle stream index by language tag."""
    sub_idx = 0
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "subtitle":
            tags = stream.get("tags", {})
            if tags.get("language", "").startswith(language):
                return f"0:s:{sub_idx}"
            sub_idx += 1
    return None


def find_external_subtitles(media_path: Path, language: str) -> Optional[Path]:
    """Look for external subtitle files matching the media file."""
    stem = media_path.stem
    parent = media_path.parent

    patterns = [
        f"{stem}.{language}.srt",
        f"{stem}.{language}.ass",
        f"{stem}.{language}.ssa",
        f"{stem}.srt",
    ]

    for pattern in patterns:
        candidate = parent / pattern
        if candidate.exists():
            logger.info(f"Found external subtitles: {candidate.name}")
            return candidate

    return None


def _detect_subtitle_extension(probe: dict, language: str) -> str:
    """Detect subtitle codec and return appropriate file extension.

    ASS/SSA codecs need to stay as .ass to preserve style metadata
    (used for filtering signs, typesetting, karaoke, etc).
    """
    for stream in probe.get("streams", []):
        if stream.get("codec_type") != "subtitle":
            continue
        tags = stream.get("tags", {})
        if not tags.get("language", "").startswith(language):
            continue

        codec = stream.get("codec_name", "").lower()
        if codec in ("ass", "ssa"):
            return ".ass"
        elif codec == "subrip":
            return ".srt"
        elif codec == "webvtt":
            return ".vtt"

    # Default to .srt
    return ".srt"
