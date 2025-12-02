"""
Tools routes module

Refactored from monolithic tools.py into modular structure.

This module integrates all tool-related routers:
- Base router: core tool management endpoints
- Provider routers: provider-specific endpoints (WordPress, Notion, Canva, etc.)
- Connections router: connection CRUD operations
- Status router: tool status checking
"""
from fastapi import APIRouter

from .base import router as base_router
from .connections import router as connections_router
from .status import router as status_router

# Import provider routers
from .providers import local_filesystem
from .providers import wordpress
from .providers import notion
from .providers import canva
from .providers import google_drive
from .providers import langchain
from .providers import mcp

# Create main router
router = APIRouter()

# Include status router FIRST (before base router) to ensure /status matches before /{tool_type}/status
router.include_router(status_router)

# Include base router (core endpoints: /providers, /discover, /, /{tool_id}, etc.)
router.include_router(base_router)

# Include connections router
router.include_router(connections_router)

# Include provider routers
router.include_router(local_filesystem.router)
router.include_router(wordpress.router)
router.include_router(notion.router)
router.include_router(canva.router)
router.include_router(google_drive.router)
router.include_router(langchain.router)
router.include_router(mcp.router)
