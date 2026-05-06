import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config import settings, BASE_DIR
from models.database import create_tables
from routers.documents import router as documents_router

logger = logging.getLogger("docxtract.app")

STATIC_DIR = BASE_DIR / "static"


# --- Lifespan (replaces deprecated on_event) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle hook."""
    logger.info("Creating database tables …")
    create_tables()
    logger.info("Docxtract is ready  →  http://%s:%s", settings.APP_HOST, settings.APP_PORT)
    yield
    logger.info("Shutting down …")


app = FastAPI(
    title="Docxtract",
    description="NLP-powered document extraction pipeline",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — restrict in production, open for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# API router
app.include_router(documents_router, prefix="/api")


# --- Global exception handler ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch unhandled errors so the client always gets a JSON response."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


@app.get("/")
async def root():
    return FileResponse(str(STATIC_DIR / "index.html"))
