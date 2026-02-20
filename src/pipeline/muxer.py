"""Muxer: embed dubbed audio track into the MKV container.

Takes the assembled dubbed audio track and adds it as a new audio stream
to the original MKV file, preserving all existing streams (video, JP audio,
subtitles, etc).
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("animedub.muxer")


def mux_dubbed_audio(
    source_mkv: Path,
    dubbed_audio: Path,
    output_mkv: Path,
    language: str = "eng",
    title: str = "English (AI Dubbed)",
    default_track: bool = False,
    keep_original_audio: bool = True,
) -> Path:
    """Add dubbed audio track to MKV file.

    Uses FFmpeg to copy all existing streams and add the dubbed audio
    as a new track with appropriate metadata.

    Args:
        source_mkv: Original MKV with video + JP audio.
        dubbed_audio: Assembled dubbed WAV/AAC to add.
        output_mkv: Where to write the new MKV.
        language: Language tag for the dubbed track (ISO 639-2).
        title: Display title for the dubbed track.
        default_track: Whether to mark dubbed track as default.
        keep_original_audio: Keep all original audio tracks.

    Returns:
        Path to the output MKV.
    """
    output_mkv.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-i", str(source_mkv),
        "-i", str(dubbed_audio),
    ]

    audio_count = _count_audio_streams(source_mkv)

    if keep_original_audio:
        # Map everything from source + new audio
        cmd.extend([
            "-map", "0",          # All streams from source
            "-map", "1:a:0",      # Audio from dubbed file
            "-c:v", "copy",       # Copy video (no re-encode)
            "-c:a", "copy",       # Copy existing audio tracks
            "-c:s", "copy",       # Copy subtitles
        ])

        # Encode the new dubbed track as AAC
        # The new track is the last audio stream
        if audio_count is not None:
            cmd.extend([
                f"-c:a:{audio_count}", "aac",
                f"-b:a:{audio_count}", "192k",
            ])
        else:
            # Fallback: encode all audio as AAC (less ideal but safe)
            cmd.extend(["-c:a", "aac", "-b:a", "192k"])

        stream_idx = audio_count if audio_count is not None else 1
    else:
        # Only video + new audio
        cmd.extend([
            "-map", "0:v",
            "-map", "1:a:0",
            "-map", "0:s?",       # Subtitles if present
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-c:s", "copy",
        ])
        stream_idx = 0

    cmd.extend([
        f"-metadata:s:a:{stream_idx}", f"language={language}",
        f"-metadata:s:a:{stream_idx}", f"title={title}",
    ])

    if default_track:
        # Set disposition: default on dubbed, remove default from others
        cmd.extend([
            f"-disposition:a:{stream_idx}", "default",
        ])
        for i in range(stream_idx):
            cmd.extend([f"-disposition:a:{i}", "0"])

    cmd.extend([
        "-y",
        str(output_mkv),
    ])

    logger.info(f"Muxing dubbed audio into: {output_mkv.name}")
    logger.debug(f"  Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg mux failed: {result.stderr[-500:]}")

    if not output_mkv.exists():
        raise FileNotFoundError(f"Expected output not created: {output_mkv}")

    logger.info(f"Mux complete: {output_mkv.name}")
    return output_mkv


def _count_audio_streams(media_path: Path) -> Optional[int]:
    """Count audio streams in a media file."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-select_streams", "a",
        "-show_entries", "stream=index",
        "-of", "csv=p=0",
        str(media_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        logger.warning(f"Could not probe audio streams: {result.stderr}")
        return None

    lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
    return len(lines)
