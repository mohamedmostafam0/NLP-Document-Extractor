# Docxtract — NLP Document Extraction Pipeline

A web-based tool that transforms unstructured documents (business cards, resumes, medical reports) into structured, machine-readable data using NLP techniques.

## Quick Start

```bash
docker-compose up --build
```

Then open:
- **App UI**: http://localhost:8000
- **MinIO Console**: http://localhost:9001 (user: `docxtract` / pass: `docxtract123`)

## Architecture

- **Frontend**: Vanilla HTML/CSS/JS served by FastAPI
- **Backend**: FastAPI (Python)
- **File Staging**: MinIO (S3-compatible object storage)
- **Database**: SQLite + SQLAlchemy
- **NLP**: spaCy + regex + Hugging Face Transformers

## Development

```bash
# Install dependencies locally
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Run the app (requires MinIO running)
uvicorn main:app --reload --port 8000
```
