# Afrigen V2 Production Dockerfile
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies including ffmpeg for audio/video assembly
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application codebase
COPY . .
RUN groupadd --system afrigen && useradd --system --gid afrigen afrigen && \
    mkdir -p /app/logs /app/static/uploads && \
    chown afrigen:afrigen /app /app/logs /app/static/uploads

# Expose default port
EXPOSE 5000

# Run schema migrations as a one-off release step, not concurrently in web replicas.
USER afrigen
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl --fail --silent http://127.0.0.1:5000/healthz || exit 1
CMD ["gunicorn", "app:app", "--workers", "1", "--threads", "8", "--timeout", "180", "--bind", "0.0.0.0:5000"]

