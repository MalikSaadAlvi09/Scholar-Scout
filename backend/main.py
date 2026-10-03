"""
ScholarScout - Main FastAPI Application.
Coordinates REST API routes, static web dashboard, and persistent research job worker.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend.config import config
from backend.logging_utils import logger
from backend.database import init_db
from backend.jobs.queue import job_worker
from backend.api.routes import router as api_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for application startup and shutdown."""
    logger.info("Initializing ScholarScout application...")
    # Initialize SQLite tables and migrations
    init_db()
    # Start persistent job worker
    job_worker.start()
    logger.info(f"ScholarScout running at http://{config.app_host}:{config.app_port}")
    yield
    # Shutdown worker
    logger.info("Shutting down ScholarScout...")
    job_worker.stop()

app = FastAPI(
    title="ScholarScout",
    description="Intelligent University Scholarship & Faculty Research Finder powered by Nemotron",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API routes
app.include_router(api_router)

# Mount Static Files (CSS, JS)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_index():
    """Serves the main web dashboard."""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {
        "message": "ScholarScout API is running. Web UI static files not found.",
        "docs": "/docs",
        "health": "/api/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=config.app_host,
        port=config.app_port,
        reload=config.debug
    )
