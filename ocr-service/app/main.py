"""
OCR Service Main Application
FastAPI application for local PaddleOCR service
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import health, ocr

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="OCR Service",
    description="Local PaddleOCR service for text extraction from images and PDFs",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router)
app.include_router(ocr.router)


@app.on_event("startup")
async def startup_event():
    """Initialize service on startup"""
    logger.info("OCR Service starting up...")
    logger.info("Service ready to process OCR requests")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("OCR Service shutting down...")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "ocr-service",
        "version": "1.0.0",
        "status": "running"
    }




