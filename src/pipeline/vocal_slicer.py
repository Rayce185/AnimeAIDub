"""Vocal slicer: extract voice reference clips from separated vocals.

Slices the Demucs-separated vocal track at subtitle timestamps to produce
individual voice reference clips for TTS voice cloning.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from pipeline.subtitle_parser import SubtitleEntry

logger = logging.getLogger("animedub.vocal_slicer")

# Minimum clip duration for usable voice reference (CosyVoice recommends 3-10s)
MIN_REFERENCE_DURATION_S = 0.5
# Padding around subtitle timestamps to capture full utterance
PAD_BEFORE_MS = 200
PAD_AFTER_MS = 300


@dataclass
class VocalSlice:
    """A sliced vocal clip with metadata."""

    entry: SubtitleEntry  # The subtitle entry this clip corresponds to
    clip_path: Path  # Path to the saved WAV clip
    duration_s: float  # Actual clip duration in seconds
    sample_rate: int


def slice_vocals(
    vocals_path: Path,
    entries: list[SubtitleEntry],
    output_dir: Path,
    pad_before_ms: int = PAD_BEFORE_MS,
    pad_after_ms: int = PAD_AFTER_MS,
) -> list[VocalSlice]:
    """Slice vocal track at subtitle timestamps.

    For each subtitle entry, extracts the corresponding vocal segment
    with optional padding. Each slice becomes a voice reference for TTS.

    Args:
        vocals_path: Path to Demucs-separated vocals WAV.
        entries: Parsed subtitle entries with timestamps.
        output_dir: Directory to save individual clips.
        pad_before_ms: Milliseconds of padding before subtitle start.
        pad_after_ms: Milliseconds of padding after subtitle end.

    Returns:
        List of VocalSlice objects with paths to saved clips.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    audio_data, sample_rate = sf.read(vocals_path, dtype="float32")
    total_samples = len(audio_data)
    total_duration_s = total_samples / sample_rate

    logger.info(
        f"Slicing {len(entries)} entries from vocals "
        f"({total_duration_s:.1f}s, {sample_rate}Hz)"
    )

    # If stereo, convert to mono for voice reference
    if audio_data.ndim > 1:
        audio_data = np.mean(audio_data, axis=1)

    slices: list[VocalSlice] = []
    skipped = 0

    for i, entry in enumerate(entries):
        # Calculate sample range with padding
        start_ms = max(0, entry.start_ms - pad_before_ms)
        end_ms = min(int(total_duration_s * 1000), entry.end_ms + pad_after_ms)

        start_sample = int(start_ms * sample_rate / 1000)
        end_sample = int(end_ms * sample_rate / 1000)

        # Clamp to valid range
        start_sample = max(0, min(start_sample, total_samples - 1))
        end_sample = max(start_sample + 1, min(end_sample, total_samples))

        clip = audio_data[start_sample:end_sample]
        duration_s = len(clip) / sample_rate

        # Skip clips too short for voice reference
        if duration_s < MIN_REFERENCE_DURATION_S:
            logger.debug(
                f"  Skipping entry {i} ({duration_s:.2f}s < {MIN_REFERENCE_DURATION_S}s)"
            )
            skipped += 1
            continue

        # Check if clip has meaningful audio (not silence)
        rms = np.sqrt(np.mean(clip**2))
        if rms < 1e-4:
            logger.debug(f"  Skipping entry {i} (silence, RMS={rms:.6f})")
            skipped += 1
            continue

        # Save clip
        clip_path = output_dir / f"voice_{i:04d}.wav"
        sf.write(str(clip_path), clip, sample_rate)

        slices.append(
            VocalSlice(
                entry=entry,
                clip_path=clip_path,
                duration_s=duration_s,
                sample_rate=sample_rate,
            )
        )

    logger.info(
        f"Sliced {len(slices)} voice references "
        f"({skipped} skipped — too short or silent)"
    )
    return slices
