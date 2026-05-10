FROM python:3.11-slim

WORKDIR /app

# System dependencies (Tesseract for OCR, Poppler for pdf2image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    tesseract-ocr \
    libtesseract-dev \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download spaCy model
RUN python -m spacy download en_core_web_sm

# Pre-download HuggingFace NER model so first request is fast
RUN python -c "from transformers import AutoTokenizer, AutoModelForTokenClassification; \
    AutoTokenizer.from_pretrained('dslim/bert-base-NER'); \
    AutoModelForTokenClassification.from_pretrained('dslim/bert-base-NER')"

# Non-root user
RUN groupadd -r docxtract && useradd -r -g docxtract -m docxtract

COPY --chown=docxtract:docxtract . .

RUN mkdir -p /app/data && chown docxtract:docxtract /app/data

# HuggingFace cache must be writable by the non-root user
RUN mkdir -p /home/docxtract/.cache && chown -R docxtract:docxtract /home/docxtract/.cache
ENV HF_HOME=/home/docxtract/.cache/huggingface

USER docxtract

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
