"""
AI Team Service - manages AI team member configurations

Provides functions to load and retrieve AI team member information
from configuration files, supporting playbook-specific variants.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from functools import lru_cache

logger = logging.getLogger(__name__)

# Cache for loaded configuration
_ai_team_config_cache: Optional[Dict[str, Any]] = None


def _load_ai_team_config() -> Dict[str, Any]:
    """Load AI team members configuration from JSON file"""
    global _ai_team_config_cache

    if _ai_team_config_cache is not None:
        return _ai_team_config_cache

    try:
        # Get config file path
        config_dir = Path(__file__).parent.parent / "config"
        config_file = config_dir / "ai_team_members.json"

        if not config_file.exists():
            logger.warning(f"AI team config file not found: {config_file}")
            _ai_team_config_cache = {}
            return _ai_team_config_cache

        with open(config_file, 'r', encoding='utf-8') as f:
            _ai_team_config_cache = json.load(f)

        logger.info(f"Loaded AI team config from {config_file}")
        return _ai_team_config_cache

    except Exception as e:
        logger.error(f"Failed to load AI team config: {e}", exc_info=True)
        _ai_team_config_cache = {}
        return _ai_team_config_cache


def get_member_info(pack_id: str, playbook_code: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get AI team member information by pack_id

    Args:
        pack_id: Pack ID (e.g., "content_planner")
        playbook_code: Optional playbook code for variant lookup

    Returns:
        Member info dict or None if not found
    """
    config = _load_ai_team_config()

    if pack_id not in config:
        logger.debug(f"Pack ID {pack_id} not found in AI team config")
        return None

    member_config = config[pack_id]

    # Try playbook-specific variant first
    if playbook_code and playbook_code in member_config:
        variant = member_config[playbook_code]
        return {
            "pack_id": pack_id,
            "name": variant.get("name", pack_id),
            "name_zh": variant.get("name_zh", pack_id),
            "role": variant.get("role", ""),
            "icon": variant.get("icon", "🤖"),
            "visible": variant.get("visible", True),
            "order": variant.get("order", 999)
        }

    # Fallback to default
    if "default" in member_config:
        default = member_config["default"]
        return {
            "pack_id": pack_id,
            "name": default.get("name", pack_id),
            "name_zh": default.get("name_zh", pack_id),
            "role": default.get("role", ""),
            "icon": default.get("icon", "🤖"),
            "visible": default.get("visible", True),
            "order": default.get("order", 999)
        }

    # No default found
    logger.warning(f"No default config found for pack_id {pack_id}")
    return None


def get_members_from_tasks(tasks: List[Any], playbook_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extract AI team members from task list

    Args:
        tasks: List of Task or TaskPlan objects
        playbook_code: Optional playbook code for variant lookup

    Returns:
        List of member info dicts, filtered by visible and sorted by order
    """
    members = []
    seen_pack_ids = set()

    for task in tasks:
        pack_id = None
        if hasattr(task, 'pack_id'):
            pack_id = task.pack_id
        elif isinstance(task, dict):
            pack_id = task.get('pack_id')

        if not pack_id or pack_id in seen_pack_ids:
            continue

        seen_pack_ids.add(pack_id)
        member_info = get_member_info(pack_id, playbook_code)

        if member_info and member_info.get("visible", True):
            members.append(member_info)

    # Sort by order
    members.sort(key=lambda m: m.get("order", 999))

    return members


def get_all_members(playbook_code: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get all visible AI team members

    Args:
        playbook_code: Optional playbook code for variant lookup

    Returns:
        List of all visible member info dicts, sorted by order
    """
    config = _load_ai_team_config()
    members = []

    for pack_id in config.keys():
        member_info = get_member_info(pack_id, playbook_code)
        if member_info and member_info.get("visible", True):
            members.append(member_info)

    # Sort by order
    members.sort(key=lambda m: m.get("order", 999))

    return members

