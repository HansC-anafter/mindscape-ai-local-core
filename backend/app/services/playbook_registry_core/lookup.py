"""Lookup helpers for PlaybookRegistry."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import yaml

from backend.app.models.playbook import (
    Playbook,
    PlaybookOwnerType,
    PlaybookVisibility,
)
from backend.app.services.playbook_loaders import PlaybookFileLoader


def parse_variants(
    playbook_variants: Dict[str, List[Dict[str, Any]]],
    playbook_config: dict,
    capability_code: str,
    playbook_code: str,
    *,
    logger: logging.Logger,
) -> None:
    """Parse and cache manifest-declared playbook variants."""
    full_code = f"{capability_code}.{playbook_code}"
    variants_raw = playbook_config.get("variants", [])
    if not variants_raw or not isinstance(variants_raw, list):
        playbook_variants.pop(full_code, None)
        playbook_variants.pop(playbook_code, None)
        return

    from backend.app.models.playbook_models.playbook_variant import PlaybookVariant

    parsed = []
    for variant_payload in variants_raw:
        if (
            not isinstance(variant_payload, dict)
            or "variant_id" not in variant_payload
        ):
            continue

        try:
            variant = PlaybookVariant(
                variant_id=variant_payload["variant_id"],
                playbook_code=full_code,
                name=variant_payload.get("name", variant_payload["variant_id"]),
                description=variant_payload.get("description"),
                skip_steps=variant_payload.get("skip_steps", []),
                custom_checklist=variant_payload.get("custom_checklist", []),
                execution_params=variant_payload.get("execution_params", {}),
                conditions=variant_payload.get("conditions"),
            )
            normalized = variant.to_runner_dict()
            normalized["variant_id"] = variant.variant_id
            normalized["name"] = variant.name
            parsed.append(normalized)
        except Exception as exc:
            logger.warning(
                "Failed to parse variant '%s' for %s: %s",
                variant_payload.get("variant_id"),
                full_code,
                exc,
            )

    if parsed:
        playbook_variants[full_code] = parsed
        playbook_variants[playbook_code] = parsed
        logger.info("Loaded %s variant(s) for playbook %s", len(parsed), full_code)
        return

    playbook_variants.pop(full_code, None)
    playbook_variants.pop(playbook_code, None)


def get_variant(
    playbook_variants: Dict[str, List[Dict[str, Any]]],
    playbook_code: str,
    variant_id: str,
) -> Optional[Dict[str, Any]]:
    """Return a single variant payload for the requested playbook code."""
    variants = playbook_variants.get(playbook_code, [])
    for variant_payload in variants:
        if variant_payload.get("variant_id") == variant_id:
            return variant_payload
    return None


def list_variants(
    playbook_variants: Dict[str, List[Dict[str, Any]]],
    playbook_code: str,
) -> List[Dict[str, Any]]:
    """List all variant payloads for a playbook code."""
    return list(playbook_variants.get(playbook_code, []))


def get_cached_capability_playbook(
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    capability_code: str,
    playbook_code: str,
    locale: str,
) -> Optional[Playbook]:
    """Return a cached capability playbook if the locale-specific entry exists."""
    playbooks = capability_playbooks.get(capability_code)
    if not playbooks:
        return None

    full_code_locale_key = f"{capability_code}.{playbook_code}:{locale}"
    if full_code_locale_key in playbooks:
        return playbooks[full_code_locale_key]

    locale_key = f"{playbook_code}:{locale}"
    if locale_key in playbooks:
        return playbooks[locale_key]

    full_code = f"{capability_code}.{playbook_code}"
    found_playbook = playbooks.get(full_code)
    if found_playbook and found_playbook.metadata.locale == locale:
        return found_playbook

    found_playbook = playbooks.get(playbook_code)
    if found_playbook and found_playbook.metadata.locale == locale:
        return found_playbook

    return None


def cache_capability_playbook(
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    capability_code: str,
    playbook_code: str,
    locale: str,
    playbook: Playbook,
) -> None:
    """Cache a capability playbook under locale-aware and legacy keys."""
    if capability_code not in capability_playbooks:
        capability_playbooks[capability_code] = {}

    full_code = f"{capability_code}.{playbook_code}"
    locale_key = f"{playbook_code}:{locale}"
    full_code_locale_key = f"{full_code}:{locale}"
    capability_playbooks[capability_code][full_code] = playbook
    capability_playbooks[capability_code][locale_key] = playbook
    capability_playbooks[capability_code][full_code_locale_key] = playbook

    if playbook_code not in capability_playbooks[capability_code]:
        capability_playbooks[capability_code][playbook_code] = playbook
        return

    existing = capability_playbooks[capability_code][playbook_code]
    locale_priority = {"zh-TW": 3, "en": 2, "ja": 1}
    if locale_priority.get(locale, 0) > locale_priority.get(
        existing.metadata.locale, 0
    ):
        capability_playbooks[capability_code][playbook_code] = playbook


def find_capability_dir_for_playbook(
    capabilities_dir: Path,
    playbook_code: str,
    locale: str,
) -> Optional[Path]:
    """Find a local capability directory that contains the requested playbook."""
    if not capabilities_dir.exists():
        return None

    for capability_dir in capabilities_dir.iterdir():
        if not capability_dir.is_dir():
            continue
        playbook_path = capability_dir / "playbooks" / locale / f"{playbook_code}.md"
        if playbook_path.exists():
            return capability_dir
    return None


def load_direct_capability_playbook(
    *,
    capability_dir: Path,
    playbook_code: str,
    locale: str,
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    loaded_capabilities: Set[str],
    enrich_playbook_metadata: Callable[[Playbook, Path, str, str], None],
    cache_playbook: Callable[[str, str, str, Playbook], None],
    parse_variants_fn: Callable[[dict, str, str], None],
    logger: logging.Logger,
) -> Optional[Playbook]:
    """Load a single capability playbook directly from its manifest path."""
    manifest_path = capability_dir / "manifest.yaml"
    if not manifest_path.exists():
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle) or {}
    except Exception as exc:
        logger.debug("Failed to parse manifest %s: %s", manifest_path, exc)
        return None

    capability_code = manifest.get("code") or capability_dir.name
    playbooks_config = manifest.get("playbooks", []) or []
    for playbook_config in playbooks_config:
        configured_code = playbook_config.get("code")
        if configured_code != playbook_code:
            continue

        path_template = playbook_config.get("path", "playbooks/{locale}/{code}.md")
        playbook_path = capability_dir / path_template.format(
            locale=locale,
            code=playbook_code,
        )
        if not playbook_path.exists():
            return None

        playbook = PlaybookFileLoader.load_playbook_from_file(playbook_path)
        if not playbook:
            return None

        playbook.metadata.locale = locale
        playbook.metadata.capability_code = capability_code
        playbook.metadata.owner_type = PlaybookOwnerType.SYSTEM
        playbook.metadata.owner_id = "system"
        playbook.metadata.visibility = PlaybookVisibility.WORKSPACE_SHARED

        enrich_playbook_metadata(playbook, capability_dir, playbook_code, locale)
        cache_playbook(capability_code, playbook_code, locale, playbook)
        parse_variants_fn(playbook_config, capability_code, playbook_code)
        loaded_capabilities.add(capability_code)
        return playbook

    return None


def load_direct_system_playbook(
    *,
    system_playbooks: Dict[str, Dict[str, Playbook]],
    i18n_dir: Path,
    playbook_code: str,
    locale: str,
) -> Optional[Playbook]:
    """Load a system playbook directly from the i18n directory."""
    if locale in system_playbooks and playbook_code in system_playbooks[locale]:
        return system_playbooks[locale][playbook_code]

    playbook_path = i18n_dir / locale / f"{playbook_code}.md"
    if not playbook_path.exists():
        return None

    playbook = PlaybookFileLoader.load_playbook_from_file(playbook_path)
    if not playbook:
        return None

    playbook.metadata.locale = locale
    playbook.metadata.owner_type = PlaybookOwnerType.SYSTEM
    playbook.metadata.owner_id = "system"
    playbook.metadata.visibility = PlaybookVisibility.WORKSPACE_SHARED

    if locale not in system_playbooks:
        system_playbooks[locale] = {}
    system_playbooks[locale][playbook_code] = playbook
    return playbook
