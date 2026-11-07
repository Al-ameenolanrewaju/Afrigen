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

# Expose default port
EXPOSE 5000

# Run migrations and start Gunicorn web server
CMD ["sh", "-c", "flask db upgrade && gunicorn app:app --workers 1 --threads 8 --timeout 180 --bind 0.0.0.0:5000"]

