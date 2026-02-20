"""Synthesizer: voice-cloned TTS generation for dubbed audio.

For each subtitle line:
1. Whisper transcribes the JP vocal slice → prompt text
2. CosyVoice3 clones the voice and speaks the target language text
3. Output is time-stretched if needed to fit subtitle duration

Models are loaded/unloaded sequentially to conserve VRAM.
"""

import gc
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import soundfile as sf
import torch
import torchaudio

from pipeline.vocal_slicer import VocalSlice

logger = logging.getLogger("animedub.synthesizer")

# Whisper config
WHISPER_MODEL = "openai/whisper-large-v3-turbo"
WHISPER_LANGUAGE = "ja"

# CosyVoice config
COSYVOICE_MODEL_DIR = "pretrained_models/Fun-CosyVoice3-0.5B"
COSYVOICE_DEFAULT_PROMPT = "You are a helpful assistant.<|endofprompt|>"


@dataclass
class SynthesizedClip:
    """A synthesized dubbed audio clip."""

    slice: VocalSlice  # Original vocal slice this was generated from
    clip_path: Path  # Path to the generated WAV
    target_text: str  # Text that was spoken
    prompt_text: str  # Whisper transcription of JP reference
    duration_s: float  # Duration of generated audio
    sample_rate: int


class Synthesizer:
    """Manages Whisper + CosyVoice3 for dubbed audio generation.

    Models are loaded lazily and unloaded between stages to
    stay within VRAM limits (sequential loading pattern).
    """

    def __init__(
        self,
        models_dir: Path,
        device: str = "cuda",
        whisper_model: str = WHISPER_MODEL,
        cosyvoice_model_dir: Optional[str] = None,
    ):
        self.models_dir = Path(models_dir)
        self.device = device
        self.whisper_model_name = whisper_model
        self.cosyvoice_model_dir = cosyvoice_model_dir or str(
            self.models_dir / "Fun-CosyVoice3-0.5B"
        )

        self._whisper_model = None
        self._whisper_processor = None
        self._cosyvoice = None

    # ------------------------------------------------------------------
    # Whisper: transcribe JP vocal slices
    # ------------------------------------------------------------------

    def _load_whisper(self) -> None:
        """Load Whisper model for JP transcription."""
        if self._whisper_model is not None:
            return

        logger.info(f"Loading Whisper model: {self.whisper_model_name}")
        from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline

        self._whisper_processor = AutoProcessor.from_pretrained(
            self.whisper_model_name,
            cache_dir=str(self.models_dir / "whisper"),
        )
        self._whisper_model = AutoModelForSpeechSeq2Seq.from_pretrained(
            self.whisper_model_name,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            cache_dir=str(self.models_dir / "whisper"),
        ).to(self.device)

        self._whisper_pipe = pipeline(
            "automatic-speech-recognition",
            model=self._whisper_model,
            tokenizer=self._whisper_processor.tokenizer,
            feature_extractor=self._whisper_processor.feature_extractor,
            torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
            device=self.device,
        )
        logger.info("Whisper loaded")

    def _unload_whisper(self) -> None:
        """Unload Whisper to free VRAM."""
        if self._whisper_model is None:
            return
        logger.info("Unloading Whisper")
        del self._whisper_pipe
        del self._whisper_model
        del self._whisper_processor
        self._whisper_pipe = None
        self._whisper_model = None
        self._whisper_processor = None
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        logger.info("Whisper unloaded")

    def transcribe_slice(self, audio_path: Path) -> str:
        """Transcribe a single audio clip with Whisper.

        Returns the Japanese transcription text.
        """
        self._load_whisper()
        result = self._whisper_pipe(
            str(audio_path),
            generate_kwargs={"language": WHISPER_LANGUAGE, "task": "transcribe"},
            return_timestamps=False,
        )
        text = result.get("text", "").strip()
        return text

    def transcribe_all(self, slices: list[VocalSlice]) -> dict[int, str]:
        """Batch transcribe all vocal slices with Whisper.

        Returns dict mapping entry index → JP transcription.
        Loads Whisper once, processes all, then unloads.
        """
        logger.info(f"Transcribing {len(slices)} vocal slices with Whisper")
        self._load_whisper()

        transcriptions: dict[int, str] = {}
        for i, vs in enumerate(slices):
            text = self.transcribe_slice(vs.clip_path)
            transcriptions[vs.entry.original_index] = text
            if (i + 1) % 10 == 0:
                logger.info(f"  Transcribed {i + 1}/{len(slices)}")

        self._unload_whisper()
        logger.info(f"Transcription complete: {len(transcriptions)} entries")
        return transcriptions

    # ------------------------------------------------------------------
    # CosyVoice3: voice cloning + TTS
    # ------------------------------------------------------------------

    def _load_cosyvoice(self) -> None:
        """Load CosyVoice3 model."""
        if self._cosyvoice is not None:
            return

        import sys

        # CosyVoice requires its third_party/Matcha-TTS in path
        cosyvoice_root = self.models_dir.parent  # assumes models_dir is inside CosyVoice repo
        matcha_path = cosyvoice_root / "third_party" / "Matcha-TTS"
        if matcha_path.exists() and str(matcha_path) not in sys.path:
            sys.path.insert(0, str(matcha_path))

        logger.info(f"Loading CosyVoice3 from: {self.cosyvoice_model_dir}")
        from cosyvoice.cli.cosyvoice import AutoModel

        self._cosyvoice = AutoModel(
            model_dir=self.cosyvoice_model_dir,
        )
        logger.info("CosyVoice3 loaded")

    def _unload_cosyvoice(self) -> None:
        """Unload CosyVoice3 to free VRAM."""
        if self._cosyvoice is None:
            return
        logger.info("Unloading CosyVoice3")
        del self._cosyvoice
        self._cosyvoice = None
        gc.collect()
        if self.device == "cuda":
            torch.cuda.empty_cache()
        logger.info("CosyVoice3 unloaded")

    def synthesize_clip(
        self,
        text: str,
        prompt_text: str,
        reference_audio: Path,
        output_path: Path,
    ) -> Optional[Path]:
        """Generate one dubbed audio clip via CosyVoice3 zero-shot.

        Args:
            text: Target language text to speak (EN/DE).
            prompt_text: What's spoken in the reference (JP transcript from Whisper).
            reference_audio: Path to JP vocal slice for voice cloning.
            output_path: Where to save the generated clip.

        Returns:
            Path to generated WAV, or None on failure.
        """
        self._load_cosyvoice()

        # Format prompt text per CosyVoice3 convention
        formatted_prompt = f"{COSYVOICE_DEFAULT_PROMPT}{prompt_text}"

        try:
            chunks = []
            for chunk in self._cosyvoice.inference_zero_shot(
                text,
                formatted_prompt,
                str(reference_audio),
                stream=False,
            ):
                chunks.append(chunk["tts_speech"])

            if not chunks:
                logger.warning(f"CosyVoice3 returned no audio for: {text[:50]}")
                return None

            # Concatenate chunks and save
            audio = torch.cat(chunks, dim=-1)
            torchaudio.save(
                str(output_path),
                audio,
                self._cosyvoice.sample_rate,
            )
            return output_path

        except Exception as e:
            logger.error(f"TTS failed for '{text[:50]}...': {e}")
            return None

    # ------------------------------------------------------------------
    # Full synthesis pipeline
    # ------------------------------------------------------------------

    def synthesize_all(
        self,
        slices: list[VocalSlice],
        transcriptions: dict[int, str],
        output_dir: Path,
    ) -> list[SynthesizedClip]:
        """Generate dubbed audio for all subtitle entries.

        1. Load CosyVoice3
        2. For each slice: generate dubbed clip using voice reference + EN text
        3. Unload CosyVoice3

        Args:
            slices: Vocal slices with voice references.
            transcriptions: JP transcriptions from Whisper (index → text).
            output_dir: Directory for generated clips.

        Returns:
            List of SynthesizedClip with paths to generated audio.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Synthesizing {len(slices)} clips with CosyVoice3")

        self._load_cosyvoice()
        results: list[SynthesizedClip] = []
        failed = 0

        for i, vs in enumerate(slices):
            idx = vs.entry.original_index
            prompt_text = transcriptions.get(idx, "")
            target_text = vs.entry.text

            if not target_text.strip():
                logger.debug(f"  Skipping entry {idx}: empty target text")
                continue

            clip_path = output_dir / f"dubbed_{idx:04d}.wav"

            result = self.synthesize_clip(
                text=target_text,
                prompt_text=prompt_text,
                reference_audio=vs.clip_path,
                output_path=clip_path,
            )

            if result and result.exists():
                info = sf.info(str(result))
                results.append(
                    SynthesizedClip(
                        slice=vs,
                        clip_path=result,
                        target_text=target_text,
                        prompt_text=prompt_text,
                        duration_s=info.duration,
                        sample_rate=info.samplerate,
                    )
                )
            else:
                failed += 1

            if (i + 1) % 10 == 0:
                logger.info(f"  Synthesized {i + 1}/{len(slices)} ({failed} failed)")

        self._unload_cosyvoice()
        logger.info(
            f"Synthesis complete: {len(results)} clips generated, {failed} failed"
        )
        return results
