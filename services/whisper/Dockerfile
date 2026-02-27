FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    faster-whisper \
    pydantic

COPY server.py .

EXPOSE 8006

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8006", "--workers", "1"]
