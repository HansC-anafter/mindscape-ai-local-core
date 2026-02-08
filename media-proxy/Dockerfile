FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY main.py .

# Run as non-root user for security (optional but good practice)
RUN useradd -m appuser
USER appuser

# Expose port (default for uvicorn is 8000 inside container)
EXPOSE 8000

# Start command
# We use one worker as it's async I/O bound, but could increase if needed.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
