# AnimeAIDub — AI-Powered Anime Dubbing Pipeline

## Project Roadmap & Technical Specification

**Version:** 0.1 (Draft)
**Date:** 2026-02-18
**Author:** Ray DiRenzo + Claude (Anthropic)
**Status:** Planning

---

## 1. PROJECT VISION

A self-hosted, automated dubbing pipeline that:

1. Scans a media library for anime with Japanese audio but no EN/DE audio track
2. Uses existing subtitle files (.srt/.ass) as the translation source — no machine translation needed
3. Separates vocals from music/effects in the Japanese audio
4. Identifies speakers per subtitle line using diarization + Whisper cross-reference
5. Clones each character's voice and synthesizes translated speech
6. Remixes new vocal track with original music/effects layer
7. Muxes the new audio track into the media file
8. Notifies the media server (Plex) to refresh

**Target:** Tdarr-style library automation — scan, process, done.

---

## 2. PIPELINE ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                      LIBRARY SCANNER                            │
│  Monitor media folders → detect JP-only anime → queue jobs      │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1: EXTRACT                                               │
│  FFmpeg → extract JP audio track + subtitle file (.srt/.ass)    │
│  Parse subtitle file → get text + timestamps per line           │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2: SEPARATE                                              │
│  Demucs/HTDemucs → split audio into:                            │
│    - Vocals track (speech only)                                 │
│    - Accompaniment track (music + effects)                      │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3: IDENTIFY SPEAKERS                                     │
│  pyannote speaker-diarization-3.1 → cluster speaker segments    │
│  Whisper (cross-reference) → rough JP transcription             │
│  Match: subtitle timestamp ↔ diarization segment ↔ speaker ID   │
│  Build per-series voice profile database                        │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 4: VOICE CLONE + TTS                                     │
│  For each subtitle line:                                        │
│    - Select speaker's Japanese voice sample (from Stage 2+3)    │
│    - Feed subtitle text (EN/DE) + voice reference               │
│    - TTS model generates speech in target language               │
│    - Preserve: pitch, tone, emotion, speaking speed             │
│  Output: individual audio clips per subtitle line               │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 5: REMIX + MUX                                           │
│  - Place generated clips at subtitle timestamps                 │
│  - Mix with accompaniment track (music + effects)               │
│  - Normalize audio levels                                       │
│  - FFmpeg → mux new audio track into media file                 │
│  - Preserve original JP track + subtitles                       │
└─────────────┬───────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 6: FINALIZE                                              │
│  - Tag new track (language, "AI-Dubbed" label)                  │
│  - Trigger Plex library scan                                    │
│  - Log result + update series voice profile DB                  │
│  - Move to next queued item                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. MODEL STACK

All models are open-source and available on Hugging Face or via pip/GitHub.

### 3.1 Audio Source Separation — Demucs / HTDemucs

| Property | Value |
|----------|-------|
| Source | `pip install demucs` (Meta/Facebook Research) |
| Model | `htdemucs_ft` (fine-tuned, best quality) |
| VRAM | ~2-4 GB |
| Speed | ~1-2x realtime on GPU |
| License | MIT |
| Purpose | Separate vocals from music/effects/other |

### 3.2 Speaker Diarization — pyannote

| Property | Value |
|----------|-------|
| HF Repo | [pyannote/speaker-diarization-3.1](https://hf.co/pyannote/speaker-diarization-3.1) |
| VRAM | ~1-2 GB |
| License | MIT |
| Purpose | Cluster audio segments by speaker identity |

### 3.3 Speech-to-Text (Cross-Reference Only) — Whisper

| Property | Value |
|----------|-------|
| HF Repo | [openai/whisper-large-v3-turbo](https://hf.co/openai/whisper-large-v3-turbo) |
| VRAM | ~6 GB (turbo) / ~10 GB (full large-v3) |
| License | MIT |
| Purpose | Rough JP transcription to match subtitle lines to speaker clusters |

### 3.4 Voice Cloning + TTS — Primary: CosyVoice 3

| Property | Value |
|----------|-------|
| HF Repo | [FunAudioLLM/Fun-CosyVoice3-0.5B-2512](https://hf.co/FunAudioLLM/Fun-CosyVoice3-0.5B-2512) |
| Languages | ZH, EN, FR, ES, **JA**, KO, IT, RU, **DE** |
| VRAM | ~2-4 GB |
| License | Apache 2.0 |
| Key Feature | Zero-shot voice cloning, emotion preservation, streaming support |

**Alternatives:** Fish Speech S1-mini (CC-BY-NC-SA-4.0, better quality), GPT-SoVITS (MIT, popular in anime community)

### 3.5 Audio Processing — FFmpeg

Standard system package for audio extraction, muxing, and normalization.

---

## 4. HARDWARE REQUIREMENTS

### 4.1 VRAM Budget Per Stage (Sequential)

| Stage | Model | Peak VRAM |
|-------|-------|-----------|
| Separation | HTDemucs | ~3 GB |
| Diarization | pyannote 3.1 | ~2 GB |
| Cross-ref STT | Whisper turbo | ~6 GB |
| Voice Clone+TTS | CosyVoice3 0.5B | ~4 GB |
| Remix/Mux | FFmpeg (CPU) | 0 GB |
| **Peak (any single stage)** | | **~6 GB** |

### 4.2 Processing Time Estimates (P100 16GB)

| Stage | 24-min episode estimate |
|-------|------------------------|
| Extract (FFmpeg) | ~10 seconds |
| Separate (Demucs) | ~5-8 minutes |
| Diarize (pyannote) | ~2-3 minutes |
| Whisper cross-ref | ~3-5 minutes |
| TTS generation (~300 lines) | ~15-25 minutes |
| Remix + Mux | ~1-2 minutes |
| **Total per episode** | **~30-45 minutes** |

A 12-episode season: roughly 6-9 hours unattended.

---

## 5. SOFTWARE STACK

### 5.1 Docker Container — FULLY STANDALONE

100% self-contained. No external dependencies on Ollama, LiteLLM, or any other container. All AI models run inside this single container.

### 5.2 Web GUI

Dashboard, library browser, settings, voice profile manager, real-time progress via WebSocket. FastAPI backend + React/Vue frontend.

### 5.3 Configuration

YAML-based config with scanner paths, detection rules, model selection, output settings, and Plex integration.

---

## 6. DEVELOPMENT ROADMAP

- **Phase 0:** Repository Setup (1 day)
- **Phase 1:** Proof of Concept — Single File CLI (2-4 weeks)
- **Phase 2:** Voice Profile Persistence (1-2 weeks)
- **Phase 3:** Web GUI — Core (3-4 weeks)
- **Phase 4:** Standalone Docker Packaging (2-3 weeks)
- **Phase 5:** Library Scanner + Automation (2-3 weeks)
- **Phase 6:** Quality Improvements (ongoing)
- **Phase 7:** Community & Distribution (ongoing)
- **Phase 8:** Desktop Application (optional, 4-6 weeks)

See full roadmap details in the [complete specification](../../AnimeAIDub-Roadmap.md).

---

## 7. LICENSING

| Component | License | Commercial Use? |
|-----------|---------|-----------------|
| Demucs (Meta) | MIT | Yes |
| pyannote 3.1 | MIT | Yes |
| Whisper (OpenAI) | MIT | Yes |
| CosyVoice3 (Alibaba) | Apache 2.0 | Yes |
| Fish Speech S1-mini | CC-BY-NC-SA-4.0 | Non-commercial only |
| GPT-SoVITS | MIT | Yes |
| FFmpeg | LGPL/GPL | Yes (with compliance) |

---

*This document is a living roadmap. Updated as development progresses.*
