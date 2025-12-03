"""
Tool provider-specific routers

Each provider module contains routes specific to that tool provider.
This module exports all provider routers for integration.
"""
from fastapi import APIRouter

from . import local_filesystem
from . import wordpress
from . import notion
from . import canva
from . import google_drive
from . import langchain
from . import mcp
from . import slack
from . import airtable
from . import google_sheets

# Export all provider routers
__all__ = [
    "local_filesystem",
    "wordpress",
    "notion",
    "canva",
    "google_drive",
    "langchain",
    "mcp",
    "slack",
    "airtable",
    "google_sheets",
]
