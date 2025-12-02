"""
Tool Information Registry

Provides official information and links for external tools.
Used in capability pack cards to help users find tools if not installed locally.
"""
from typing import Dict, Any, Optional

TOOL_INFO: Dict[str, Dict[str, Any]] = {
    "wordpress": {
        "name": "WordPress",
        "official_url": "https://wordpress.org/",
        "download_url": "https://wordpress.org/download/",
        "description": "Open-source content management system",
        "installation_type": "local_or_remote",
        "local_setup_guide": "https://wordpress.org/support/article/how-to-install-wordpress/"
    },
    "notion": {
        "name": "Notion",
        "official_url": "https://www.notion.so/",
        "download_url": "https://www.notion.so/desktop",
        "description": "All-in-one workspace for notes, docs, and collaboration",
        "installation_type": "cloud_service",
        "api_docs": "https://developers.notion.com/"
    },
    "google_drive": {
        "name": "Google Drive",
        "official_url": "https://www.google.com/drive/",
        "download_url": "https://www.google.com/drive/download/",
        "description": "Cloud storage and file sharing service",
        "installation_type": "cloud_service",
        "api_docs": "https://developers.google.com/drive"
    },
    "obsidian": {
        "name": "Obsidian",
        "official_url": "https://obsidian.md/",
        "download_url": "https://obsidian.md/download",
        "description": "Knowledge base that works on local Markdown files",
        "installation_type": "local_app",
        "local_setup_guide": "https://obsidian.md/help/"
    },
    "vector_db": {
        "name": "PostgreSQL with pgvector",
        "official_url": "https://www.postgresql.org/",
        "download_url": "https://www.postgresql.org/download/",
        "description": "Open-source relational database with vector extension",
        "installation_type": "local_or_remote",
        "pgvector_docs": "https://github.com/pgvector/pgvector"
    },
    "canva": {
        "name": "Canva",
        "official_url": "https://www.canva.com/",
        "api_docs": "https://www.canva.com/developers/",
        "description": "Design platform for creating visual content, templates, and graphics",
        "installation_type": "cloud_service"
    }
}


def get_tool_info(tool_type: str) -> Optional[Dict[str, Any]]:
    """
    Get official information for a tool

    Args:
        tool_type: Tool type identifier (e.g., 'wordpress', 'obsidian')

    Returns:
        Tool information dict or None if not found
    """
    return TOOL_INFO.get(tool_type)


def get_tools_info(tool_types: list[str]) -> Dict[str, Dict[str, Any]]:
    """
    Get official information for multiple tools

    Args:
        tool_types: List of tool type identifiers

    Returns:
        Dict mapping tool_type -> tool_info
    """
    return {
        tool_type: get_tool_info(tool_type)
        for tool_type in tool_types
        if get_tool_info(tool_type) is not None
    }



