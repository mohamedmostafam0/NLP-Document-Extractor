# Docxtract — NLP Document Intelligence Pipeline

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.11-blue?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/PostgreSQL-316192?style=flat&logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/spaCy-09A3D5?style=flat&logo=spacy&logoColor=white" alt="spaCy">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white" alt="Docker">
</div>

<br>

**Docxtract** is an advanced, self-hosted web application that transforms unstructured documents (such as Business Cards, Resumes, and Medical Reports) into highly accurate, structured, machine-readable JSON data using Natural Language Processing (NLP).

## ✨ Key Features

- 🧠 **Robust NLP Pipeline**: Leverages a combination of spaCy Named Entity Recognition (NER), custom regular expressions, and layout-aware heuristics to reliably extract key fields even from complex layouts like Resume headers.
- ⚡ **Real-Time Progress Tracking**: A live, animated Server-Sent Events (SSE) pipeline tracker keeps you informed across all 6 processing phases (Upload → Storage → OCR → NER Extraction → Structuring → Done).
- ✏️ **Manual Data Review & Editing**: A built-in JSON editor modal allows human reviewers to manually correct or append fields when the NLP engine isn't 100% confident. 
- 📊 **Export Capabilities**: Instantly download extracted structured data in `.json` or `.csv` formats.
- 🎨 **Modern, Premium UI**: A sleek, fully responsive dark-mode Single Page Application (SPA) featuring drag-and-drop file uploads, dynamic confidence scoring bars, and smooth transitions.

---

## 🏗 Architecture

Docxtract follows a decoupled service architecture orchestrated via Docker Compose:

- **Frontend**: Vanilla HTML5, CSS3, and JavaScript interacting asynchronously with the REST API.
- **Backend API**: FastAPI framework running on Python 3.11.
- **Storage Layer**: MinIO (S3-compatible object storage) for staging raw uploaded files securely.
- **Database Layer**: PostgreSQL (via SQLAlchemy ORM) to persist document metadata, structured extraction results, and human-review status.
- **Extraction Engine**: 
  - `tesseract-ocr` for Optical Character Recognition (OCR) of images/PDFs.
  - `spaCy` (`en_core_web_sm`) and Hugging Face Transformers for NER token classification.

---

## 🚀 Quick Start

The easiest way to run the full application (including PostgreSQL and MinIO) is using Docker Compose.

### Prerequisites
- Docker & Docker Compose installed on your system.

### Running the App

```bash
# Clone the repository
git clone https://github.com/mohamedmostafam0/NLP-Document-Extractor.git
cd NLP-Document-Extractor

# Build and start the services
docker compose up -d --build
```

Wait a few seconds for the database and storage services to initialize, then open your browser:
- **Docxtract Dashboard**: [http://localhost:8000](http://localhost:8000)
- **MinIO Console**: [http://localhost:9001](http://localhost:9001) *(Credentials: `docxtract` / `docxtract123`)*

---

## 🛠 Local Development

If you prefer to run the application locally without Docker (e.g., for active development):

1. **Install System Dependencies** (Ubuntu/Debian example):
   ```bash
   sudo apt-get update
   sudo apt-get install tesseract-ocr libtesseract-dev
   ```

2. **Set up a Virtual Environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   python -m spacy download en_core_web_sm
   ```

3. **Start External Services**:
   Ensure you have a local or Dockerized PostgreSQL and MinIO instance running. You will need to define a `.env` file referencing your `DATABASE_URL` and `MINIO_ENDPOINT`.

4. **Run the FastAPI Server**:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

---

## 📄 Supported Document Types

Currently, the NLP pipeline is optimized with distinct heuristics and schemas for:
1. **Resumes (`resume`)**: Extracts Name, Contact Info (Email/Phone), Location, Skills, Education, and Work Experience.
2. **Business Cards (`business_card`)**: Extracts Name, Title, Company, Email, Phone, Address, and Website.
3. **Medical Reports (`medical_report`)**: Extracts Patient Name, DOB, Visit Date, Provider, Diagnoses, Medications, and Vitals.

## 🤝 Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change. Ensure to update tests as appropriate.
