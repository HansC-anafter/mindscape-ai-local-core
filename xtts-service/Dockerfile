# Mindscape XTTS-v2 Service — Dockerfile (ARM64 / Apple Silicon compatible)
#
# Builds on python:3.11-slim with:
# - Rust toolchain (required by sudachipy, a Coqui TTS dependency)
# - ffmpeg for audio processing
# - XTTS-v2 via TTS package

FROM python:3.11-slim

WORKDIR /app

# Install system deps including Rust (needed for sudachipy in Coqui TTS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    git \
    curl \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Install Rust (for sudachipy compilation)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Python deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py ./

# Directories
RUN mkdir -p /app/voices /app/data/tts/output

EXPOSE 8020

HEALTHCHECK --interval=30s --timeout=15s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8020/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020", "--workers", "1"]
