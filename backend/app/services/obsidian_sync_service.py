"""
Obsidian Sync Service

Background service for scanning Obsidian vaults and creating events.
Integrates with event system and embedding pipeline.
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime
import uuid

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.services.obsidian_scanner import ObsidianScanner
from backend.app.services.stores.events_store import EventsStore
from backend.app.services.system_settings_store import SystemSettingsStore

logger = logging.getLogger(__name__)


class ObsidianSyncService:
    """
    Service for syncing Obsidian vaults with Mindscape event system
    """

    def __init__(self):
        self.events_store = EventsStore()
        self.settings_store = SystemSettingsStore()
        self.scanners: Dict[str, ObsidianScanner] = {}
        self._running = False

    def load_config(self) -> Optional[Dict[str, Any]]:
        """Load Obsidian configuration from settings"""
        try:
            setting = self.settings_store.get_setting("obsidian_config")
            if setting:
                import json
                config = json.loads(setting.value) if isinstance(setting.value, str) else setting.value
                if config.get("enabled", False):
                    return config
            return None
        except Exception as e:
            logger.error(f"Failed to load Obsidian config: {e}")
            return None

    def create_scanners(self) -> Dict[str, ObsidianScanner]:
        """Create scanners for all configured vaults"""
        config = self.load_config()
        if not config:
            return {}

        vault_paths = config.get("vault_paths", [])
        include_folders = config.get("include_folders", [])
        exclude_folders = config.get("exclude_folders", [".obsidian", "Templates"])
        include_tags = config.get("include_tags", ["research", "paper", "project"])

        scanners = {}
        for vault_path in vault_paths:
            try:
                scanner = ObsidianScanner(
                    vault_path=vault_path,
                    include_folders=include_folders,
                    exclude_folders=exclude_folders,
                    include_tags=include_tags
                )
                scanners[vault_path] = scanner
            except Exception as e:
                logger.error(f"Failed to create scanner for vault {vault_path}: {e}")

        return scanners

    async def sync_vaults(self, profile_id: str = "default-user"):
        """
        Scan all configured vaults and create events for changes

        Args:
            profile_id: Profile ID for events
        """
        scanners = self.create_scanners()

        for vault_path, scanner in scanners.items():
            try:
                events = scanner.scan_vault()

                for event_data in events:
                    await self._create_event_from_scan(event_data, profile_id, vault_path)

                if events:
                    logger.info(f"Synced {len(events)} note changes from vault {vault_path}")
            except Exception as e:
                logger.error(f"Error syncing vault {vault_path}: {e}")

    async def _create_event_from_scan(
        self,
        event_data: Dict[str, Any],
        profile_id: str,
        vault_path: str
    ):
        """Create MindEvent from scanner event data"""
        try:
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.fromisoformat(event_data["modified"]),
                actor=EventActor.SYSTEM,
                channel="obsidian_sync",
                profile_id=profile_id,
                event_type=EventType.OBSIDIAN_NOTE_UPDATED,
                payload={
                    "note_path": event_data["note_path"],
                    "vault_path": vault_path,
                    "title": event_data.get("title", ""),
                    "content": event_data.get("content", ""),
                    "body": event_data.get("content", ""),
                    "tags": event_data.get("tags", []),
                    "hash": event_data.get("hash"),
                    "is_new": event_data.get("is_new", False)
                },
                metadata={
                    "should_embed": event_data.get("should_embed", False),
                    "source": "obsidian_vault",
                    "vault_path": vault_path
                }
            )

            should_embed = event_data.get("should_embed", False)
            self.events_store.create_event(event, generate_embedding=should_embed)

        except Exception as e:
            logger.error(f"Failed to create event from scan: {e}")

    async def start_background_sync(self, interval_seconds: int = 300):
        """
        Start background sync task

        Args:
            interval_seconds: Scan interval in seconds (default: 5 minutes)
        """
        if self._running:
            logger.warning("Background sync already running")
            return

        self._running = True
        logger.info(f"Starting Obsidian background sync (interval: {interval_seconds}s)")

        while self._running:
            try:
                await self.sync_vaults()
            except Exception as e:
                logger.error(f"Error in background sync: {e}")

            await asyncio.sleep(interval_seconds)

    def stop_background_sync(self):
        """Stop background sync task"""
        self._running = False
        logger.info("Stopped Obsidian background sync")




