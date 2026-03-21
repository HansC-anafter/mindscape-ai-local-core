FROM python:3.11-slim

# Install system dependencies for OCR and PDF processing
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8001

# EasyOCR models auto-download on first run (~90MB).
# Keep-alive timeout for slow first-inference model loading.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001", "--timeout-keep-alive", "300"]
