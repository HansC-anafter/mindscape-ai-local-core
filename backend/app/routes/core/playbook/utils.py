"""
Shared utility functions for playbook routes
"""

from typing import Optional, List, Dict, Any
from ....models.playbook import Playbook


def determine_preferred_locale(
    target_language: Optional[str] = None,
    locale: Optional[str] = None
) -> Optional[str]:
    """
    Determine preferred locale from target_language or locale parameter

    Args:
        target_language: Target language for filtering (e.g., 'zh-TW', 'en')
        locale: Language locale (deprecated, use target_language instead)

    Returns:
        Preferred locale string or None
    """
    preferred_locale = None
    if target_language:
        if target_language.startswith('en'):
            preferred_locale = 'en'
        elif target_language.startswith('zh'):
            preferred_locale = 'zh-TW'
        elif target_language.startswith('ja') or target_language == 'ja':
            preferred_locale = 'ja'
    elif locale:
        preferred_locale = locale

    return preferred_locale


def select_preferred_locale_version(
    playbooks: List[Playbook],
    preferred_locale: Optional[str] = None
) -> List[Playbook]:
    """
    Group playbooks by playbook_code and select preferred locale version

    Args:
        playbooks: List of playbooks to process
        preferred_locale: Preferred locale (if specified)

    Returns:
        List of playbooks with preferred locale versions selected
    """
    playbook_dict = {}
    locale_priority = {'zh-TW': 3, 'en': 2, 'ja': 1}

    for playbook in playbooks:
        code = playbook.metadata.playbook_code
        playbook_locale = playbook.metadata.locale

        if code not in playbook_dict:
            playbook_dict[code] = playbook
        elif preferred_locale:
            if playbook_locale == preferred_locale and playbook_dict[code].metadata.locale != preferred_locale:
                playbook_dict[code] = playbook
            elif playbook_dict[code].metadata.locale == preferred_locale and playbook_locale != preferred_locale:
                continue
            elif playbook_dict[code].metadata.locale != preferred_locale and playbook_locale != preferred_locale:
                if locale_priority.get(playbook_locale, 0) > locale_priority.get(playbook_dict[code].metadata.locale, 0):
                    playbook_dict[code] = playbook
        else:
            if locale_priority.get(playbook_locale, 0) > locale_priority.get(playbook_dict[code].metadata.locale, 0):
                playbook_dict[code] = playbook

    return list(playbook_dict.values())


def filter_playbooks(
    playbooks: List[Playbook],
    tag_list: Optional[List[str]] = None,
    onboarding_task: Optional[str] = None,
    uses_tool: Optional[str] = None
) -> List[Playbook]:
    """
    Filter playbooks by tags, onboarding_task, or uses_tool

    Args:
        playbooks: List of playbooks to filter
        tag_list: List of tags to filter by
        onboarding_task: Onboarding task to filter by
        uses_tool: Tool name to filter by

    Returns:
        Filtered list of playbooks
    """
    filtered = playbooks

    if tag_list:
        filtered = [p for p in filtered
                   if any(tag in p.metadata.tags for tag in tag_list)]

    if onboarding_task:
        filtered = [p for p in filtered
                   if p.metadata.onboarding_task == onboarding_task]

    if uses_tool:
        filtered = [p for p in filtered
                   if uses_tool in (p.metadata.required_tools or [])]

    return filtered


def format_playbook_list_response(
    playbook: Playbook,
    user_meta: Optional[Dict[str, Any]] = None,
    has_personal_variant: bool = False,
    default_variant: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Format playbook object to API response format for list endpoints

    Args:
        playbook: Playbook object to format
        user_meta: User metadata (favorite, use_count, etc.)
        has_personal_variant: Whether playbook has personal variant
        default_variant: Default variant information

    Returns:
        Formatted playbook response dictionary
    """
    return {
        "playbook_code": playbook.metadata.playbook_code,
        "version": playbook.metadata.version,
        "locale": playbook.metadata.locale,
        "name": playbook.metadata.name,
        "description": playbook.metadata.description,
        "tags": playbook.metadata.tags,
        "entry_agent_type": playbook.metadata.entry_agent_type,
        "onboarding_task": playbook.metadata.onboarding_task,
        "icon": playbook.metadata.icon,
        "required_tools": playbook.metadata.required_tools,
        "kind": playbook.metadata.kind.value if playbook.metadata.kind else None,
        "capability_code": playbook.metadata.capability_code,
        "user_meta": user_meta or {
            "favorite": False,
            "use_count": 0
        },
        "has_personal_variant": has_personal_variant,
        "default_variant_name": default_variant.get("variant_name") if default_variant else None
    }


def sort_playbooks_by_user_preference(
    playbooks: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Sort playbooks by user preference (favorite first, then use_count)

    Args:
        playbooks: List of playbook response dictionaries

    Returns:
        Sorted list of playbooks
    """
    return sorted(playbooks, key=lambda x: (
        -int(x['user_meta'].get('favorite', False)),
        -x['user_meta'].get('use_count', 0)
    ))

