"""Unified registry for system, capability, user, and cloud playbooks."""

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional
from pathlib import Path
from enum import Enum

from backend.app.models.playbook import (
    Playbook,
    PlaybookMetadata,
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
from backend.app.services.playbook_registry_core.loaders import (
    load_capability_playbooks as load_capability_playbooks_from_sources,
    load_playbooks_from_directory as load_playbooks_from_capability_directory,
    load_single_capability as load_single_capability_playbooks,
    load_system_playbooks as load_system_playbooks_from_sources,
    reload_system_playbook,
)
from backend.app.services.playbook_registry_core.metadata import (
    enrich_playbook_metadata,
    load_user_playbooks,
    matches_filters,
)
from backend.app.services.playbook_registry_core.search import (
    collect_playbook_metadata,
    resolve_registry_playbook,
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


def _record_loaded_capability_activation(
    *,
    capability_code: str,
    manifest: Dict[str, Any],
    manifest_path: Path,
) -> None:
    try:
        from app.services.pack_activation_service import PackActivationService

        PackActivationService().record_activation_succeeded(
            pack_id=capability_code,
            manifest=manifest,
            manifest_path=manifest_path if manifest_path.exists() else None,
            activation_mode="playbook_registry_load",
            registered_prefixes=[],
        )
    except Exception as exc:
        logger.warning(
            "Failed to persist playbook activation state for %s: %s",
            capability_code,
            exc,
        )


class PlaybookRegistry:
    """Unified query facade for all playbook sources."""

    def __init__(self, store=None, cloud_client=None, cloud_extension_manager=None):
        self.store = store

        if cloud_extension_manager:
            self.cloud_extension_manager = cloud_extension_manager
        elif cloud_client:
            self.cloud_extension_manager = None
            logger.warning(
                "Using deprecated cloud_client parameter. Please migrate to cloud_extension_manager."
            )
        else:
            self.cloud_extension_manager = None

        self.system_playbooks: Dict[str, Dict[str, Playbook]] = {}
        self.capability_playbooks: Dict[str, Dict[str, Playbook]] = {}
        self.user_playbooks: Dict[str, Dict[str, Playbook]] = {}
        self.cloud_playbooks: Dict[str, Playbook] = {}

        self._loaded = False
        self._system_loaded = False
        self._user_loaded = False
        self._loaded_capabilities: set = set()
        self._capabilities_dir: Optional[Path] = None
        self._load_lock = asyncio.Lock()
        self._load_thread_lock = threading.RLock()
        self._capability_locks: Dict[str, asyncio.Lock] = {}

        self._playbook_variants: Dict[str, List[Dict[str, Any]]] = {}

    async def _ensure_loaded(self):
        """Ensure system and user playbooks are loaded (lazy loading)"""
        if self._loaded:
            return
        async with self._load_lock:
            if not self._loaded:
                await asyncio.to_thread(self._load_all_playbooks_sync)

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
        """Ensure a specific capability's playbooks are loaded."""
        if capability_code in self._loaded_capabilities:
            return
        if capability_code in self.capability_playbooks:
            self._loaded_capabilities.add(capability_code)
            return

        if capability_code not in self._capability_locks:
            self._capability_locks[capability_code] = asyncio.Lock()

        async with self._capability_locks[capability_code]:
            if capability_code in self._loaded_capabilities:
                return

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

            self._loaded_capabilities.add(capability_code)

    async def _load_all_playbooks(self):
        """Load all playbooks from different sources"""
        await asyncio.to_thread(self._load_all_playbooks_sync)

    def _load_all_playbooks_sync(self):
        """Load all playbooks from different sources without blocking the API event loop."""
        if self._loaded:
            return
        with self._load_thread_lock:
            if self._loaded:
                return

            logger.info("Loading playbooks from all sources...")

            if not self._system_loaded:
                self._load_system_playbooks()
                self._system_loaded = True

            self._load_capability_playbooks()

            if self.store and not self._user_loaded:
                self._load_user_playbooks()
                self._user_loaded = True

            self._loaded = True
            logger.info(
                f"Loaded {len(self.system_playbooks)} system playbook locales, "
                f"{len(self.capability_playbooks)} capability packs"
            )

    def _load_system_playbooks(self):
        """Load system-level playbooks."""
        load_system_playbooks_from_sources(
            registry_file=Path(__file__),
            system_playbooks=self.system_playbooks,
            enrich_playbook_metadata=self._enrich_playbook_metadata,
            logger=logger,
        )

    def _load_capability_playbooks(self):
        """Load local capability playbooks."""
        self._capabilities_dir = load_capability_playbooks_from_sources(
            registry_file=Path(__file__),
            capability_playbooks=self.capability_playbooks,
            loaded_capabilities=self._loaded_capabilities,
            enrich_playbook_metadata=self._enrich_playbook_metadata,
            parse_variants_fn=self._parse_variants,
            record_activation=_record_loaded_capability_activation,
            logger=logger,
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
        load_single_capability_playbooks(
            capability_dir=capability_dir,
            capability_playbooks=self.capability_playbooks,
            enrich_playbook_metadata=self._enrich_playbook_metadata,
            parse_variants_fn=self._parse_variants,
            record_activation=_record_loaded_capability_activation,
            logger=logger,
        )

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
        load_playbooks_from_capability_directory(
            capabilities_dir=capabilities_dir,
            capability_playbooks=self.capability_playbooks,
            enrich_playbook_metadata=self._enrich_playbook_metadata,
            parse_variants_fn=self._parse_variants,
            record_activation=_record_loaded_capability_activation,
            logger=logger,
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
        """Unified lookup interface for user, capability, system, and cloud playbooks."""
        return await resolve_registry_playbook(
            self,
            playbook_code=playbook_code,
            locale=locale,
            workspace_id=workspace_id,
            capability_code=capability_code,
            logger=logger,
        )

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
        """Reload a specific system playbook from file system."""
        self.invalidate_cache(playbook_code, locale)
        return reload_system_playbook(
            registry_file=Path(__file__),
            system_playbooks=self.system_playbooks,
            playbook_code=playbook_code,
            locale=locale,
            logger=logger,
        )

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
