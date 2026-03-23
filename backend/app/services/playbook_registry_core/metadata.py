"""Metadata and user-playbook helpers for PlaybookRegistry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from backend.app.models.playbook import Playbook
from backend.app.services.playbook_loaders import PlaybookDatabaseLoader


def _resolve_localized_value(value, locale: str):
    if not isinstance(value, dict):
        return value
    if not value:
        return None
    return value.get(locale) or value.get("en") or next(iter(value.values()))


def enrich_playbook_metadata(
    playbook: Playbook,
    capability_dir: Path,
    playbook_code: str,
    locale: str,
    *,
    logger: logging.Logger,
) -> None:
    """Enrich a playbook from a nearby JSON spec when available."""
    possible_json_paths = [
        capability_dir / "playbooks" / "specs" / f"{playbook_code}.json",
        capability_dir / "playbooks" / f"{playbook_code}.json",
        capability_dir / "specs" / f"{playbook_code}.json",
        capability_dir / f"{playbook_code}.json",
    ]

    for json_path in possible_json_paths:
        if not json_path.exists():
            continue

        try:
            with open(json_path, "r", encoding="utf-8") as handle:
                spec = json.load(handle)

            name = _resolve_localized_value(spec.get("display_name", {}), locale)
            if name:
                playbook.metadata.name = name

            description = _resolve_localized_value(spec.get("description"), locale)
            if description:
                playbook.metadata.description = description

            logger.debug(
                "Enriched metadata for %s from %s", playbook_code, json_path.name
            )
            return
        except Exception as exc:
            logger.debug("Failed to enrich metadata from %s: %s", json_path, exc)


def load_user_playbooks(
    *,
    store,
    user_playbooks: Dict[str, Dict[str, Playbook]],
    logger: logging.Logger,
) -> None:
    """Load user-defined playbooks from the configured store."""
    if not store:
        return

    try:
        db_path = store.db_path if hasattr(store, "db_path") else None
        if not db_path:
            logger.warning("Cannot load user playbooks: store has no db_path")
            return

        db_playbooks = PlaybookDatabaseLoader.load_playbooks_from_db(db_path)
        workspace_playbooks = user_playbooks.setdefault("default", {})

        for playbook in db_playbooks:
            playbook_code = playbook.metadata.playbook_code
            locale = playbook.metadata.locale
            workspace_playbooks[playbook_code] = playbook
            logger.debug(
                "Loaded user playbook: %s (locale: %s)", playbook_code, locale
            )

        logger.info(
            "Loaded %s user playbooks from database",
            sum(len(playbooks) for playbooks in user_playbooks.values()),
        )
    except Exception as exc:
        logger.warning("Failed to load user playbooks: %s", exc, exc_info=True)


def matches_filters(
    playbook: Playbook,
    category: Optional[str] = None,
    tags: Optional[List[str]] = None,
) -> bool:
    """Check whether a playbook matches category and tag filters."""
    if category and category not in playbook.metadata.tags:
        return False
    if tags and not any(tag in playbook.metadata.tags for tag in tags):
        return False
    return True
