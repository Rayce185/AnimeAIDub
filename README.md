# AnimeAIDub

**AI-powered anime dubbing pipeline** — automated voice cloning and translation using existing subtitles, open-source models, and GPU acceleration.

Tdarr-style library automation for Plex/media servers.

## What It Does

1. Scans your media library for anime with Japanese audio but no EN/DE audio track
2. Uses existing subtitle files (.srt/.ass) as the translation source — no machine translation needed
3. Separates vocals from music/effects in the Japanese audio
4. Identifies speakers per subtitle line using diarization + Whisper cross-reference
5. Clones each character's voice and synthesizes translated speech
6. Remixes the new vocal track with original music/effects
7. Muxes the new audio track into the media file
8. Notifies Plex to refresh

## Model Stack

| Component | Model | License |
|-----------|-------|---------|
| Source Separation | Demucs / HTDemucs (Meta) | MIT |
| Speaker Diarization | pyannote 3.1 | MIT |
| Speech-to-Text | Whisper large-v3-turbo (OpenAI) | MIT |
| Voice Clone + TTS | CosyVoice3 0.5B (Alibaba) | Apache 2.0 |
| Audio Processing | FFmpeg | LGPL/GPL |

All models are open-source and run locally on your GPU.

## Hardware Requirements

**Minimum:** 8 GB VRAM (sequential model loading)
**Recommended:** 16+ GB VRAM (parallel stages possible)

See [docs/ROADMAP.md](docs/ROADMAP.md) for full technical specification.

## Quick Start

```bash
docker compose up -d
```

Then open `http://localhost:29100` for the Web GUI.

See [config.example.yaml](config.example.yaml) for all configuration options.

## Status

🚧 **Early development** — Pipeline architecture defined, implementation in progress.

## License

MIT
