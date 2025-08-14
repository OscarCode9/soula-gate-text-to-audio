# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies needed for audio processing and compilation
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    libsndfile1 \
    libsndfile1-dev \
    pkg-config \
    build-essential \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/

# Create a non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Create cache directories with proper permissions
RUN mkdir -p /home/appuser/.cache/huggingface && \
    mkdir -p /home/appuser/.cache/kokoro && \
    chown -R appuser:appuser /home/appuser/.cache

USER appuser

# Expose the port the app runs on
EXPOSE 5032

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/home/appuser/.cache/huggingface
ENV TRANSFORMERS_CACHE=/home/appuser/.cache/huggingface
ENV HF_HUB_CACHE=/home/appuser/.cache/huggingface

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:5032/ || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5032"]
