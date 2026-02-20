"""Audio assembler: place dubbed clips at timestamps and mix with accompaniment.

Takes the individual dubbed stems from the synthesizer and the Demucs
accompaniment track, positions each dubbed clip at its original subtitle
timestamp, and mixes them into a final audio track.

Timing precision is critical — the dubbed track must align with the
original JP audio so lip sync and scene context remain coherent.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf

from pipeline.synthesizer import SynthesizedClip

logger = logging.getLogger("animedub.assembler")

# Target sample rate for final output (standard for video)
TARGET_SAMPLE_RATE = 44100
# How much louder the voice should be relative to accompaniment (dB)
DEFAULT_VOICE_BOOST_DB = 3.0


@dataclass
class AssemblyResult:
    """Result of the audio assembly stage."""

    output_path: Path
    duration_s: float
    sample_rate: int
    clips_placed: int
    clips_time_adjusted: int  # Clips that needed speed adjustment


def assemble_audio(
    clips: list[SynthesizedClip],
    accompaniment_path: Path,
    output_path: Path,
    voice_boost_db: float = DEFAULT_VOICE_BOOST_DB,
    target_sample_rate: int = TARGET_SAMPLE_RATE,
) -> AssemblyResult:
    """Assemble dubbed clips with accompaniment into final audio track.

    For each dubbed clip:
    1. Resample to target rate if needed
    2. Time-stretch to match original subtitle duration (if too long/short)
    3. Place at the original subtitle timestamp
    4. Mix all clips together
    5. Mix with accompaniment track

    Args:
        clips: Synthesized dubbed clips with timing metadata.
        accompaniment_path: Path to Demucs accompaniment (no_vocals.wav).
        output_path: Where to save the final mixed audio.
        voice_boost_db: Boost voice volume relative to accompaniment.
        target_sample_rate: Sample rate for final output.

    Returns:
        AssemblyResult with output path and stats.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load accompaniment as the base track
    accomp_data, accomp_sr = sf.read(str(accompaniment_path), dtype="float32")
    if accomp_data.ndim > 1:
        accomp_data = np.mean(accomp_data, axis=1)

    # Resample accompaniment if needed
    if accomp_sr != target_sample_rate:
        accomp_data = _resample(accomp_data, accomp_sr, target_sample_rate)

    total_samples = len(accomp_data)
    total_duration_s = total_samples / target_sample_rate

    logger.info(
        f"Assembling {len(clips)} dubbed clips onto "
        f"{total_duration_s:.1f}s accompaniment track"
    )

    # Create the voice mix track (same length as accompaniment)
    voice_track = np.zeros(total_samples, dtype=np.float32)
    clips_placed = 0
    clips_adjusted = 0

    for clip in clips:
        entry = clip.slice.entry
        target_start_ms = entry.start_ms
        target_duration_ms = entry.end_ms - entry.start_ms

        # Load dubbed clip
        clip_data, clip_sr = sf.read(str(clip.clip_path), dtype="float32")
        if clip_data.ndim > 1:
            clip_data = np.mean(clip_data, axis=1)

        # Resample if needed
        if clip_sr != target_sample_rate:
            clip_data = _resample(clip_data, clip_sr, target_sample_rate)

        clip_samples = len(clip_data)
        clip_duration_ms = (clip_samples / target_sample_rate) * 1000

        # Time-stretch if dubbed clip is significantly different from original
        # Allow 20% tolerance before stretching
        ratio = clip_duration_ms / target_duration_ms if target_duration_ms > 0 else 1.0

        if ratio > 1.2 or ratio < 0.8:
            # Need to time-stretch to fit
            target_samples = int(target_duration_ms * target_sample_rate / 1000)
            clip_data = _time_stretch(clip_data, target_samples)
            clips_adjusted += 1
            logger.debug(
                f"  Clip {entry.original_index}: stretched "
                f"{clip_duration_ms:.0f}ms -> {target_duration_ms:.0f}ms "
                f"(ratio {ratio:.2f})"
            )

        # Calculate placement position
        start_sample = int(target_start_ms * target_sample_rate / 1000)

        # Bounds check
        end_sample = start_sample + len(clip_data)
        if start_sample >= total_samples:
            logger.warning(
                f"  Clip {entry.original_index} starts past end of track — skipping"
            )
            continue
        if end_sample > total_samples:
            clip_data = clip_data[: total_samples - start_sample]

        # Additive mix (overlap is fine — voices rarely overlap in subs)
        voice_track[start_sample : start_sample + len(clip_data)] += clip_data
        clips_placed += 1

    # Apply voice boost
    if voice_boost_db != 0:
        boost_factor = 10 ** (voice_boost_db / 20)
        voice_track *= boost_factor

    # Mix voice + accompaniment
    final_mix = accomp_data + voice_track

    # Normalize to prevent clipping
    peak = np.max(np.abs(final_mix))
    if peak > 0.95:
        final_mix = final_mix * (0.95 / peak)
        logger.info(f"Normalized output (peak was {peak:.3f})")

    # Save
    sf.write(str(output_path), final_mix, target_sample_rate)
    final_duration = len(final_mix) / target_sample_rate

    logger.info(
        f"Assembly complete: {clips_placed} clips placed "
        f"({clips_adjusted} time-adjusted), {final_duration:.1f}s output"
    )

    return AssemblyResult(
        output_path=output_path,
        duration_s=final_duration,
        sample_rate=target_sample_rate,
        clips_placed=clips_placed,
        clips_time_adjusted=clips_adjusted,
    )


def _resample(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Simple linear interpolation resampling.

    For production, this should use librosa.resample or torchaudio.
    Linear interp is sufficient for the POC.
    """
    if orig_sr == target_sr:
        return audio

    ratio = target_sr / orig_sr
    target_length = int(len(audio) * ratio)
    indices = np.linspace(0, len(audio) - 1, target_length)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)


def _time_stretch(audio: np.ndarray, target_samples: int) -> np.ndarray:
    """Simple time-stretch via resampling (changes pitch).

    For production, use phase vocoder (librosa.effects.time_stretch)
    to preserve pitch. Resampling-based stretch is adequate for POC
    to validate timing alignment.
    """
    if len(audio) == target_samples:
        return audio

    indices = np.linspace(0, len(audio) - 1, target_samples)
    return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)
