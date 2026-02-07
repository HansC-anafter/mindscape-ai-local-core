"""
Playbook Registry
Unified registry for all playbooks (system, capability, user)
Supports lazy loading to avoid startup overhead
"""

import os
import logging
from typing import Dict, List, Optional
from pathlib import Path
from enum import Enum

from backend.app.models.playbook import (
    Playbook,
    PlaybookMetadata,
    PlaybookOwnerType,
    PlaybookVisibility,
)
from backend.app.services.playbook_loaders import (
    PlaybookFileLoader,
    PlaybookDatabaseLoader,
)

logger = logging.getLogger(__name__)

# Optional import for cloud extension support
try:
    from backend.app.services.cloud_extension_manager import CloudExtensionManager
except ImportError:
    CloudExtensionManager = None


class PlaybookSource(str, Enum):
    """Playbook source type"""

    SYSTEM = "system"  # System-level playbooks
    CAPABILITY = "capability"  # Capability pack playbooks
    USER = "user"  # User-defined playbooks


class PlaybookRegistry:
    """
    Unified registry for all playbooks
    Similar to Intent Registry, provides unified query interface
    """

    def __init__(self, store=None, cloud_client=None, cloud_extension_manager=None):
        """
        Initialize PlaybookRegistry

        Args:
            store: MindscapeStore instance (optional, for user playbooks)
            cloud_client: CloudPlaybookClient instance (optional, deprecated - use cloud_extension_manager)
            cloud_extension_manager: CloudExtensionManager instance (optional, for cloud playbooks from multiple providers)
        """
        self.store = store

        # Support both old cloud_client and new cloud_extension_manager for backward compatibility
        if cloud_extension_manager:
            self.cloud_extension_manager = cloud_extension_manager
        elif cloud_client:
            # Legacy support: try to get extension manager from cloud_client
            self.cloud_extension_manager = None
            logger.warning(
                "Using deprecated cloud_client parameter. Please migrate to cloud_extension_manager."
            )
        else:
            self.cloud_extension_manager = None

        # Cache: locale -> code -> playbook
        self.system_playbooks: Dict[str, Dict[str, Playbook]] = {}
        # Cache: capability_code -> code -> playbook
        self.capability_playbooks: Dict[str, Dict[str, Playbook]] = {}
        # Cache: workspace_id -> code -> playbook
        self.user_playbooks: Dict[str, Dict[str, Playbook]] = {}
        # Cache: cloud playbooks (provider_id:capability_code:playbook_code:locale -> playbook)
        self.cloud_playbooks: Dict[str, Playbook] = {}

        # Lazy loading flag
        self._loaded = False

    async def _ensure_loaded(self):
        """Ensure playbooks are loaded (lazy loading)"""
        if not self._loaded:
            await self._load_all_playbooks()
            self._loaded = True

    async def _load_all_playbooks(self):
        """Load all playbooks from different sources"""
        logger.info("Loading playbooks from all sources...")

        # Load system-level playbooks first for core functionality
        self._load_system_playbooks()

        # Load capability playbooks for extended features
        self._load_capability_playbooks()

        # Load user-defined playbooks from database if store is available
        if self.store:
            self._load_user_playbooks()

        logger.info(
            f"Loaded {len(self.system_playbooks)} system playbook locales, "
            f"{len(self.capability_playbooks)} capability packs"
        )

    def _load_system_playbooks(self):
        """
        Load system-level playbooks from:
        1. NPM packages (@mindscape/playbook-*)
        2. backend/i18n/playbooks/ (backward compatibility)
        """
        # First try loading from NPM packages
        try:
            from backend.app.services.playbook_loaders.npm_loader import (
                PlaybookNpmLoader,
            )

            packages = PlaybookNpmLoader.find_playbook_packages()

            supported_locales = ["zh-TW", "en", "ja"]

            for package in packages:
                playbook_code = package["playbook_code"]

                for locale in supported_locales:
                    if locale not in self.system_playbooks:
                        self.system_playbooks[locale] = {}

                    # Try to load i18n from NPM package
                    i18n_content = PlaybookNpmLoader.load_playbook_i18n(
                        playbook_code, locale
                    )
                    if i18n_content:
                        try:
                            from io import StringIO

                            # Create a temporary file-like object for PlaybookFileLoader
                            # PlaybookFileLoader expects a Path, so we need to write to temp file
                            import tempfile

                            with tempfile.NamedTemporaryFile(
                                mode="w", suffix=".md", delete=False, encoding="utf-8"
                            ) as tmp_file:
                                tmp_file.write(i18n_content)
                                tmp_path = Path(tmp_file.name)

                            playbook = PlaybookFileLoader.load_playbook_from_file(
                                tmp_path
                            )
                            if playbook:
                                playbook.metadata.locale = locale
                                if playbook_code not in self.system_playbooks[locale]:
                                    self.system_playbooks[locale][
                                        playbook_code
                                    ] = playbook
                                    logger.debug(
                                        f"Loaded playbook from NPM package: {playbook_code} ({locale})"
                                    )

                            # Clean up temp file
                            tmp_path.unlink()
                        except Exception as e:
                            logger.warning(
                                f"Failed to load playbook from NPM package {package['name']}: {e}"
                            )
        except Exception as e:
            logger.debug(f"Failed to load playbooks from NPM packages: {e}")

        # Fallback to core i18n directory (backward compatibility)
        base_dir = Path(__file__).parent.parent.parent.parent
        i18n_dir = base_dir / "backend" / "i18n" / "playbooks"

        if not i18n_dir.exists():
            logger.warning(f"System playbooks directory does not exist: {i18n_dir}")
            return

        # Supported locales
        supported_locales = ["zh-TW", "en", "ja"]

        for locale in supported_locales:
            locale_dir = i18n_dir / locale
            if not locale_dir.exists():
                continue

            if locale not in self.system_playbooks:
                self.system_playbooks[locale] = {}

            # Load .md files from locale directory
            for md_file in locale_dir.glob("*.md"):
                if md_file.name == "README.md":
                    continue

                try:
                    playbook = PlaybookFileLoader.load_playbook_from_file(md_file)
                    if playbook:
                        # Ensure locale matches directory
                        playbook.metadata.locale = locale
                        playbook.metadata.owner_type = PlaybookOwnerType.SYSTEM
                        playbook.metadata.owner_id = "system"
                        playbook.metadata.visibility = (
                            PlaybookVisibility.WORKSPACE_SHARED
                        )
                        playbook_code = playbook.metadata.playbook_code

                        # Try to enrich from capability directory if applicable
                        # Dynamically discover capability directories - NO HARDCODED PACK NAMES
                        app_dir = Path(__file__).parent.parent
                        caps_dir = app_dir / "capabilities"

                        # Try to infer capability from playbook_code prefix (e.g., "ig_analyze_following" -> "ig")
                        # Scan all capability directories, no hardcoded list
                        if caps_dir.exists():
                            for cap_dir in caps_dir.iterdir():
                                if not cap_dir.is_dir():
                                    continue
                                cap_name = cap_dir.name
                                # Check if playbook_code starts with this capability name
                                if playbook_code.startswith(
                                    f"{cap_name}_"
                                ) or playbook_code.startswith(f"{cap_name}."):
                                    self._enrich_playbook_metadata(
                                        playbook, cap_dir, playbook_code, locale
                                    )
                                    if playbook.metadata.description:
                                        break
                            else:
                                # Fallback: search all capability dirs for matching JSON spec
                                for cap_dir in caps_dir.iterdir():
                                    if not cap_dir.is_dir():
                                        continue
                                    self._enrich_playbook_metadata(
                                        playbook, cap_dir, playbook_code, locale
                                    )
                                    if playbook.metadata.description:
                                        break

                        # Only add if not already loaded from NPM package
                        if playbook_code not in self.system_playbooks[locale]:
                            self.system_playbooks[locale][playbook_code] = playbook
                            logger.debug(
                                f"Loaded system playbook: {playbook_code} ({locale})"
                            )
                except Exception as e:
                    logger.warning(
                        f"Failed to load system playbook from {md_file}: {e}"
                    )

    def _load_capability_playbooks(self):
        """
        Load capability pack playbooks from local capabilities directory only

        Each capability pack has a manifest.yaml that defines:
        - playbooks: list of playbook definitions with code, locales, and path
        - flows: list of flow definitions

        Remote capabilities should be accessed via cloud_extension_manager.
        """
        import yaml

        # Load from local capabilities directory only
        # Path calculation: __file__ is in app/services/playbook_registry.py
        # parent = services/, parent.parent = app/, so app/capabilities
        app_dir = Path(__file__).parent.parent  # app/
        local_capabilities_dir = app_dir / "capabilities"  # app/capabilities
        logger.info(
            f"Checking capabilities directory: {local_capabilities_dir} (exists: {local_capabilities_dir.exists()})"
        )
        if local_capabilities_dir.exists():
            logger.info(
                f"Loading local capability playbooks from {local_capabilities_dir}"
            )
            self._load_playbooks_from_directory(local_capabilities_dir)
        else:
            logger.warning(
                f"Local capabilities directory does not exist: {local_capabilities_dir}"
            )

    def _load_playbooks_from_directory(self, capabilities_dir: Path):
        """Load playbooks from a capabilities directory"""
        import yaml

        for capability_dir in capabilities_dir.iterdir():
            if not capability_dir.is_dir():
                continue

            manifest_path = capability_dir / "manifest.yaml"
            if not manifest_path.exists():
                logger.debug(
                    f"No manifest.yaml found in {capability_dir.name}, skipping"
                )
                continue

            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = yaml.safe_load(f)

                capability_code = manifest.get("code")
                if not capability_code:
                    logger.warning(
                        f"Manifest in {capability_dir.name} missing 'code' field, skipping"
                    )
                    continue

                logger.info(f"Loading capability pack: {capability_code}")

                if capability_code not in self.capability_playbooks:
                    self.capability_playbooks[capability_code] = {}

                playbooks_config = manifest.get("playbooks", [])
                for playbook_config in playbooks_config:
                    playbook_code = playbook_config.get("code")
                    if not playbook_code:
                        continue

                    locales = playbook_config.get("locales", ["zh-TW", "en"])
                    path_template = playbook_config.get(
                        "path", "playbooks/{locale}/{code}.md"
                    )

                    for locale in locales:
                        playbook_path = capability_dir / path_template.format(
                            locale=locale, code=playbook_code
                        )

                        if not playbook_path.exists():
                            logger.debug(f"Playbook file not found: {playbook_path}")
                            continue

                        try:
                            playbook = PlaybookFileLoader.load_playbook_from_file(
                                playbook_path
                            )
                            if playbook:
                                playbook.metadata.locale = locale
                                playbook.metadata.capability_code = capability_code
                                playbook.metadata.owner_type = PlaybookOwnerType.SYSTEM
                                playbook.metadata.owner_id = "system"
                                playbook.metadata.visibility = (
                                    PlaybookVisibility.WORKSPACE_SHARED
                                )

                                # Enrich metadata from JSON spec if available
                                self._enrich_playbook_metadata(
                                    playbook, capability_dir, playbook_code, locale
                                )

                                full_code = f"{capability_code}.{playbook_code}"
                                # Store with locale-specific key to avoid overwriting
                                locale_key = f"{playbook_code}:{locale}"
                                self.capability_playbooks[capability_code][
                                    full_code
                                ] = playbook
                                self.capability_playbooks[capability_code][
                                    locale_key
                                ] = playbook
                                # Also store without locale for backward compatibility (prefer zh-TW, then en, then any)
                                if (
                                    playbook_code
                                    not in self.capability_playbooks[capability_code]
                                ):
                                    self.capability_playbooks[capability_code][
                                        playbook_code
                                    ] = playbook
                                else:
                                    # Prefer zh-TW > en > others
                                    existing = self.capability_playbooks[
                                        capability_code
                                    ][playbook_code]
                                    existing_locale = existing.metadata.locale
                                    locale_priority = {"zh-TW": 3, "en": 2, "ja": 1}
                                    if locale_priority.get(
                                        locale, 0
                                    ) > locale_priority.get(existing_locale, 0):
                                        self.capability_playbooks[capability_code][
                                            playbook_code
                                        ] = playbook
                                logger.debug(
                                    f"Loaded capability playbook: {full_code} ({locale}) from {capability_code}"
                                )
                        except Exception as e:
                            logger.warning(
                                f"Failed to load playbook {playbook_code} ({locale}) from {capability_code}: {e}"
                            )

                logger.info(
                    f"Loaded {len(self.capability_playbooks[capability_code])} playbooks from {capability_code}"
                )

            except Exception as e:
                logger.warning(
                    f"Failed to load capability pack from {capability_dir.name}: {e}",
                    exc_info=True,
                )

    def _enrich_playbook_metadata(
        self, playbook, capability_dir: Path, playbook_code: str, locale: str
    ):
        """Try to enrich playbook metadata from coordinate JSON spec file"""
        import json

        possible_json_paths = [
            capability_dir / "playbooks" / "specs" / f"{playbook_code}.json",
            capability_dir / "playbooks" / f"{playbook_code}.json",
            capability_dir / "specs" / f"{playbook_code}.json",  # For system playbooks
            capability_dir / f"{playbook_code}.json",  # For system playbooks
        ]

        for json_path in possible_json_paths:
            if json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        spec = json.load(f)

                    # Extract display name for the locale
                    display_names = spec.get("display_name", {})
                    if isinstance(display_names, dict):
                        # Try current locale, then fallback to en, then first available
                        name = (
                            display_names.get(locale)
                            or display_names.get("en")
                            or next(iter(display_names.values()))
                            if display_names
                            else None
                        )
                        if name:
                            playbook.metadata.name = name

                    # Extract description
                    description = spec.get("description")
                    if description:
                        # If description is localized (dict), handle it similarly
                        if isinstance(description, dict):
                            description = (
                                description.get(locale)
                                or description.get("en")
                                or next(iter(description.values()))
                                if description
                                else None
                            )

                        if description:
                            playbook.metadata.description = description

                    logger.debug(
                        f"Enriched metadata for {playbook_code} from {json_path.name}"
                    )
                    return
                except Exception as e:
                    logger.debug(f"Failed to enrich metadata from {json_path}: {e}")

    def _load_user_playbooks(self):
        """Load user-defined playbooks from database"""
        if not self.store:
            return

        try:
            # Get database path from store
            db_path = self.store.db_path if hasattr(self.store, "db_path") else None
            if not db_path:
                logger.warning("Cannot load user playbooks: store has no db_path")
                return

            # Load playbooks directly from database
            db_playbooks = PlaybookDatabaseLoader.load_playbooks_from_db(db_path)

            for playbook in db_playbooks:
                workspace_key = "default"

                if workspace_key not in self.user_playbooks:
                    self.user_playbooks[workspace_key] = {}

                playbook_code = playbook.metadata.playbook_code
                locale = playbook.metadata.locale

                self.user_playbooks[workspace_key][playbook_code] = playbook
                logger.debug(
                    f"Loaded user playbook: {playbook_code} (locale: {locale})"
                )

            logger.info(
                f"Loaded {sum(len(pbs) for pbs in self.user_playbooks.values())} user playbooks from database"
            )
        except Exception as e:
            logger.warning(f"Failed to load user playbooks: {e}", exc_info=True)

    async def get_playbook(
        self,
        playbook_code: str,
        locale: str = "zh-TW",
        workspace_id: Optional[str] = None,
        capability_code: Optional[str] = None,
    ) -> Optional[Playbook]:
        """
        Unified lookup interface

        Lookup priority:
        1. User-defined playbook (if workspace_id provided)
        2. Capability playbook (local or cloud)
        3. System-level playbook
        4. Cloud playbook (if capability_code provided and cloud_client available)

        Args:
            playbook_code: Playbook code (supports format: "capability_code.playbook_code")
            locale: Locale code (default: "zh-TW")
            workspace_id: Workspace ID (optional)
            capability_code: Capability pack code (optional, for cloud playbooks)
                            If not provided and playbook_code contains ".", will be extracted from playbook_code
        """
        await self._ensure_loaded()

        # Support capability_code.playbook_code format
        # If playbook_code contains ".", try to extract capability_code
        if "." in playbook_code:
            parts = playbook_code.split(".", 1)
            if len(parts) == 2:
                potential_capability_code = parts[0]
                actual_playbook_code = parts[1]
                # Check if this looks like a capability code (not just a dot in the name)
                # Simple heuristic: if the first part matches a known capability pack, use it
                if potential_capability_code in self.capability_playbooks:
                    # If capability_code was not provided, use extracted one
                    # If capability_code was provided, verify it matches and use actual_playbook_code
                    if not capability_code:
                        capability_code = potential_capability_code
                        playbook_code = actual_playbook_code
                        logger.debug(
                            f"Extracted capability_code={capability_code}, playbook_code={playbook_code} from combined code"
                        )
                    elif capability_code == potential_capability_code:
                        # Capability code matches, use the extracted playbook_code
                        playbook_code = actual_playbook_code
                        logger.debug(
                            f"Extracted playbook_code={playbook_code} from combined code (capability_code already provided)"
                        )
                    else:
                        # Capability code mismatch, keep original playbook_code
                        logger.debug(
                            f"Capability code mismatch: provided={capability_code}, extracted={potential_capability_code}, keeping original playbook_code"
                        )

        logger.debug(
            f"PlaybookRegistry.get_playbook: code={playbook_code}, locale={locale}, workspace_id={workspace_id}, capability_code={capability_code}"
        )
        logger.debug(f"Available system locales: {list(self.system_playbooks.keys())}")
        logger.debug(
            f"Available capability packs: {list(self.capability_playbooks.keys())}"
        )
        logger.debug(f"Available user workspaces: {list(self.user_playbooks.keys())}")

        # 1. Check user playbooks
        if workspace_id and workspace_id in self.user_playbooks:
            if playbook_code in self.user_playbooks[workspace_id]:
                logger.debug(
                    f"Found playbook {playbook_code} in user playbooks for workspace {workspace_id}"
                )
                return self.user_playbooks[workspace_id][playbook_code]

        # 2. Check local capability playbooks
        # If capability_code is specified, check that specific capability first
        if capability_code and capability_code in self.capability_playbooks:
            # First try locale-specific key
            locale_key = f"{playbook_code}:{locale}"
            if locale_key in self.capability_playbooks[capability_code]:
                logger.debug(
                    f"Found playbook {playbook_code} ({locale}) in capability {capability_code}"
                )
                return self.capability_playbooks[capability_code][locale_key]
            # Then try full_code
            full_code = f"{capability_code}.{playbook_code}"
            if full_code in self.capability_playbooks[capability_code]:
                found_playbook = self.capability_playbooks[capability_code][full_code]
                # Check if locale matches
                if found_playbook.metadata.locale == locale:
                    logger.debug(
                        f"Found playbook {full_code} ({locale}) in capability {capability_code}"
                    )
                    return found_playbook
            # Fallback to playbook_code without locale
            if playbook_code in self.capability_playbooks[capability_code]:
                found_playbook = self.capability_playbooks[capability_code][
                    playbook_code
                ]
                # Check if locale matches
                if found_playbook.metadata.locale == locale:
                    logger.debug(
                        f"Found playbook {playbook_code} ({locale}) in capability {capability_code}"
                    )
                    return found_playbook
        # Otherwise, check all capabilities
        for cap_code, playbooks in self.capability_playbooks.items():
            # Try locale-specific key first
            locale_key = f"{playbook_code}:{locale}"
            if locale_key in playbooks:
                logger.debug(
                    f"Found playbook {playbook_code} ({locale}) in capability {cap_code}"
                )
                return playbooks[locale_key]
            # Then try full_code
            full_code = f"{cap_code}.{playbook_code}"
            if full_code in playbooks:
                found_playbook = playbooks[full_code]
                if found_playbook.metadata.locale == locale:
                    logger.debug(
                        f"Found playbook {full_code} ({locale}) in capability {cap_code}"
                    )
                    return found_playbook
            # Fallback to playbook_code
            if playbook_code in playbooks:
                found_playbook = playbooks[playbook_code]
                if found_playbook.metadata.locale == locale:
                    logger.debug(
                        f"Found playbook {playbook_code} ({locale}) in capability {cap_code}"
                    )
                    return found_playbook

        # 3. Check system playbooks
        if locale in self.system_playbooks:
            if playbook_code in self.system_playbooks[locale]:
                logger.debug(
                    f"Found playbook {playbook_code} in system playbooks for locale {locale}"
                )
                return self.system_playbooks[locale][playbook_code]
            else:
                logger.debug(
                    f"Playbook {playbook_code} not found in system playbooks for locale {locale}, available codes: {list(self.system_playbooks[locale].keys())}"
                )
        else:
            logger.debug(f"Locale {locale} not found in system playbooks")

        # 4. Try cloud playbook if capability_code provided
        if capability_code and self.cloud_extension_manager:
            # Try to get playbook from any configured provider
            try:
                playbook_data = (
                    await self.cloud_extension_manager.get_playbook_from_any_provider(
                        capability_code, playbook_code, locale
                    )
                )

                if playbook_data:
                    # Load playbook from content
                    content = playbook_data.get("content")
                    if content:
                        playbook = PlaybookFileLoader.load_playbook_from_content(
                            content, playbook_code=playbook_code, locale=locale
                        )

                        if playbook:
                            playbook.metadata.capability_code = capability_code
                            # Cache with provider info if available
                            provider_id = playbook_data.get("provider_id", "unknown")
                            cache_key = f"{provider_id}:{capability_code}:{playbook_code}:{locale}"
                            self.cloud_playbooks[cache_key] = playbook
                            logger.info(
                                f"Loaded cloud playbook: {capability_code}.{playbook_code} ({locale}) from {provider_id}"
                            )
                            return playbook
            except Exception as e:
                logger.warning(
                    f"Failed to load cloud playbook {capability_code}.{playbook_code}: {e}"
                )

        logger.warning(
            f"Playbook {playbook_code} not found (locale={locale}, workspace_id={workspace_id}, capability_code={capability_code})"
        )
        return None

    async def list_playbooks(
        self,
        workspace_id: Optional[str] = None,
        locale: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[PlaybookSource] = None,
        tags: Optional[List[str]] = None,
    ) -> List[PlaybookMetadata]:
        """
        List all available playbooks with filtering

        Args:
            workspace_id: Workspace ID (optional)
            locale: Language locale (optional, defaults to all locales)
            category: Category filter (matches tags)
            source: Source filter (system, capability, user)
            tags: Tags filter (list of tags to match)

        Returns:
            List of PlaybookMetadata
        """
        await self._ensure_loaded()

        playbooks_map: Dict[str, PlaybookMetadata] = {}
        locales_to_check = [locale] if locale else ["zh-TW", "en", "ja"]

        # 1. Capability Playbooks FIRST (they have enriched descriptions from JSON specs)
        if (
            not source
            or source == PlaybookSource.CAPABILITY
            or source == PlaybookSource.SYSTEM
        ):
            for playbooks_dict in self.capability_playbooks.values():
                for playbook in playbooks_dict.values():
                    if self._matches_filters(playbook, category, tags):
                        # Filter by requested locale if necessary
                        if locale and playbook.metadata.locale != locale:
                            continue

                        key = f"{playbook.metadata.playbook_code}:{playbook.metadata.locale}"
                        if key not in playbooks_map:
                            playbooks_map[key] = playbook.metadata

        # 2. System Playbooks (from i18n dir, may have less metadata)
        # Only add if not already loaded from capability packs
        if not source or source == PlaybookSource.SYSTEM:
            for loc in locales_to_check:
                if loc in self.system_playbooks:
                    for playbook in self.system_playbooks[loc].values():
                        if self._matches_filters(playbook, category, tags):
                            # Dedupe by playbook_code and locale
                            key = f"{playbook.metadata.playbook_code}:{playbook.metadata.locale}"
                            if key not in playbooks_map:
                                playbooks_map[key] = playbook.metadata

        # 3. User Playbooks
        if not source or source == PlaybookSource.USER:
            if workspace_id and workspace_id in self.user_playbooks:
                for playbook in self.user_playbooks[workspace_id].values():
                    if self._matches_filters(playbook, category, tags):
                        if locale and playbook.metadata.locale != locale:
                            continue
                        key = f"{playbook.metadata.playbook_code}:{playbook.metadata.locale}"
                        if key not in playbooks_map:
                            playbooks_map[key] = playbook.metadata

        return list(playbooks_map.values())

    def _matches_filters(
        self,
        playbook: Playbook,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Check if playbook matches the given filters"""
        if category:
            if category not in playbook.metadata.tags:
                return False

        if tags:
            if not any(tag in playbook.metadata.tags for tag in tags):
                return False

        return True

    def invalidate_cache(
        self, playbook_code: Optional[str] = None, locale: Optional[str] = None
    ):
        """
        Invalidate playbook cache

        Args:
            playbook_code: Specific playbook code to invalidate (optional, if None invalidates all)
            locale: Specific locale to invalidate (optional, if None invalidates all locales)
        """
        if playbook_code:
            # Invalidate specific playbook
            if locale:
                if (
                    locale in self.system_playbooks
                    and playbook_code in self.system_playbooks[locale]
                ):
                    del self.system_playbooks[locale][playbook_code]
                    logger.info(
                        f"Invalidated cache for playbook {playbook_code} (locale: {locale})"
                    )
            else:
                # Invalidate for all locales
                for loc in self.system_playbooks:
                    if playbook_code in self.system_playbooks[loc]:
                        del self.system_playbooks[loc][playbook_code]
                logger.info(
                    f"Invalidated cache for playbook {playbook_code} (all locales)"
                )
        else:
            # Invalidate all caches
            self._loaded = False
            self.system_playbooks.clear()
            self.capability_playbooks.clear()
            self.user_playbooks.clear()
            logger.info("Invalidated all playbook caches")

    async def reload_playbook(self, playbook_code: str, locale: str = "zh-TW"):
        """
        Reload a specific playbook from file system

        Args:
            playbook_code: Playbook code
            locale: Language locale
        """
        # Invalidate cache for this playbook
        self.invalidate_cache(playbook_code, locale)

        # Reload system playbooks for this locale
        base_dir = Path(__file__).parent.parent.parent.parent
        i18n_dir = base_dir / "backend" / "i18n" / "playbooks"
        locale_dir = i18n_dir / locale

        if locale_dir.exists():
            if locale not in self.system_playbooks:
                self.system_playbooks[locale] = {}

            # Find and reload the playbook file
            for md_file in locale_dir.glob("*.md"):
                if md_file.name == "README.md":
                    continue

                try:
                    playbook = PlaybookFileLoader.load_playbook_from_file(md_file)
                    if playbook and playbook.metadata.playbook_code == playbook_code:
                        playbook.metadata.locale = locale
                        self.system_playbooks[locale][playbook_code] = playbook
                        logger.info(f"Reloaded playbook: {playbook_code} ({locale})")
                        return True
                except Exception as e:
                    logger.warning(f"Failed to reload playbook from {md_file}: {e}")

        logger.warning(f"Failed to reload playbook {playbook_code} (locale: {locale})")
        return False


# Global singleton instance
_playbook_registry_instance: Optional["PlaybookRegistry"] = None


def get_playbook_registry() -> "PlaybookRegistry":
    """
    Get global singleton instance of PlaybookRegistry
    This ensures we only load/scan playbooks once per process
    """
    global _playbook_registry_instance
    if _playbook_registry_instance is None:
        _playbook_registry_instance = PlaybookRegistry()
    return _playbook_registry_instance
