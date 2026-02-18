FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04

LABEL maintainer="Ray DiRenzo"
LABEL description="AnimeAIDub - AI-powered anime dubbing pipeline"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3-pip \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1

WORKDIR /app

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config.example.yaml .

VOLUME ["/data", "/models", "/media"]

EXPOSE 29100

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python3 -c "import httpx; httpx.get('http://localhost:29100/health')" || exit 1

ENTRYPOINT ["python3", "-m", "src.main"]
