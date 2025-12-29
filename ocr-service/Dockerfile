FROM python:3.11-slim

    # Install system dependencies for PaddleOCR and PDF processing
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

# Install PaddlePaddle (auto-detect GPU/CPU)
# Fix Windows line endings (CRLF -> LF) and make executable
COPY install_paddle.sh .
RUN sed -i 's/\r$//' install_paddle.sh && \
    chmod +x install_paddle.sh && \
    ./install_paddle.sh

# Copy application code
COPY app/ ./app/

# Expose port
EXPOSE 8001

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]




