#!/usr/bin/env python3
"""Download all pretrained models for AnimeAIDub pipeline.

Downloads to /models (or --output-dir) with progress reporting.
Safe to re-run — skips already-downloaded models.

Models:
  - Fun-CosyVoice3-0.5B-2512  (~1.5GB)  Voice cloning + TTS
  - CosyVoice-ttsfrd           (~50MB)   Text normalization (optional)
  - openai/whisper-large-v3-turbo (~3GB)  JP transcription
  - htdemucs_ft                (~300MB)  Source separation (auto-downloaded by demucs)

Usage:
    python3 scripts/download_models.py [--output-dir /models]
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("animedub.download")


def download_cosyvoice3(models_dir: Path) -> bool:
    """Download Fun-CosyVoice3-0.5B-2512 from HuggingFace."""
    target = models_dir / "Fun-CosyVoice3-0.5B"

    # Check if already downloaded (look for config file)
    if (target / "cosyvoice.yaml").exists() or (target / "config.yaml").exists():
        logger.info(f"CosyVoice3 already present at {target}")
        return True

    logger.info("Downloading Fun-CosyVoice3-0.5B-2512...")
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
            local_dir=str(target),
            local_dir_use_symlinks=False,
        )
        logger.info(f"CosyVoice3 downloaded to {target}")
        return True
    except Exception as e:
        logger.error(f"CosyVoice3 download failed: {e}")
        return False


def download_cosyvoice_ttsfrd(models_dir: Path) -> bool:
    """Download CosyVoice text normalization resource (optional)."""
    target = models_dir / "CosyVoice-ttsfrd"

    if (target / "resource").exists():
        logger.info(f"CosyVoice-ttsfrd already present at {target}")
        return True

    logger.info("Downloading CosyVoice-ttsfrd (text normalization)...")
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            "FunAudioLLM/CosyVoice-ttsfrd",
            local_dir=str(target),
            local_dir_use_symlinks=False,
        )

        # Unzip resource if present
        resource_zip = target / "resource.zip"
        if resource_zip.exists():
            import zipfile

            with zipfile.ZipFile(resource_zip, "r") as z:
                z.extractall(target)
            logger.info("Extracted resource.zip")

        logger.info(f"CosyVoice-ttsfrd downloaded to {target}")
        return True
    except Exception as e:
        logger.warning(f"CosyVoice-ttsfrd download failed (optional): {e}")
        return False


def download_whisper(models_dir: Path) -> bool:
    """Download Whisper large-v3-turbo for JP transcription."""
    cache_dir = models_dir / "whisper"
    # HF transformers caches by model hash, hard to check directly
    # Just trigger download — it's a no-op if cached
    logger.info("Downloading/verifying Whisper large-v3-turbo...")
    try:
        os.environ["HF_HOME"] = str(models_dir / "huggingface")
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor

        AutoProcessor.from_pretrained(
            "openai/whisper-large-v3-turbo",
            cache_dir=str(cache_dir),
        )
        AutoModelForSpeechSeq2Seq.from_pretrained(
            "openai/whisper-large-v3-turbo",
            cache_dir=str(cache_dir),
        )
        logger.info("Whisper large-v3-turbo ready")
        return True
    except Exception as e:
        logger.error(f"Whisper download failed: {e}")
        return False


def download_demucs(models_dir: Path) -> bool:
    """Pre-download Demucs htdemucs_ft model.

    Demucs downloads models on first use to torch hub cache.
    We trigger this to avoid download during pipeline run.
    """
    logger.info("Downloading/verifying Demucs htdemucs_ft...")
    try:
        os.environ["TORCH_HOME"] = str(models_dir / "torch")
        import torch

        torch.hub.set_dir(str(models_dir / "torch" / "hub"))
        # Import triggers model registry, actual download happens on first separation
        # We can force it by loading the model
        from demucs.pretrained import get_model

        get_model("htdemucs_ft")
        logger.info("Demucs htdemucs_ft ready")
        return True
    except Exception as e:
        logger.error(f"Demucs download failed: {e}")
        return False


def verify_gpu() -> None:
    """Log GPU status."""
    try:
        import torch

        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_mem / (1024**3)
            logger.info(f"GPU: {name} ({vram:.1f}GB VRAM)")
        else:
            logger.warning("No CUDA GPU detected — models will run on CPU")
    except ImportError:
        logger.warning("PyTorch not installed — cannot check GPU")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download AnimeAIDub models")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("/models"),
        help="Model storage directory (default: /models)",
    )
    parser.add_argument(
        "--skip-whisper",
        action="store_true",
        help="Skip Whisper download (large, ~3GB)",
    )
    args = parser.parse_args()

    start = time.time()
    logger.info("=== AnimeAIDub Model Downloader ===")
    logger.info(f"Output: {args.output_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    verify_gpu()

    results = {}

    # CosyVoice3 — required
    results["CosyVoice3"] = download_cosyvoice3(args.output_dir)

    # CosyVoice ttsfrd — optional but recommended
    results["CosyVoice-ttsfrd"] = download_cosyvoice_ttsfrd(args.output_dir)

    # Whisper — required
    if not args.skip_whisper:
        results["Whisper"] = download_whisper(args.output_dir)
    else:
        results["Whisper"] = None
        logger.info("Skipping Whisper (--skip-whisper)")

    # Demucs — required
    results["Demucs"] = download_demucs(args.output_dir)

    # Summary
    elapsed = time.time() - start
    logger.info("")
    logger.info("=== Download Summary ===")
    all_ok = True
    for name, status in results.items():
        if status is True:
            logger.info(f"  ✓ {name}")
        elif status is None:
            logger.info(f"  ⊘ {name} (skipped)")
        else:
            logger.info(f"  ✗ {name} (FAILED)")
            all_ok = False

    logger.info(f"  Elapsed: {elapsed:.0f}s")

    if not all_ok:
        logger.error("Some required models failed to download!")
        return 1

    logger.info("All models ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
