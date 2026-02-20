FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

LABEL maintainer="Ray DiRenzo"
LABEL description="AnimeAIDub - AI-powered anime dubbing pipeline"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# ── System dependencies ───────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-dev \
    python3.10-venv \
    python3-pip \
    ffmpeg \
    sox \
    libsox-dev \
    git \
    git-lfs \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/* \
    && update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1 \
    && python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel

# ── Clone CosyVoice repo (for library code + Matcha-TTS submodule) ────
WORKDIR /opt
RUN git clone --recursive https://github.com/FunAudioLLM/CosyVoice.git \
    && cd CosyVoice \
    && git submodule update --init --recursive

# ── Install PyTorch with CUDA 12.4 (P100 compute 6.0 compatible) ─────
RUN pip3 install --no-cache-dir \
    torch==2.4.0+cu124 \
    torchaudio==2.4.0+cu124 \
    --extra-index-url https://download.pytorch.org/whl/cu124

# ── Install CosyVoice dependencies ───────────────────────────────────
WORKDIR /opt/CosyVoice
RUN pip3 install --no-cache-dir \
    conformer \
    diffusers \
    gdown \
    grpcio \
    grpcio-tools \
    hydra-core \
    HyperPyYAML \
    lightning \
    matplotlib \
    modelscope \
    omegaconf \
    onnxruntime-gpu \
    openai-whisper \
    protobuf \
    pydantic \
    rich \
    soundfile \
    tensorboard \
    WeTextProcessing \
    && pip3 install --no-cache-dir \
    transformers>=4.51.0 \
    huggingface-hub>=0.20.0 \
    numpy==1.26.4

# ── Install AnimeAIDub dependencies ──────────────────────────────────
RUN pip3 install --no-cache-dir \
    demucs>=4.0.1 \
    faster-whisper>=1.0.0 \
    pyyaml>=6.0 \
    httpx>=0.27.0

# ── Copy AnimeAIDub application code ─────────────────────────────────
WORKDIR /app
COPY src/ ./src/
COPY scripts/ ./scripts/

# ── Python path for CosyVoice + AnimeAIDub imports ───────────────────
ENV PYTHONPATH="/opt/CosyVoice:/opt/CosyVoice/third_party/Matcha-TTS:/app/src:${PYTHONPATH}"
ENV COSYVOICE_ROOT="/opt/CosyVoice"
ENV HF_HOME="/models/huggingface"
ENV TORCH_HOME="/models/torch"

# /models  — pretrained model storage (persistent, download once)
# /media   — anime media files
# /work    — intermediate processing files
# /output  — dubbed output files
VOLUME ["/models", "/media", "/work", "/output"]

HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
    CMD python3 -c "import torch; print(f'GPU: {torch.cuda.is_available()}')" || exit 1

ENTRYPOINT ["python3", "-m", "pipeline.dub_episode"]
