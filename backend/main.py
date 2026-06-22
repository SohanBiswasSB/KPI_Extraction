"""Application entry point for the KPI Extraction Platform API."""
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.api.v1.api import api_router
from app.core.database import engine, Base


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI):
    """Manage application startup and shutdown lifecycle events."""
    # Startup
    print("Starting up KPI Extraction Platform...")

    # Create database tables
    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)

    print("Database tables created/verified")

    yield

    # Shutdown
    print("Shutting down KPI Extraction Platform...")


app = FastAPI(
    title="KPI Extraction Platform API",
    description="AI-powered KPI dashboard and analytics platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_HOSTS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix="/api/v1")

# Mount static files for uploads
if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/")
async def root():
    """Return basic API metadata for the root endpoint."""
    return {
        "message": "KPI Extraction Platform API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Return a health status payload for the service."""
    return {"status": "healthy", "message": "KPI Extraction Platform is running"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
