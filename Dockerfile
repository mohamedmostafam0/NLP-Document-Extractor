FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm 2>/dev/null

# Create non-root user
RUN groupadd -r docxtract && useradd -r -g docxtract -m docxtract

# Copy application code
COPY --chown=docxtract:docxtract . .

# Create data directory with correct ownership
RUN mkdir -p /app/data && chown docxtract:docxtract /app/data

USER docxtract

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
