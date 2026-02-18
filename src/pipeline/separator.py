"""Stage 2: Audio source separation using Demucs.

Separates vocals from music/effects to get clean speech.
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("animedub.separator")


def separate_vocals(
    audio_path: Path,
    output_dir: Path,
    model: str = "htdemucs_ft",
    device: str = "cuda",
) -> dict[str, Path]:
    """Separate vocals from accompaniment using Demucs."""
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3", "-m", "demucs",
        "--two-stems", "vocals",
        "-n", model,
        "--device", device,
        "-o", str(output_dir),
        str(audio_path)
    ]

    logger.info(f"Separating vocals: {audio_path.name} (model: {model})")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    if result.returncode != 0:
        raise RuntimeError(f"Demucs separation failed: {result.stderr}")

    stem = audio_path.stem
    base = output_dir / model / stem

    vocals_path = base / "vocals.wav"
    accompaniment_path = base / "no_vocals.wav"

    if not vocals_path.exists():
        raise FileNotFoundError(f"Expected vocals output not found: {vocals_path}")

    logger.info("Vocal separation complete")
    return {
        "vocals": vocals_path,
        "accompaniment": accompaniment_path,
    }
