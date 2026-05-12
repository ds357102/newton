# Newton — single-image deploy.
# Builds an image that runs the FastAPI app on $PORT (Railway/Render/Fly all set this).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build deps (some PRAW deps need gcc)
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install runtime deps first for layer caching
COPY pyproject.toml ./
RUN pip install --upgrade pip setuptools wheel && \
    pip install \
      "fastapi>=0.115" "uvicorn[standard]>=0.30" \
      "pydantic>=2.7" "pydantic-settings>=2.4" \
      "httpx>=0.27" "feedparser>=6.0" \
      "anthropic>=0.34" "structlog>=24.1" "python-multipart"

# App source
COPY . .

# Default port is 8080; hosts that set $PORT will override.
ENV PORT=8080
EXPOSE 8080

# Web process. Workers ride alongside (see Procfile) or in a sidecar service.
CMD ["sh", "-c", "python -m uvicorn newton.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
