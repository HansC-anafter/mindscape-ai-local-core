"""
Playbook Registry
Unified registry for all playbooks (system, capability, user)
Supports lazy loading to avoid startup overhead
"""

import os
import asyncio
import logging
from typing import Any, Dict, List, Optional
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
)
from backend.app.services.playbook_registry_core.cache import (
    invalidate_registry_cache,
)
from backend.app.services.playbook_registry_core.lookup import (
    cache_capability_playbook as cache_capability_playbook_entry,
    find_capability_dir_for_playbook,
    get_variant as get_playbook_variant,
    get_cached_capability_playbook,
    list_variants as list_playbook_variants,
    load_direct_capability_playbook,
    load_direct_system_playbook,
    parse_variants as parse_playbook_variants,
)
from backend.app.services.playbook_registry_core.metadata import (
    enrich_playbook_metadata,
    load_user_playbooks,
    matches_filters,
)
from backend.app.services.playbook_registry_core.search import (
    collect_playbook_metadata,
    lookup_local_playbook,
    resolve_playbook_lookup_request,
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

        # Lazy loading flags
        self._loaded = False
        self._system_loaded = False
        self._user_loaded = False
        # Per-capability lazy loading: tracks which capabilities have been loaded
        self._loaded_capabilities: set = set()
        # Capabilities directory path (resolved once, reused for per-cap loading)
        self._capabilities_dir: Optional[Path] = None
        # Concurrency protection: global load lock and per-capability locks
        self._load_lock = asyncio.Lock()
        self._capability_locks: Dict[str, asyncio.Lock] = {}

        # Playbook-level variants (separate from Graph IR variants)
        # Key: playbook_code (e.g. "yogacoach.intake_flow"), Value: list of variants
        self._playbook_variants: Dict[str, List[Dict[str, Any]]] = {}

    async def _ensure_loaded(self):
        """Ensure system and user playbooks are loaded (lazy loading)"""
        if self._loaded:
            return
        async with self._load_lock:
            if not self._loaded:
                await self._load_all_playbooks()
                self._loaded = True

    async def _ensure_user_playbooks_loaded(self):
        """Load user playbooks without forcing a full registry preload."""
        if self._user_loaded or not self.store:
            return
        async with self._load_lock:
            if self._user_loaded or not self.store:
                return
            self._load_user_playbooks()
            self._user_loaded = True

    async def _ensure_capability_loaded(self, capability_code: str):
        """
        Ensure a specific capability's playbooks are loaded.
        Only loads the requested capability, not all capabilities.
        Falls back to full load if capability directory cannot be resolved.
        Uses per-capability lock to prevent concurrent duplicate loads.
        """
        if capability_code in self._loaded_capabilities:
            return
        if capability_code in self.capability_playbooks:
            # Already loaded (e.g. via _load_all_playbooks)
            self._loaded_capabilities.add(capability_code)
            return

        # Acquire per-capability lock to prevent concurrent duplicate loads
        if capability_code not in self._capability_locks:
            self._capability_locks[capability_code] = asyncio.Lock()

        async with self._capability_locks[capability_code]:
            # Double-check after acquiring lock (another coroutine may have loaded it)
            if capability_code in self._loaded_capabilities:
                return

            # Resolve capabilities directory if not yet known
            if self._capabilities_dir is None:
                app_dir = Path(__file__).parent.parent
                self._capabilities_dir = app_dir / "capabilities"

            if self._capabilities_dir.exists():
                cap_dir = self._capabilities_dir / capability_code
                if cap_dir.is_dir():
                    self._load_single_capability(cap_dir)
                    self._loaded_capabilities.add(capability_code)
                    logger.info(f"Lazy-loaded capability playbooks: {capability_code}")
                    return

            # Capability not found locally. Mark the miss and leave broader
            # system/user loading to normal fallback lookup paths.
            self._loaded_capabilities.add(capability_code)

    async def _load_all_playbooks(self):
        """Load all playbooks from different sources"""
        logger.info("Loading playbooks from all sources...")

        # Load system-level playbooks first for core functionality
        if not self._system_loaded:
            self._load_system_playbooks()
            self._system_loaded = True

        # Load capability playbooks for extended features
        self._load_capability_playbooks()

        # Load user-defined playbooks from database if store is available
        if self.store and not self._user_loaded:
            self._load_user_playbooks()
            self._user_loaded = True

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

        # Cache the resolved path for per-capability lazy loading
        self._capabilities_dir = local_capabilities_dir

        logger.info(
            f"Checking capabilities directory: {local_capabilities_dir} (exists: {local_capabilities_dir.exists()})"
        )
        if local_capabilities_dir.exists():
            logger.info(
                f"Loading local capability playbooks from {local_capabilities_dir}"
            )
            self._load_playbooks_from_directory(local_capabilities_dir)
            # Mark all loaded capabilities as tracked
            for cap_code in list(self.capability_playbooks.keys()):
                self._loaded_capabilities.add(cap_code)
        else:
            logger.warning(
                f"Local capabilities directory does not exist: {local_capabilities_dir}"
            )

    def _parse_variants(
        self, playbook_config: dict, capability_code: str, playbook_code: str
    ) -> None:
        """Parse variants from a manifest playbook entry."""
        parse_playbook_variants(
            self._playbook_variants,
            playbook_config,
            capability_code,
            playbook_code,
            logger=logger,
        )

    def _load_single_capability(self, capability_dir: Path):
        """
        Load playbooks from a single capability directory.
        Used by per-capability lazy loading to avoid scanning all capabilities.
        """
        import yaml

        manifest_path = capability_dir / "manifest.yaml"
        if not manifest_path.exists():
            logger.debug(f"No manifest.yaml found in {capability_dir.name}, skipping")
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)

            capability_code = manifest.get("code")
            if not capability_code:
                logger.warning(
                    f"Manifest in {capability_dir.name} missing 'code' field, skipping"
                )
                return

            logger.info(f"Lazy-loading capability pack: {capability_code}")

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

                            self._enrich_playbook_metadata(
                                playbook, capability_dir, playbook_code, locale
                            )

                            full_code = f"{capability_code}.{playbook_code}"
                            locale_key = f"{playbook_code}:{locale}"
                            self.capability_playbooks[capability_code][
                                full_code
                            ] = playbook
                            self.capability_playbooks[capability_code][
                                locale_key
                            ] = playbook
                            if (
                                playbook_code
                                not in self.capability_playbooks[capability_code]
                            ):
                                self.capability_playbooks[capability_code][
                                    playbook_code
                                ] = playbook
                            else:
                                existing = self.capability_playbooks[capability_code][
                                    playbook_code
                                ]
                                existing_locale = existing.metadata.locale
                                locale_priority = {"zh-TW": 3, "en": 2, "ja": 1}
                                if locale_priority.get(locale, 0) > locale_priority.get(
                                    existing_locale, 0
                                ):
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

                # Parse variants for this playbook (shared helper)
                self._parse_variants(playbook_config, capability_code, playbook_code)

        except Exception as e:
            logger.error(f"Failed to load capability {capability_dir.name}: {e}")

    def _get_capabilities_dir(self) -> Path:
        if self._capabilities_dir is None:
            app_dir = Path(__file__).parent.parent
            self._capabilities_dir = app_dir / "capabilities"
        return self._capabilities_dir

    def _get_cached_capability_playbook(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str,
    ) -> Optional[Playbook]:
        return get_cached_capability_playbook(
            self.capability_playbooks,
            capability_code,
            playbook_code,
            locale,
        )

    def _cache_capability_playbook(
        self,
        capability_code: str,
        playbook_code: str,
        locale: str,
        playbook: Playbook,
    ) -> None:
        cache_capability_playbook_entry(
            self.capability_playbooks,
            capability_code,
            playbook_code,
            locale,
            playbook,
        )

    def _find_capability_dir_for_playbook(
        self, playbook_code: str, locale: str
    ) -> Optional[Path]:
        return find_capability_dir_for_playbook(
            self._get_capabilities_dir(),
            playbook_code,
            locale,
        )

    def _load_direct_capability_playbook(
        self,
        capability_dir: Path,
        playbook_code: str,
        locale: str,
    ) -> Optional[Playbook]:
        return load_direct_capability_playbook(
            capability_dir=capability_dir,
            playbook_code=playbook_code,
            locale=locale,
            capability_playbooks=self.capability_playbooks,
            loaded_capabilities=self._loaded_capabilities,
            enrich_playbook_metadata=self._enrich_playbook_metadata,
            cache_playbook=self._cache_capability_playbook,
            parse_variants_fn=self._parse_variants,
            logger=logger,
        )

    def _load_direct_system_playbook(
        self, playbook_code: str, locale: str
    ) -> Optional[Playbook]:
        base_dir = Path(__file__).parent.parent.parent.parent
        i18n_dir = base_dir / "backend" / "i18n" / "playbooks"
        return load_direct_system_playbook(
            system_playbooks=self.system_playbooks,
            i18n_dir=i18n_dir,
            playbook_code=playbook_code,
            locale=locale,
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

                    # Parse variants for this playbook (shared helper)
                    self._parse_variants(
                        playbook_config, capability_code, playbook_code
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
        """Try to enrich playbook metadata from a JSON spec file."""
        enrich_playbook_metadata(
            playbook,
            capability_dir,
            playbook_code,
            locale,
            logger=logger,
        )

    def _load_user_playbooks(self):
        """Load user-defined playbooks from the configured store."""
        load_user_playbooks(
            store=self.store,
            user_playbooks=self.user_playbooks,
            logger=logger,
        )

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
        (
            requested_playbook_code,
            playbook_code,
            capability_code,
            resolved_capability,
        ) = resolve_playbook_lookup_request(
            playbook_code=playbook_code,
            capability_code=capability_code,
            capability_playbooks=self.capability_playbooks,
            logger=logger,
        )

        if workspace_id:
            await self._ensure_user_playbooks_loaded()

        if resolved_capability:
            cached = self._get_cached_capability_playbook(
                resolved_capability, playbook_code, locale
            )
            if cached:
                return cached

            direct_capability_dir = self._get_capabilities_dir() / resolved_capability
            if direct_capability_dir.is_dir():
                direct_playbook = self._load_direct_capability_playbook(
                    direct_capability_dir, playbook_code, locale
                )
                if direct_playbook:
                    return direct_playbook
        else:
            direct_capability_dir = self._find_capability_dir_for_playbook(
                playbook_code, locale
            )
            if direct_capability_dir is not None:
                direct_playbook = self._load_direct_capability_playbook(
                    direct_capability_dir, playbook_code, locale
                )
                if direct_playbook:
                    return direct_playbook

            direct_system_playbook = self._load_direct_system_playbook(
                playbook_code, locale
            )
            if direct_system_playbook:
                return direct_system_playbook

        if resolved_capability:
            await self._ensure_capability_loaded(resolved_capability)
        else:
            await self._ensure_loaded()

        logger.debug(
            f"PlaybookRegistry.get_playbook: code={playbook_code}, locale={locale}, workspace_id={workspace_id}, capability_code={capability_code}"
        )
        logger.debug(f"Available system locales: {list(self.system_playbooks.keys())}")
        logger.debug(
            f"Available capability packs: {list(self.capability_playbooks.keys())}"
        )
        logger.debug(f"Available user workspaces: {list(self.user_playbooks.keys())}")

        local_playbook = lookup_local_playbook(
            system_playbooks=self.system_playbooks,
            capability_playbooks=self.capability_playbooks,
            user_playbooks=self.user_playbooks,
            playbook_code=playbook_code,
            locale=locale,
            workspace_id=workspace_id,
            capability_code=capability_code,
            logger=logger,
        )
        if local_playbook:
            return local_playbook

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
            f"Playbook {requested_playbook_code} not found (locale={locale}, workspace_id={workspace_id}, capability_code={capability_code})"
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

        return collect_playbook_metadata(
            capability_playbooks=self.capability_playbooks,
            system_playbooks=self.system_playbooks,
            user_playbooks=self.user_playbooks,
            workspace_id=workspace_id,
            locale=locale,
            category=category,
            source_value=source.value if source else None,
            tags=tags,
            matches_filters_fn=self._matches_filters,
        )

    def _matches_filters(
        self,
        playbook: Playbook,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """Check whether a playbook matches the requested filters."""
        return matches_filters(playbook, category=category, tags=tags)

    def invalidate_cache(
        self,
        playbook_code: Optional[str] = None,
        locale: Optional[str] = None,
        capability_code: Optional[str] = None,
    ):
        """
        Invalidate playbook cache

        Args:
            playbook_code: Specific playbook code to invalidate (optional, if None invalidates all)
            locale: Specific locale to invalidate (optional, if None invalidates all locales)
            capability_code: Specific capability to invalidate (optional, granular cache clear)
        """
        reset_loaded = invalidate_registry_cache(
            system_playbooks=self.system_playbooks,
            capability_playbooks=self.capability_playbooks,
            user_playbooks=self.user_playbooks,
            playbook_variants=self._playbook_variants,
            loaded_capabilities=self._loaded_capabilities,
            capability_locks=self._capability_locks,
            logger=logger,
            playbook_code=playbook_code,
            locale=locale,
            capability_code=capability_code,
        )
        if reset_loaded:
            self._loaded = False

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

    def get_variant(
        self, playbook_code: str, variant_id: str
    ) -> Optional[Dict[str, Any]]:
        """Lookup a specific playbook variant by ID.

        Returns a runner-compatible dict (skip_steps, custom_checklist,
        execution_params) or None if not found.

        This is a playbook-level API, separate from GraphVariantRegistry.
        """
        return get_playbook_variant(self._playbook_variants, playbook_code, variant_id)

    def list_variants(self, playbook_code: str) -> List[Dict[str, Any]]:
        """List all variants for a playbook.

        Returns list of runner-compatible dicts.
        """
        return list_playbook_variants(self._playbook_variants, playbook_code)


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
