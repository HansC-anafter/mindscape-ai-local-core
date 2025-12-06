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

from backend.app.models.playbook import Playbook, PlaybookMetadata
from backend.app.services.playbook_loaders import PlaybookFileLoader, PlaybookDatabaseLoader

logger = logging.getLogger(__name__)


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

    def __init__(self, store=None):
        """
        Initialize PlaybookRegistry

        Args:
            store: MindscapeStore instance (optional, for user playbooks)
        """
        self.store = store

        # Cache: locale -> code -> playbook
        self.system_playbooks: Dict[str, Dict[str, Playbook]] = {}
        # Cache: capability_code -> code -> playbook
        self.capability_playbooks: Dict[str, Dict[str, Playbook]] = {}
        # Cache: workspace_id -> code -> playbook
        self.user_playbooks: Dict[str, Dict[str, Playbook]] = {}

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

        logger.info(f"Loaded {len(self.system_playbooks)} system playbook locales, "
                   f"{len(self.capability_playbooks)} capability packs")

    def _load_system_playbooks(self):
        """
        Load system-level playbooks from:
        1. NPM packages (@mindscape/playbook-*)
        2. backend/i18n/playbooks/ (backward compatibility)
        """
        # First try loading from NPM packages
        try:
            from backend.app.services.playbook_loaders.npm_loader import PlaybookNpmLoader
            packages = PlaybookNpmLoader.find_playbook_packages()
            
            supported_locales = ['zh-TW', 'en', 'ja']
            
            for package in packages:
                playbook_code = package["playbook_code"]
                
                for locale in supported_locales:
                    if locale not in self.system_playbooks:
                        self.system_playbooks[locale] = {}
                    
                    # Try to load i18n from NPM package
                    i18n_content = PlaybookNpmLoader.load_playbook_i18n(playbook_code, locale)
                    if i18n_content:
                        try:
                            from io import StringIO
                            from backend.app.services.playbook_loaders.file_loader import PlaybookFileLoader
                            
                            # Create a temporary file-like object for PlaybookFileLoader
                            # PlaybookFileLoader expects a Path, so we need to write to temp file
                            import tempfile
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False, encoding='utf-8') as tmp_file:
                                tmp_file.write(i18n_content)
                                tmp_path = Path(tmp_file.name)
                            
                            playbook = PlaybookFileLoader.load_playbook_from_file(tmp_path)
                            if playbook:
                                playbook.metadata.locale = locale
                                if playbook_code not in self.system_playbooks[locale]:
                                    self.system_playbooks[locale][playbook_code] = playbook
                                    logger.debug(f"Loaded playbook from NPM package: {playbook_code} ({locale})")
                            
                            # Clean up temp file
                            tmp_path.unlink()
                        except Exception as e:
                            logger.warning(f"Failed to load playbook from NPM package {package['name']}: {e}")
        except Exception as e:
            logger.debug(f"Failed to load playbooks from NPM packages: {e}")

        # Fallback to core i18n directory (backward compatibility)
        base_dir = Path(__file__).parent.parent.parent.parent
        i18n_dir = base_dir / "backend" / "i18n" / "playbooks"

        if not i18n_dir.exists():
            logger.warning(f"System playbooks directory does not exist: {i18n_dir}")
            return

        # Supported locales
        supported_locales = ['zh-TW', 'en', 'ja']

        for locale in supported_locales:
            locale_dir = i18n_dir / locale
            if not locale_dir.exists():
                continue

            if locale not in self.system_playbooks:
                self.system_playbooks[locale] = {}

            # Load .md files from locale directory
            for md_file in locale_dir.glob('*.md'):
                if md_file.name == 'README.md':
                    continue

                try:
                    playbook = PlaybookFileLoader.load_playbook_from_file(md_file)
                    if playbook:
                        # Ensure locale matches directory
                        playbook.metadata.locale = locale
                        playbook_code = playbook.metadata.playbook_code
                        # Only add if not already loaded from NPM package
                        if playbook_code not in self.system_playbooks[locale]:
                            self.system_playbooks[locale][playbook_code] = playbook
                            logger.debug(f"Loaded system playbook: {playbook_code} ({locale})")
                except Exception as e:
                    logger.warning(f"Failed to load system playbook from {md_file}: {e}")

    def _load_capability_playbooks(self):
        """Load capability pack playbooks"""
        pass

    def _load_user_playbooks(self):
        """Load user-defined playbooks from database"""
        if not self.store:
            return

        try:
            # Get database path from store
            db_path = self.store.db_path if hasattr(self.store, 'db_path') else None
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
                logger.debug(f"Loaded user playbook: {playbook_code} (locale: {locale})")

            logger.info(f"Loaded {sum(len(pbs) for pbs in self.user_playbooks.values())} user playbooks from database")
        except Exception as e:
            logger.warning(f"Failed to load user playbooks: {e}", exc_info=True)

    async def get_playbook(
        self,
        playbook_code: str,
        locale: str = "zh-TW",
        workspace_id: Optional[str] = None
    ) -> Optional[Playbook]:
        """
        Unified lookup interface

        Lookup priority:
        1. User-defined playbook (if workspace_id provided)
        2. Capability playbook
        3. System-level playbook
        """
        await self._ensure_loaded()

        logger.debug(f"PlaybookRegistry.get_playbook: code={playbook_code}, locale={locale}, workspace_id={workspace_id}")
        logger.debug(f"Available system locales: {list(self.system_playbooks.keys())}")
        logger.debug(f"Available capability packs: {list(self.capability_playbooks.keys())}")
        logger.debug(f"Available user workspaces: {list(self.user_playbooks.keys())}")

        if workspace_id and workspace_id in self.user_playbooks:
            if playbook_code in self.user_playbooks[workspace_id]:
                logger.debug(f"Found playbook {playbook_code} in user playbooks for workspace {workspace_id}")
                return self.user_playbooks[workspace_id][playbook_code]

        for capability_code, playbooks in self.capability_playbooks.items():
            if playbook_code in playbooks:
                logger.debug(f"Found playbook {playbook_code} in capability {capability_code}")
                return playbooks[playbook_code]

        if locale in self.system_playbooks:
            if playbook_code in self.system_playbooks[locale]:
                logger.debug(f"Found playbook {playbook_code} in system playbooks for locale {locale}")
                return self.system_playbooks[locale][playbook_code]
            else:
                logger.debug(f"Playbook {playbook_code} not found in system playbooks for locale {locale}, available codes: {list(self.system_playbooks[locale].keys())}")
        else:
            logger.debug(f"Locale {locale} not found in system playbooks")

        logger.warning(f"Playbook {playbook_code} not found (locale={locale}, workspace_id={workspace_id})")
        return None

    async def list_playbooks(
        self,
        workspace_id: Optional[str] = None,
        locale: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[PlaybookSource] = None,
        tags: Optional[List[str]] = None
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

        playbooks: List[PlaybookMetadata] = []
        locales_to_check = [locale] if locale else ['zh-TW', 'en', 'ja']

        if not source or source == PlaybookSource.SYSTEM:
            for loc in locales_to_check:
                if loc in self.system_playbooks:
                    for playbook in self.system_playbooks[loc].values():
                        if self._matches_filters(playbook, category, tags):
                            playbooks.append(playbook.metadata)

        if not source or source == PlaybookSource.CAPABILITY:
            for playbooks_dict in self.capability_playbooks.values():
                for playbook in playbooks_dict.values():
                    if self._matches_filters(playbook, category, tags):
                        playbooks.append(playbook.metadata)

        if not source or source == PlaybookSource.USER:
            if workspace_id and workspace_id in self.user_playbooks:
                for playbook in self.user_playbooks[workspace_id].values():
                    if self._matches_filters(playbook, category, tags):
                        playbooks.append(playbook.metadata)

        return playbooks

    def _matches_filters(
        self,
        playbook: Playbook,
        category: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> bool:
        """Check if playbook matches the given filters"""
        if category:
            if category not in playbook.metadata.tags:
                return False

        if tags:
            if not any(tag in playbook.metadata.tags for tag in tags):
                return False

        return True

    def invalidate_cache(self, playbook_code: Optional[str] = None, locale: Optional[str] = None):
        """
        Invalidate playbook cache

        Args:
            playbook_code: Specific playbook code to invalidate (optional, if None invalidates all)
            locale: Specific locale to invalidate (optional, if None invalidates all locales)
        """
        if playbook_code:
            # Invalidate specific playbook
            if locale:
                if locale in self.system_playbooks and playbook_code in self.system_playbooks[locale]:
                    del self.system_playbooks[locale][playbook_code]
                    logger.info(f"Invalidated cache for playbook {playbook_code} (locale: {locale})")
            else:
                # Invalidate for all locales
                for loc in self.system_playbooks:
                    if playbook_code in self.system_playbooks[loc]:
                        del self.system_playbooks[loc][playbook_code]
                logger.info(f"Invalidated cache for playbook {playbook_code} (all locales)")
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
            for md_file in locale_dir.glob('*.md'):
                if md_file.name == 'README.md':
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

