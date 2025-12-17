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
from .execution import router as execution_router
from .registration import router as registration_router
from .oauth import router as oauth_router

# Import provider routers
from .providers import local_filesystem
from .providers import wordpress
from .providers import notion
from .providers import canva
from . import tool_slots
from .providers import google_drive
from .providers import langchain
from .providers import mcp
from .providers import slack
from .providers import airtable
from .providers import google_sheets
from .providers import github

# Create main router
router = APIRouter()

# Include status router FIRST (before base router) to ensure /status matches before /{tool_type}/status
router.include_router(status_router)

# Include OAuth router (for social media integrations)
router.include_router(oauth_router)

# Include connections router BEFORE base router to ensure /connections matches before /{tool_id}
router.include_router(connections_router)

# Include execution router (tool execution for Playbook)
router.include_router(execution_router)

# Include registration router (enhanced tool registration)
router.include_router(registration_router)

# Include tool slots router (tool slot mapping management)
router.include_router(tool_slots.router)

# Include base router LAST (core endpoints: /providers, /discover, /, /{tool_id}, etc.)
# This must be last because /{tool_id} is a catch-all route
router.include_router(base_router)

# Include provider routers
router.include_router(local_filesystem.router)
router.include_router(wordpress.router)
router.include_router(notion.router)
router.include_router(canva.router)
router.include_router(google_drive.router)
router.include_router(langchain.router)
router.include_router(mcp.router)
router.include_router(slack.router)
router.include_router(airtable.router)
router.include_router(google_sheets.router)
router.include_router(github.router)
