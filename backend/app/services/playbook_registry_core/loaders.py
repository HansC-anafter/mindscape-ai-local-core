"""Source loaders for PlaybookRegistry."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

import yaml

from backend.app.models.playbook import (
    Playbook,
    PlaybookOwnerType,
    PlaybookVisibility,
)
from backend.app.services.playbook_loaders import PlaybookFileLoader

EnrichPlaybook = Callable[[Playbook, Path, str, str], None]
ParseVariants = Callable[[dict, str, str], None]
RecordActivation = Callable[..., None]


def load_system_playbooks(
    *,
    registry_file: Path,
    system_playbooks: Dict[str, Dict[str, Playbook]],
    enrich_playbook_metadata: EnrichPlaybook,
    logger: logging.Logger,
) -> None:
    """
    Load system-level playbooks from NPM packages and backend/i18n/playbooks.
    """
    try:
        from backend.app.services.playbook_loaders.npm_loader import (
            PlaybookNpmLoader,
        )

        packages = PlaybookNpmLoader.find_playbook_packages()
        supported_locales = ["zh-TW", "en", "ja"]

        for package in packages:
            playbook_code = package["playbook_code"]

            for locale in supported_locales:
                if locale not in system_playbooks:
                    system_playbooks[locale] = {}

                i18n_content = PlaybookNpmLoader.load_playbook_i18n(
                    playbook_code, locale
                )
                if not i18n_content:
                    continue

                try:
                    with tempfile.NamedTemporaryFile(
                        mode="w", suffix=".md", delete=False, encoding="utf-8"
                    ) as tmp_file:
                        tmp_file.write(i18n_content)
                        tmp_path = Path(tmp_file.name)

                    playbook = PlaybookFileLoader.load_playbook_from_file(tmp_path)
                    if playbook:
                        playbook.metadata.locale = locale
                        if playbook_code not in system_playbooks[locale]:
                            system_playbooks[locale][playbook_code] = playbook
                            logger.debug(
                                "Loaded playbook from NPM package: %s (%s)",
                                playbook_code,
                                locale,
                            )

                    tmp_path.unlink()
                except Exception as exc:
                    logger.warning(
                        "Failed to load playbook from NPM package %s: %s",
                        package["name"],
                        exc,
                    )
    except Exception as exc:
        logger.debug("Failed to load playbooks from NPM packages: %s", exc)

    base_dir = registry_file.parent.parent.parent.parent
    i18n_dir = base_dir / "backend" / "i18n" / "playbooks"

    if not i18n_dir.exists():
        logger.warning("System playbooks directory does not exist: %s", i18n_dir)
        return

    supported_locales = ["zh-TW", "en", "ja"]
    app_dir = registry_file.parent.parent
    caps_dir = app_dir / "capabilities"

    for locale in supported_locales:
        locale_dir = i18n_dir / locale
        if not locale_dir.exists():
            continue

        if locale not in system_playbooks:
            system_playbooks[locale] = {}

        for md_file in locale_dir.glob("*.md"):
            if md_file.name == "README.md":
                continue

            try:
                playbook = PlaybookFileLoader.load_playbook_from_file(md_file)
                if not playbook:
                    continue

                playbook.metadata.locale = locale
                playbook.metadata.owner_type = PlaybookOwnerType.SYSTEM
                playbook.metadata.owner_id = "system"
                playbook.metadata.visibility = PlaybookVisibility.WORKSPACE_SHARED
                playbook_code = playbook.metadata.playbook_code

                _enrich_system_playbook_from_capabilities(
                    playbook=playbook,
                    playbook_code=playbook_code,
                    locale=locale,
                    caps_dir=caps_dir,
                    enrich_playbook_metadata=enrich_playbook_metadata,
                )

                if playbook_code not in system_playbooks[locale]:
                    system_playbooks[locale][playbook_code] = playbook
                    logger.debug(
                        "Loaded system playbook: %s (%s)",
                        playbook_code,
                        locale,
                    )
            except Exception as exc:
                logger.warning("Failed to load system playbook from %s: %s", md_file, exc)


def load_capability_playbooks(
    *,
    registry_file: Path,
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    loaded_capabilities: Set[str],
    enrich_playbook_metadata: EnrichPlaybook,
    parse_variants_fn: ParseVariants,
    record_activation: RecordActivation,
    logger: logging.Logger,
) -> Path:
    """
    Load capability pack playbooks from local app/capabilities only.
    """
    app_dir = registry_file.parent.parent
    local_capabilities_dir = app_dir / "capabilities"

    logger.info(
        "Checking capabilities directory: %s (exists: %s)",
        local_capabilities_dir,
        local_capabilities_dir.exists(),
    )
    if local_capabilities_dir.exists():
        logger.info("Loading local capability playbooks from %s", local_capabilities_dir)
        load_playbooks_from_directory(
            capabilities_dir=local_capabilities_dir,
            capability_playbooks=capability_playbooks,
            enrich_playbook_metadata=enrich_playbook_metadata,
            parse_variants_fn=parse_variants_fn,
            record_activation=record_activation,
            logger=logger,
        )
        for cap_code in list(capability_playbooks.keys()):
            loaded_capabilities.add(cap_code)
    else:
        logger.warning(
            "Local capabilities directory does not exist: %s",
            local_capabilities_dir,
        )

    return local_capabilities_dir


def load_single_capability(
    *,
    capability_dir: Path,
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    enrich_playbook_metadata: EnrichPlaybook,
    parse_variants_fn: ParseVariants,
    record_activation: RecordActivation,
    logger: logging.Logger,
) -> None:
    """
    Load playbooks from one capability directory for per-capability lazy loading.
    """
    manifest_path = capability_dir / "manifest.yaml"
    if not manifest_path.exists():
        logger.debug("No manifest.yaml found in %s, skipping", capability_dir.name)
        return

    try:
        with open(manifest_path, "r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle)

        capability_code = manifest.get("code")
        if not capability_code:
            logger.warning(
                "Manifest in %s missing 'code' field, skipping",
                capability_dir.name,
            )
            return

        logger.info("Lazy-loading capability pack: %s", capability_code)
        _load_manifest_playbooks(
            capability_dir=capability_dir,
            capability_code=capability_code,
            manifest=manifest,
            capability_playbooks=capability_playbooks,
            enrich_playbook_metadata=enrich_playbook_metadata,
            parse_variants_fn=parse_variants_fn,
            logger=logger,
        )

        if capability_playbooks.get(capability_code):
            record_activation(
                capability_code=capability_code,
                manifest=manifest,
                manifest_path=manifest_path,
            )
    except Exception as exc:
        logger.error("Failed to load capability %s: %s", capability_dir.name, exc)


def load_playbooks_from_directory(
    *,
    capabilities_dir: Path,
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    enrich_playbook_metadata: EnrichPlaybook,
    parse_variants_fn: ParseVariants,
    record_activation: RecordActivation,
    logger: logging.Logger,
) -> None:
    """Load playbooks from each capability directory under a local capabilities root."""
    for capability_dir in capabilities_dir.iterdir():
        if not capability_dir.is_dir():
            continue

        manifest_path = capability_dir / "manifest.yaml"
        if not manifest_path.exists():
            logger.debug("No manifest.yaml found in %s, skipping", capability_dir.name)
            continue

        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                manifest = yaml.safe_load(handle)

            capability_code = manifest.get("code")
            if not capability_code:
                logger.warning(
                    "Manifest in %s missing 'code' field, skipping",
                    capability_dir.name,
                )
                continue

            logger.info("Loading capability pack: %s", capability_code)
            _load_manifest_playbooks(
                capability_dir=capability_dir,
                capability_code=capability_code,
                manifest=manifest,
                capability_playbooks=capability_playbooks,
                enrich_playbook_metadata=enrich_playbook_metadata,
                parse_variants_fn=parse_variants_fn,
                logger=logger,
            )

            logger.info(
                "Loaded %s playbooks from %s",
                len(capability_playbooks[capability_code]),
                capability_code,
            )
            if capability_playbooks.get(capability_code):
                record_activation(
                    capability_code=capability_code,
                    manifest=manifest,
                    manifest_path=manifest_path,
                )
        except Exception as exc:
            logger.warning(
                "Failed to load capability pack from %s: %s",
                capability_dir.name,
                exc,
                exc_info=True,
            )


def reload_system_playbook(
    *,
    registry_file: Path,
    system_playbooks: Dict[str, Dict[str, Playbook]],
    playbook_code: str,
    locale: str,
    logger: logging.Logger,
) -> bool:
    """Reload one system playbook from backend/i18n/playbooks."""
    base_dir = registry_file.parent.parent.parent.parent
    i18n_dir = base_dir / "backend" / "i18n" / "playbooks"
    locale_dir = i18n_dir / locale

    if locale_dir.exists():
        if locale not in system_playbooks:
            system_playbooks[locale] = {}

        for md_file in locale_dir.glob("*.md"):
            if md_file.name == "README.md":
                continue

            try:
                playbook = PlaybookFileLoader.load_playbook_from_file(md_file)
                if playbook and playbook.metadata.playbook_code == playbook_code:
                    playbook.metadata.locale = locale
                    system_playbooks[locale][playbook_code] = playbook
                    logger.info("Reloaded playbook: %s (%s)", playbook_code, locale)
                    return True
            except Exception as exc:
                logger.warning("Failed to reload playbook from %s: %s", md_file, exc)

    logger.warning("Failed to reload playbook %s (locale: %s)", playbook_code, locale)
    return False


def _enrich_system_playbook_from_capabilities(
    *,
    playbook: Playbook,
    playbook_code: str,
    locale: str,
    caps_dir: Path,
    enrich_playbook_metadata: EnrichPlaybook,
) -> None:
    if not caps_dir.exists():
        return

    for cap_dir in caps_dir.iterdir():
        if not cap_dir.is_dir():
            continue
        cap_name = cap_dir.name
        if playbook_code.startswith(f"{cap_name}_") or playbook_code.startswith(
            f"{cap_name}."
        ):
            enrich_playbook_metadata(playbook, cap_dir, playbook_code, locale)
            if playbook.metadata.description:
                return

    for cap_dir in caps_dir.iterdir():
        if not cap_dir.is_dir():
            continue
        enrich_playbook_metadata(playbook, cap_dir, playbook_code, locale)
        if playbook.metadata.description:
            return


def _load_manifest_playbooks(
    *,
    capability_dir: Path,
    capability_code: str,
    manifest: Dict[str, Any],
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    enrich_playbook_metadata: EnrichPlaybook,
    parse_variants_fn: ParseVariants,
    logger: logging.Logger,
) -> None:
    if capability_code not in capability_playbooks:
        capability_playbooks[capability_code] = {}

    playbooks_config = manifest.get("playbooks", [])
    for playbook_config in playbooks_config:
        playbook_code = playbook_config.get("code")
        if not playbook_code:
            continue

        locales = playbook_config.get("locales", ["zh-TW", "en"])
        path_template = playbook_config.get("path", "playbooks/{locale}/{code}.md")

        for locale in locales:
            playbook_path = capability_dir / path_template.format(
                locale=locale,
                code=playbook_code,
            )
            if not playbook_path.exists():
                logger.debug("Playbook file not found: %s", playbook_path)
                continue

            try:
                playbook = PlaybookFileLoader.load_playbook_from_file(playbook_path)
                if not playbook:
                    continue

                playbook.metadata.locale = locale
                playbook.metadata.capability_code = capability_code
                playbook.metadata.owner_type = PlaybookOwnerType.SYSTEM
                playbook.metadata.owner_id = "system"
                playbook.metadata.visibility = PlaybookVisibility.WORKSPACE_SHARED

                enrich_playbook_metadata(playbook, capability_dir, playbook_code, locale)
                _cache_manifest_playbook(
                    capability_playbooks=capability_playbooks,
                    capability_code=capability_code,
                    playbook_code=playbook_code,
                    locale=locale,
                    playbook=playbook,
                )
                logger.debug(
                    "Loaded capability playbook: %s.%s (%s) from %s",
                    capability_code,
                    playbook_code,
                    locale,
                    capability_code,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to load playbook %s (%s) from %s: %s",
                    playbook_code,
                    locale,
                    capability_code,
                    exc,
                )

        parse_variants_fn(playbook_config, capability_code, playbook_code)


def _cache_manifest_playbook(
    *,
    capability_playbooks: Dict[str, Dict[str, Playbook]],
    capability_code: str,
    playbook_code: str,
    locale: str,
    playbook: Playbook,
) -> None:
    playbooks = capability_playbooks[capability_code]
    full_code = f"{capability_code}.{playbook_code}"
    locale_key = f"{playbook_code}:{locale}"
    playbooks[full_code] = playbook
    playbooks[locale_key] = playbook

    if playbook_code not in playbooks:
        playbooks[playbook_code] = playbook
        return

    existing = playbooks[playbook_code]
    locale_priority = {"zh-TW": 3, "en": 2, "ja": 1}
    if locale_priority.get(locale, 0) > locale_priority.get(
        existing.metadata.locale, 0
    ):
        playbooks[playbook_code] = playbook
