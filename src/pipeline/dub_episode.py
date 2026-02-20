"""AnimeAIDub Phase 1 CLI — single-file dubbing pipeline.

Usage:
    python -m pipeline.dub_episode \
        --input /path/to/episode.mkv \
        --output /path/to/output.mkv \
        --target-lang en \
        --models-dir /path/to/pretrained_models \
        [--device cuda] \
        [--work-dir /tmp/animedub_work]

Pipeline stages (sequential, GPU models loaded/unloaded between stages):
    1. Parse subtitles (SRT/ASS, extract from MKV or find external)
    2. Extract JP audio → WAV
    3. Demucs: separate vocals from accompaniment
    4. Slice vocals at subtitle timestamps → voice reference clips
    5. Whisper: transcribe each JP voice clip → prompt text
    6. CosyVoice3: clone voice + speak target language → dubbed stems
    7. Assemble dubbed stems + accompaniment → final audio
    8. Mux dubbed audio into MKV container
"""

import argparse
import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("animedub")


def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="AnimeAIDub — AI-powered anime dubbing pipeline"
    )
    parser.add_argument(
        "--input", "-i", type=Path, required=True,
        help="Input MKV file with JP audio and subtitles",
    )
    parser.add_argument(
        "--output", "-o", type=Path, required=True,
        help="Output MKV file with added dubbed audio track",
    )
    parser.add_argument(
        "--target-lang", "-l", default="en",
        help="Target language for dubbing (default: en)",
    )
    parser.add_argument(
        "--sub-lang", default="en",
        help="Subtitle language to use as translation source (default: en)",
    )
    parser.add_argument(
        "--models-dir", type=Path, required=True,
        help="Directory containing pretrained models (CosyVoice, etc.)",
    )
    parser.add_argument(
        "--work-dir", type=Path, default=None,
        help="Working directory for intermediate files (default: /tmp/animedub_<stem>)",
    )
    parser.add_argument(
        "--device", default="cuda", choices=["cuda", "cpu"],
        help="Device for GPU models (default: cuda)",
    )
    parser.add_argument(
        "--demucs-model", default="htdemucs_ft",
        help="Demucs model variant (default: htdemucs_ft)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--skip-mux", action="store_true",
        help="Stop after assembly (don't create final MKV)",
    )

    args = parser.parse_args()
    configure_logging(args.verbose)
    pipeline_start = time.time()

    # Validate input
    if not args.input.exists():
        logger.error(f"Input file not found: {args.input}")
        return 1

    if not args.models_dir.exists():
        logger.error(f"Models directory not found: {args.models_dir}")
        return 1

    # Set up working directory
    if args.work_dir is None:
        args.work_dir = Path(f"/tmp/animedub_{args.input.stem}")
    args.work_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"=== AnimeAIDub Phase 1 Pipeline ===")
    logger.info(f"Input:  {args.input}")
    logger.info(f"Output: {args.output}")
    logger.info(f"Target: {args.target_lang}")
    logger.info(f"Work:   {args.work_dir}")
    logger.info(f"Device: {args.device}")

    # ── Stage 1: Extract subtitles ────────────────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 1: Extract subtitles ━━━")

    from pipeline.extractor import extract_subtitles, find_external_subtitles

    sub_dir = args.work_dir / "subs"
    sub_file = extract_subtitles(args.input, sub_dir, language=args.sub_lang)

    if sub_file is None:
        # Try external
        sub_file = find_external_subtitles(args.input, args.sub_lang)

    if sub_file is None:
        logger.error(
            f"No {args.sub_lang} subtitles found (embedded or external). "
            f"Cannot proceed without translation text."
        )
        return 1

    logger.info(f"  Subtitle file: {sub_file}")

    # Parse subtitles
    from pipeline.subtitle_parser import parse_subtitles

    parse_result = parse_subtitles(sub_file)
    logger.info(f"  {parse_result.summary()}")

    if parse_result.dialogue_count == 0:
        logger.error("No dialogue lines found after filtering. Check subtitle file.")
        return 1

    logger.info(f"  Stage 1 complete ({time.time() - stage_start:.1f}s)")

    # ── Stage 2: Extract JP audio ─────────────────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 2: Extract JP audio ━━━")

    from pipeline.extractor import extract_audio_track

    audio_dir = args.work_dir / "audio"
    jp_audio = extract_audio_track(args.input, audio_dir, language="ja")
    logger.info(f"  JP audio: {jp_audio}")
    logger.info(f"  Stage 2 complete ({time.time() - stage_start:.1f}s)")

    # ── Stage 3: Source separation (Demucs) ───────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 3: Source separation (Demucs) ━━━")

    from pipeline.separator import separate_vocals

    sep_dir = args.work_dir / "separated"
    separated = separate_vocals(
        jp_audio, sep_dir, model=args.demucs_model, device=args.device
    )
    vocals_path = separated["vocals"]
    accomp_path = separated["accompaniment"]
    logger.info(f"  Vocals: {vocals_path}")
    logger.info(f"  Accompaniment: {accomp_path}")
    logger.info(f"  Stage 3 complete ({time.time() - stage_start:.1f}s)")

    # ── Stage 4: Slice vocals at timestamps ───────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 4: Slice vocals ━━━")

    from pipeline.vocal_slicer import slice_vocals

    slices_dir = args.work_dir / "slices"
    slices = slice_vocals(vocals_path, parse_result.entries, slices_dir)
    logger.info(f"  Voice reference clips: {len(slices)}")
    logger.info(f"  Stage 4 complete ({time.time() - stage_start:.1f}s)")

    if not slices:
        logger.error("No usable voice reference clips. Check audio/subtitle alignment.")
        return 1

    # ── Stage 5: Whisper transcription ────────────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 5: Whisper transcription (JP) ━━━")

    from pipeline.synthesizer import Synthesizer

    synth = Synthesizer(
        models_dir=args.models_dir,
        device=args.device,
    )
    transcriptions = synth.transcribe_all(slices)
    logger.info(f"  Transcribed: {len(transcriptions)} clips")
    logger.info(f"  Stage 5 complete ({time.time() - stage_start:.1f}s)")

    # ── Stage 6: TTS synthesis (CosyVoice3) ───────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 6: TTS synthesis (CosyVoice3) ━━━")

    dubbed_dir = args.work_dir / "dubbed"
    dubbed_clips = synth.synthesize_all(slices, transcriptions, dubbed_dir)
    logger.info(f"  Dubbed clips: {len(dubbed_clips)}")
    logger.info(f"  Stage 6 complete ({time.time() - stage_start:.1f}s)")

    if not dubbed_clips:
        logger.error("No dubbed clips generated. Check TTS model and voice references.")
        return 1

    # ── Stage 7: Audio assembly ───────────────────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 7: Audio assembly ━━━")

    from pipeline.assembler import assemble_audio

    assembled_audio = args.work_dir / "final_dubbed_audio.wav"
    assembly = assemble_audio(dubbed_clips, accomp_path, assembled_audio)
    logger.info(f"  Output: {assembly.output_path}")
    logger.info(f"  Clips placed: {assembly.clips_placed}")
    logger.info(f"  Time-adjusted: {assembly.clips_time_adjusted}")
    logger.info(f"  Duration: {assembly.duration_s:.1f}s")
    logger.info(f"  Stage 7 complete ({time.time() - stage_start:.1f}s)")

    if args.skip_mux:
        logger.info("")
        logger.info(f"=== Skipping mux (--skip-mux). Audio at: {assembled_audio} ===")
        total_time = time.time() - pipeline_start
        logger.info(f"=== Pipeline complete in {total_time:.1f}s ===")
        return 0

    # ── Stage 8: Mux into MKV ─────────────────────────────────────────
    stage_start = time.time()
    logger.info("")
    logger.info("━━━ Stage 8: Mux into MKV ━━━")

    from pipeline.muxer import mux_dubbed_audio

    lang_codes = {"en": "eng", "de": "ger", "fr": "fre", "es": "spa"}
    lang_tag = lang_codes.get(args.target_lang, args.target_lang)

    lang_names = {"en": "English", "de": "German", "fr": "French", "es": "Spanish"}
    lang_name = lang_names.get(args.target_lang, args.target_lang.upper())

    output = mux_dubbed_audio(
        source_mkv=args.input,
        dubbed_audio=assembled_audio,
        output_mkv=args.output,
        language=lang_tag,
        title=f"{lang_name} (AI Dubbed)",
        default_track=False,
        keep_original_audio=True,
    )
    logger.info(f"  Output MKV: {output}")
    logger.info(f"  Stage 8 complete ({time.time() - stage_start:.1f}s)")

    # ── Summary ───────────────────────────────────────────────────────
    total_time = time.time() - pipeline_start
    logger.info("")
    logger.info("━━━ Pipeline Summary ━━━")
    logger.info(f"  Input:       {args.input.name}")
    logger.info(f"  Output:      {args.output.name}")
    logger.info(f"  Dialogue:    {parse_result.dialogue_count} lines")
    logger.info(f"  Dubbed:      {len(dubbed_clips)} clips")
    logger.info(f"  Duration:    {assembly.duration_s:.1f}s")
    logger.info(f"  Total time:  {total_time:.1f}s")
    logger.info(f"  Work dir:    {args.work_dir}")
    logger.info("")
    logger.info("=== Done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
