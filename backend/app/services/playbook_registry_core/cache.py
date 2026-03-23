"""Cache helpers for PlaybookRegistry."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Set


def invalidate_registry_cache(
    *,
    system_playbooks: Dict[str, Dict[str, Any]],
    capability_playbooks: Dict[str, Dict[str, Any]],
    user_playbooks: Dict[str, Dict[str, Any]],
    playbook_variants: Dict[str, Any],
    loaded_capabilities: Set[str],
    capability_locks: Dict[str, Any],
    logger: logging.Logger,
    playbook_code: Optional[str] = None,
    locale: Optional[str] = None,
    capability_code: Optional[str] = None,
) -> bool:
    """Invalidate playbook caches and return whether the full registry was reset."""
    if capability_code:
        if capability_code in capability_playbooks:
            del capability_playbooks[capability_code]

        prefix = f"{capability_code}."
        stale_keys = [key for key in playbook_variants if key.startswith(prefix)]
        for key in stale_keys:
            variant_payload = playbook_variants.get(key)
            plain_key = key[len(prefix) :]
            if playbook_variants.get(plain_key) is variant_payload:
                playbook_variants.pop(plain_key, None)
            playbook_variants.pop(key, None)

        loaded_capabilities.discard(capability_code)
        logger.info("Invalidated cache for capability %s", capability_code)
        return False

    if playbook_code:
        if locale:
            if locale in system_playbooks and playbook_code in system_playbooks[locale]:
                del system_playbooks[locale][playbook_code]
                logger.info(
                    "Invalidated cache for playbook %s (locale: %s)",
                    playbook_code,
                    locale,
                )
        else:
            for current_locale in system_playbooks:
                if playbook_code in system_playbooks[current_locale]:
                    del system_playbooks[current_locale][playbook_code]
            logger.info(
                "Invalidated cache for playbook %s (all locales)", playbook_code
            )

        if "." in playbook_code:
            variant_payload = playbook_variants.get(playbook_code)
            plain_key = playbook_code.split(".", 1)[1]
            if playbook_variants.get(plain_key) is variant_payload:
                playbook_variants.pop(plain_key, None)
            playbook_variants.pop(playbook_code, None)
            return False

        playbook_variants.pop(playbook_code, None)
        suffix = f".{playbook_code}"
        dotted_keys = [key for key in playbook_variants if key.endswith(suffix)]
        for key in dotted_keys:
            playbook_variants.pop(key, None)
        return False

    loaded_capabilities.clear()
    capability_locks.clear()
    system_playbooks.clear()
    capability_playbooks.clear()
    user_playbooks.clear()
    playbook_variants.clear()
    logger.info("Invalidated all playbook caches")
    return True
