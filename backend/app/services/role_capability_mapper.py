"""
Role Capability Mapper Service

Maps newly installed capability packs to AI roles using LLM.
This service analyzes capability pack summaries and suggests which roles
should have access to the new capabilities.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import json

from backend.app.models.ai_role import AIRoleConfig
from backend.app.services.ai_role_store import AIRoleStore
from backend.app.shared.tool_executor import ToolExecutor

logger = logging.getLogger(__name__)

_executor = ToolExecutor()

# Default fallback role for unmapped capabilities
FALLBACK_ROLE_ID = "mindscape_assistant"


class RoleCapabilityMapping:
    """Single role-capability mapping"""
    role_id: str
    brief_label: str
    blurb: str
    suggested_entry_prompt: str


def _create_fallback_mapping(
    capability_id: str,
    capability_name: str,
    summary_for_roles: str,
    existing_role_ids: set,
    target_language: str = "zh-TW"
) -> Optional[Dict[str, Any]]:
    """
    Create fallback mapping to default assistant role

    Args:
        capability_id: Capability pack ID
        capability_name: Capability display name
        summary_for_roles: Summary text (should be in English)
        existing_role_ids: Set of existing role IDs
        target_language: Target language for output (e.g., 'zh-TW', 'en')

    Returns:
        Fallback mapping dictionary or None
    """
    # Default fallback role ID
    FALLBACK_ROLE_ID = "mindscape_assistant"

    # Check if fallback role exists, if not use first available role
    target_role_id = FALLBACK_ROLE_ID
    if FALLBACK_ROLE_ID not in existing_role_ids:
        # Try to find a generic assistant-like role
        assistant_like_roles = ["assistant", "helper", "mindscape_assistant", "general_assistant"]
        for role_id in assistant_like_roles:
            if role_id in existing_role_ids:
                target_role_id = role_id
                break

        # If still not found, use first available role
        if target_role_id not in existing_role_ids and existing_role_ids:
            target_role_id = list(existing_role_ids)[0]
        elif not existing_role_ids:
            # No roles available, cannot create mapping
            logger.warning("No roles available for fallback mapping")
            return None

    # Create simple fallback mapping
    brief_label = capability_name[:10] if len(capability_name) <= 10 else capability_name[:7] + "..."
    blurb = summary_for_roles[:20] + "…" if len(summary_for_roles) > 20 else summary_for_roles

    # Generate default entry prompt based on target language
    if target_language.startswith("zh"):
        entry_prompt = f"使用 {capability_name} 能力"
    else:
        entry_prompt = f"Use {capability_name} capability"

    return {
        "role_id": target_role_id,
        "brief_label": brief_label,
        "blurb": blurb,
        "suggested_entry_prompt": entry_prompt,
        "is_fallback": True  # Mark as fallback for UI display
    }


async def map_capability_to_roles(
    capability_id: str,
    capability_name: str,
    summary_for_roles: str,
    profile_id: str = "default-user",
    target_language: str = "zh-TW"
) -> List[Dict[str, Any]]:
    """
    Map a capability pack to AI roles using LLM

    Args:
        capability_id: Capability pack ID (e.g., 'mindscape.major_proposal')
        capability_name: Capability pack display name
        summary_for_roles: Summary text for role mapping (should be in English)
        profile_id: User profile ID
        target_language: Target language for output (e.g., 'zh-TW', 'en')

    Returns:
        List of role mappings with role_id, brief_label, blurb, suggested_entry_prompt
    """
    try:
        # Get all enabled roles for this profile
        role_store = AIRoleStore()
        roles = role_store.get_enabled_roles(profile_id)

        if not roles:
            logger.warning(f"No enabled roles found for profile {profile_id}")
            return []

        # Prepare role list for LLM
        role_list = []
        for role in roles:
            role_list.append({
                "id": role.id,
                "name": role.name,
                "description": role.description
            })

        # Prepare prompt for LLM
        prompt = f"""You are helping to map a newly installed capability pack to AI roles.

**Available AI Roles:**
{json.dumps(role_list, ensure_ascii=False, indent=2)}

**New Capability Pack:**
- ID: {capability_id}
- Name: {capability_name}
- Summary: {summary_for_roles}

**Task:**
Determine which roles (maximum 3) should have access to this new capability.
If no roles are a good fit, return an empty array.

**Requirements:**
- Select at most 3 roles that would benefit from this capability
- For each selected role, provide:
  - role_id: The role's ID
  - brief_label: A 4-10 character label for the new skill (in {target_language})
  - blurb: A ~20 character description of what new ability this role gains (in {target_language})
  - suggested_entry_prompt: A one-sentence prompt users can use to access this skill (in {target_language})

**Output Format (JSON array):**
[
  {{
    "role_id": "project_manager",
    "brief_label": "寫重大計畫書",
    "blurb": "幫你把計畫目標拆成條列，整理成可送件的計畫書草稿。",
    "suggested_entry_prompt": "幫我寫一份可送政府補助的計畫書草稿。"
  }}
]

**Note:** All output text (brief_label, blurb, suggested_entry_prompt) should be in {target_language}.
Return only valid JSON, no additional text."""

        # Call LLM for structured extraction
        from backend.app.capabilities.core_llm.services.structured import extract as structured_extract

        schema_description = f"""Array of role mappings. Each mapping contains:
- role_id: Role ID from the available roles list
- brief_label: 4-10 character label for the new skill (in {target_language})
- blurb: ~20 character description of the new ability (in {target_language})
- suggested_entry_prompt: One-sentence prompt for users to access this skill (in {target_language})"""

        # Generate example output based on target language
        if target_language.startswith("zh"):
            example_output = [
                {
                    "role_id": "project_manager",
                    "brief_label": "寫重大計畫書",
                    "blurb": "幫你把計畫目標拆成條列，整理成可送件的計畫書草稿。",
                    "suggested_entry_prompt": "幫我寫一份可送政府補助的計畫書草稿。"
                }
            ]
        else:
            example_output = [
                {
                    "role_id": "project_manager",
                    "brief_label": "Write Proposals",
                    "blurb": "Helps break down goals and draft grant proposals.",
                    "suggested_entry_prompt": "Help me write a government grant proposal draft."
                }
            ]

        result = await structured_extract(
            text=prompt,
            schema_description=schema_description,
            example_output=example_output,
            target_language=target_language
        )

        extracted_data = result.get("extracted_data", {})
        # Handle both array and object formats
        if isinstance(extracted_data, list):
            mappings = extracted_data
        elif isinstance(extracted_data, dict) and "mappings" in extracted_data:
            mappings = extracted_data["mappings"]
        elif isinstance(extracted_data, dict):
            # If it's a single mapping, wrap in array
            mappings = [extracted_data] if extracted_data else []
        else:
            mappings = []

        # Validate mappings
        valid_mappings = []
        role_ids = {role.id for role in roles}

        for mapping in mappings:
            if mapping.get("role_id") in role_ids:
                valid_mappings.append(mapping)
            else:
                logger.warning(f"Invalid role_id in mapping: {mapping.get('role_id')}")

        # Fallback: If no mappings found, assign to default assistant role
        if not valid_mappings:
            logger.info(f"No role mappings found for {capability_id}, using fallback role")
            fallback_mapping = _create_fallback_mapping(
                capability_id,
                capability_name,
                summary_for_roles,
                role_ids,
                target_language=target_language
            )
            if fallback_mapping:
                valid_mappings.append(fallback_mapping)

        logger.info(f"Mapped {capability_id} to {len(valid_mappings)} roles: {[m['role_id'] for m in valid_mappings]}")

        return valid_mappings

    except Exception as e:
        logger.error(f"Failed to map capability to roles: {e}", exc_info=True)
        # On error, still create fallback mapping to ensure capability is accessible
        try:
            role_store = AIRoleStore()
            roles = role_store.get_enabled_roles(profile_id)
            role_ids = {role.id for role in roles} if roles else set()

            fallback_mapping = _create_fallback_mapping(
                capability_id,
                capability_name,
                summary_for_roles,
                role_ids,
                target_language=target_language
            )
            if fallback_mapping:
                logger.info(f"Created fallback mapping for {capability_id} due to error")
                return [fallback_mapping]
        except Exception as fallback_error:
            logger.error(f"Failed to create fallback mapping: {fallback_error}", exc_info=True)

        return []


def save_role_capability_mappings(
    capability_id: str,
    mappings: List[Dict[str, Any]],
    profile_id: str = "default-user"
) -> Dict[str, Any]:
    """
    Save role-capability mappings to database

    Args:
        capability_id: Capability pack ID
        mappings: List of mapping dictionaries
        profile_id: User profile ID

    Returns:
        Dict with saved_count and has_fallback flag
    """
    try:
        import sqlite3
        from pathlib import Path

        # Get database path (same as ai_role_store)
        db_path = Path("./data/mindscape.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create table if not exists (add is_fallback column)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS role_capabilities (
                role_id TEXT NOT NULL,
                capability_id TEXT NOT NULL,
                profile_id TEXT NOT NULL,
                label TEXT NOT NULL,
                blurb TEXT NOT NULL,
                entry_prompt TEXT NOT NULL,
                is_fallback INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                PRIMARY KEY (role_id, capability_id, profile_id)
            )
        """)

        # Add is_fallback column if it doesn't exist (for existing databases)
        try:
            cursor.execute("ALTER TABLE role_capabilities ADD COLUMN is_fallback INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            # Column already exists
            pass

        from datetime import datetime
        now = datetime.utcnow().isoformat()

        saved_count = 0
        has_fallback = False

        for mapping in mappings:
            try:
                is_fallback = mapping.get("is_fallback", False)
                if is_fallback:
                    has_fallback = True

                cursor.execute("""
                    INSERT OR REPLACE INTO role_capabilities
                    (role_id, capability_id, profile_id, label, blurb, entry_prompt, is_fallback, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    mapping["role_id"],
                    capability_id,
                    profile_id,
                    mapping["brief_label"],
                    mapping["blurb"],
                    mapping["suggested_entry_prompt"],
                    1 if is_fallback else 0,
                    now
                ))
                saved_count += 1
            except Exception as e:
                logger.error(f"Failed to save mapping for role {mapping.get('role_id')}: {e}")

        conn.commit()
        conn.close()

        logger.info(f"Saved {saved_count} role-capability mappings for {capability_id} (fallback: {has_fallback})")

        return {
            "saved_count": saved_count,
            "has_fallback": has_fallback
        }

    except Exception as e:
        logger.error(f"Failed to save role-capability mappings: {e}", exc_info=True)
        return {
            "saved_count": 0,
            "has_fallback": False
        }


def get_role_capabilities(role_id: str, profile_id: str = "default-user") -> List[Dict[str, Any]]:
    """
    Get all capabilities mapped to a specific role

    Args:
        role_id: Role ID
        profile_id: User profile ID

    Returns:
        List of capability mappings
    """
    try:
        import sqlite3
        from pathlib import Path

        db_path = Path("./data/mindscape.db")
        if not db_path.exists():
            return []

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT capability_id, label, blurb, entry_prompt, is_fallback
            FROM role_capabilities
            WHERE role_id = ? AND profile_id = ?
            ORDER BY is_fallback ASC, created_at DESC
        """, (role_id, profile_id))

        results = []
        for row in cursor.fetchall():
            results.append({
                "capability_id": row["capability_id"],
                "label": row["label"],
                "blurb": row["blurb"],
                "entry_prompt": row["entry_prompt"],
                "is_fallback": bool(row.get("is_fallback", 0))
            })

        conn.close()
        return results

    except Exception as e:
        logger.error(f"Failed to get role capabilities: {e}", exc_info=True)
        return []
