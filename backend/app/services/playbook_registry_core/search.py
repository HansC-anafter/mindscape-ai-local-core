"""Search helpers for PlaybookRegistry."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from backend.app.models.playbook import Playbook, PlaybookMetadata
from backend.app.services.playbook_loaders import PlaybookFileLoader


def lookup_local_playbook(
    *,
    system_playbooks: Dict[str, Dict[str, Playbook]],
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    user_playbooks: Dict[str, Dict[str, Playbook]],
    playbook_code: str,
    locale: str,
    workspace_id: Optional[str],
    capability_code: Optional[str],
    logger: logging.Logger,
) -> Optional[Playbook]:
    """Search user, capability, and system caches for a playbook."""
    fallback_locales = [candidate for candidate in ("zh-TW", "en", "ja") if candidate != locale]

    if workspace_id and workspace_id in user_playbooks:
        if playbook_code in user_playbooks[workspace_id]:
            logger.debug(
                "Found playbook %s in user playbooks for workspace %s",
                playbook_code,
                workspace_id,
            )
            return user_playbooks[workspace_id][playbook_code]

    if capability_code and capability_code in capability_playbooks:
        playbooks = capability_playbooks[capability_code]
        full_code_locale_key = f"{capability_code}.{playbook_code}:{locale}"
        if full_code_locale_key in playbooks:
            logger.debug(
                "Found playbook %s (%s) via full_code locale key in capability %s",
                playbook_code,
                locale,
                capability_code,
            )
            return playbooks[full_code_locale_key]

        locale_key = f"{playbook_code}:{locale}"
        if locale_key in playbooks:
            logger.debug(
                "Found playbook %s (%s) in capability %s",
                playbook_code,
                locale,
                capability_code,
            )
            return playbooks[locale_key]

        full_code = f"{capability_code}.{playbook_code}"
        found_playbook = playbooks.get(full_code)
        if found_playbook and found_playbook.metadata.locale == locale:
            logger.debug(
                "Found playbook %s (%s) in capability %s",
                full_code,
                locale,
                capability_code,
            )
            return found_playbook

        found_playbook = playbooks.get(playbook_code)
        if found_playbook and found_playbook.metadata.locale == locale:
            logger.debug(
                "Found playbook %s (%s) in capability %s",
                playbook_code,
                locale,
                capability_code,
            )
            return found_playbook

        found_playbook = playbooks.get(playbook_code)
        if found_playbook:
            logger.debug(
                "Falling back to playbook %s locale %s in capability %s",
                playbook_code,
                found_playbook.metadata.locale,
                capability_code,
            )
            return found_playbook

        found_playbook = playbooks.get(full_code)
        if found_playbook:
            logger.debug(
                "Falling back to playbook %s locale %s in capability %s via full code",
                full_code,
                found_playbook.metadata.locale,
                capability_code,
            )
            return found_playbook

    locale_key = f"{playbook_code}:{locale}"
    for cap_code, playbooks in capability_playbooks.items():
        if locale_key in playbooks:
            logger.debug(
                "Found playbook %s (%s) in capability %s",
                playbook_code,
                locale,
                cap_code,
            )
            return playbooks[locale_key]

        full_code = f"{cap_code}.{playbook_code}"
        found_playbook = playbooks.get(full_code)
        if found_playbook and found_playbook.metadata.locale == locale:
            logger.debug(
                "Found playbook %s (%s) in capability %s",
                full_code,
                locale,
                cap_code,
            )
            return found_playbook

        found_playbook = playbooks.get(playbook_code)
        if found_playbook and found_playbook.metadata.locale == locale:
            logger.debug(
                "Found playbook %s (%s) in capability %s",
                playbook_code,
                locale,
                cap_code,
            )
            return found_playbook

        found_playbook = playbooks.get(playbook_code)
        if found_playbook:
            logger.debug(
                "Falling back to playbook %s locale %s in capability %s",
                playbook_code,
                found_playbook.metadata.locale,
                cap_code,
            )
            return found_playbook

        found_playbook = playbooks.get(full_code)
        if found_playbook:
            logger.debug(
                "Falling back to playbook %s locale %s in capability %s via full code",
                full_code,
                found_playbook.metadata.locale,
                cap_code,
            )
            return found_playbook

    if locale in system_playbooks:
        if playbook_code in system_playbooks[locale]:
            logger.debug(
                "Found playbook %s in system playbooks for locale %s",
                playbook_code,
                locale,
            )
            return system_playbooks[locale][playbook_code]

        logger.debug(
            "Playbook %s not found in system playbooks for locale %s, available codes: %s",
            playbook_code,
            locale,
            list(system_playbooks[locale].keys()),
        )
    for fallback_locale in fallback_locales:
        if fallback_locale in system_playbooks and playbook_code in system_playbooks[fallback_locale]:
            logger.debug(
                "Falling back to system playbook %s locale %s",
                playbook_code,
                fallback_locale,
            )
            return system_playbooks[fallback_locale][playbook_code]

    logger.debug("Locale %s not found in system playbooks", locale)
    return None


def resolve_playbook_lookup_request(
    *,
    playbook_code: str,
    capability_code: Optional[str],
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    logger: logging.Logger,
) -> tuple[str, str, Optional[str], Optional[str]]:
    """Normalize dotted playbook codes before the actual lookup starts."""
    requested_playbook_code = playbook_code
    resolved_capability = capability_code

    if not resolved_capability and "." in playbook_code:
        resolved_capability, playbook_code = playbook_code.split(".", 1)
    if resolved_capability and not capability_code:
        capability_code = resolved_capability

    if "." in playbook_code:
        potential_capability_code, actual_playbook_code = playbook_code.split(".", 1)
        if potential_capability_code in capability_playbooks:
            if not capability_code:
                capability_code = potential_capability_code
                playbook_code = actual_playbook_code
                logger.debug(
                    "Extracted capability_code=%s, playbook_code=%s from combined code",
                    capability_code,
                    playbook_code,
                )
            elif capability_code == potential_capability_code:
                playbook_code = actual_playbook_code
                logger.debug(
                    "Extracted playbook_code=%s from combined code (capability_code already provided)",
                    playbook_code,
                )
            else:
                logger.debug(
                    "Capability code mismatch: provided=%s, extracted=%s, keeping original playbook_code",
                    capability_code,
                    potential_capability_code,
                )

    return requested_playbook_code, playbook_code, capability_code, resolved_capability


async def resolve_registry_playbook(
    registry: Any,
    *,
    playbook_code: str,
    locale: str,
    workspace_id: Optional[str],
    capability_code: Optional[str],
    logger: logging.Logger,
) -> Optional[Playbook]:
    """Resolve one playbook through the canonical PlaybookRegistry facade state."""
    (
        requested_playbook_code,
        playbook_code,
        capability_code,
        resolved_capability,
    ) = resolve_playbook_lookup_request(
        playbook_code=playbook_code,
        capability_code=capability_code,
        capability_playbooks=registry.capability_playbooks,
        logger=logger,
    )

    if workspace_id:
        await registry._ensure_user_playbooks_loaded()

    if resolved_capability:
        cached = registry._get_cached_capability_playbook(
            resolved_capability, playbook_code, locale
        )
        if cached:
            return cached

        direct_capability_dir = registry._get_capabilities_dir() / resolved_capability
        if direct_capability_dir.is_dir():
            direct_playbook = registry._load_direct_capability_playbook(
                direct_capability_dir, playbook_code, locale
            )
            if direct_playbook:
                return direct_playbook
    else:
        direct_capability_dir = registry._find_capability_dir_for_playbook(
            playbook_code, locale
        )
        if direct_capability_dir is not None:
            direct_playbook = registry._load_direct_capability_playbook(
                direct_capability_dir, playbook_code, locale
            )
            if direct_playbook:
                return direct_playbook

        direct_system_playbook = registry._load_direct_system_playbook(
            playbook_code, locale
        )
        if direct_system_playbook:
            return direct_system_playbook

    if resolved_capability:
        await registry._ensure_capability_loaded(resolved_capability)
    else:
        await registry._ensure_loaded()

    logger.debug(
        "PlaybookRegistry.get_playbook: code=%s, locale=%s, workspace_id=%s, capability_code=%s",
        playbook_code,
        locale,
        workspace_id,
        capability_code,
    )
    logger.debug("Available system locales: %s", list(registry.system_playbooks.keys()))
    logger.debug(
        "Available capability packs: %s",
        list(registry.capability_playbooks.keys()),
    )
    logger.debug("Available user workspaces: %s", list(registry.user_playbooks.keys()))

    local_playbook = lookup_local_playbook(
        system_playbooks=registry.system_playbooks,
        capability_playbooks=registry.capability_playbooks,
        user_playbooks=registry.user_playbooks,
        playbook_code=playbook_code,
        locale=locale,
        workspace_id=workspace_id,
        capability_code=capability_code,
        logger=logger,
    )
    if local_playbook:
        return local_playbook

    if capability_code and registry.cloud_extension_manager:
        try:
            playbook_data = (
                await registry.cloud_extension_manager.get_playbook_from_any_provider(
                    capability_code, playbook_code, locale
                )
            )
            if playbook_data:
                content = playbook_data.get("content")
                if content:
                    playbook = PlaybookFileLoader.load_playbook_from_content(
                        content, playbook_code=playbook_code, locale=locale
                    )
                    if playbook:
                        playbook.metadata.capability_code = capability_code
                        provider_id = playbook_data.get("provider_id", "unknown")
                        cache_key = (
                            f"{provider_id}:{capability_code}:{playbook_code}:{locale}"
                        )
                        registry.cloud_playbooks[cache_key] = playbook
                        logger.info(
                            "Loaded cloud playbook: %s.%s (%s) from %s",
                            capability_code,
                            playbook_code,
                            locale,
                            provider_id,
                        )
                        return playbook
        except Exception as exc:
            logger.warning(
                "Failed to load cloud playbook %s.%s: %s",
                capability_code,
                playbook_code,
                exc,
            )

    logger.warning(
        "Playbook %s not found (locale=%s, workspace_id=%s, capability_code=%s)",
        requested_playbook_code,
        locale,
        workspace_id,
        capability_code,
    )
    return None


def collect_playbook_metadata(
    *,
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    system_playbooks: Dict[str, Dict[str, Playbook]],
    user_playbooks: Dict[str, Dict[str, Playbook]],
    workspace_id: Optional[str],
    locale: Optional[str],
    category: Optional[str],
    source_value: Optional[str],
    tags: Optional[List[str]],
    matches_filters_fn: Callable[..., bool],
) -> List[PlaybookMetadata]:
    """Collect playbook metadata across registry sources with dedupe."""
    playbooks_map: Dict[str, PlaybookMetadata] = {}
    locales_to_check = [locale] if locale else ["zh-TW", "en", "ja"]

    if not source_value or source_value in {"capability", "system"}:
        for playbooks_dict in capability_playbooks.values():
            for playbook in playbooks_dict.values():
                if not matches_filters_fn(playbook, category, tags):
                    continue
                if locale and playbook.metadata.locale != locale:
                    continue
                key = f"{playbook.metadata.playbook_code}:{playbook.metadata.locale}"
                playbooks_map.setdefault(key, playbook.metadata)

    if not source_value or source_value == "system":
        for current_locale in locales_to_check:
            if current_locale not in system_playbooks:
                continue
            for playbook in system_playbooks[current_locale].values():
                if not matches_filters_fn(playbook, category, tags):
                    continue
                key = f"{playbook.metadata.playbook_code}:{playbook.metadata.locale}"
                playbooks_map.setdefault(key, playbook.metadata)

    if (
        (not source_value or source_value == "user")
        and workspace_id
        and workspace_id in user_playbooks
    ):
        for playbook in user_playbooks[workspace_id].values():
            if not matches_filters_fn(playbook, category, tags):
                continue
            if locale and playbook.metadata.locale != locale:
                continue
            key = f"{playbook.metadata.playbook_code}:{playbook.metadata.locale}"
            playbooks_map.setdefault(key, playbook.metadata)

    return list(playbooks_map.values())
