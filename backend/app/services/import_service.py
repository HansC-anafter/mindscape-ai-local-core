"""
Import Service
Handles importing configuration from PortableConfiguration format
"""

import json
import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Dict, Any, List, Optional
from pathlib import Path

from backend.app.models.export import ExportedConfiguration
from backend.app.models.mindscape import MindscapeProfile, IntentCard, IntentStatus, PriorityLevel
from backend.app.models.playbook import Playbook, PlaybookMetadata
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_store import PlaybookStore

logger = logging.getLogger(__name__)


class ImportService:
    """
    Service for importing configuration from PortableConfiguration format

    Handles:
    1. Validating imported configuration
    2. Converting to internal models
    3. Importing playbooks, profiles, and intents
    """

    def __init__(
        self,
        mindscape_store: Optional[MindscapeStore] = None,
        playbook_store: Optional[PlaybookStore] = None,
    ):
        self.mindscape_store = mindscape_store or MindscapeStore()
        self.playbook_store = playbook_store or PlaybookStore()

    def import_from_file(self, file_path: str, profile_id: str) -> Dict[str, Any]:
        """
        Import configuration from a JSON file

        Args:
            file_path: Path to JSON file
            profile_id: Target profile ID to import to

        Returns:
            Import result summary
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return self.import_from_dict(data, profile_id)

    def import_from_dict(self, data: Dict[str, Any], profile_id: str) -> Dict[str, Any]:
        """
        Import configuration from dictionary

        Args:
            data: Configuration data
            profile_id: Target profile ID

        Returns:
            Import result summary
        """
        results = {
            "success": True,
            "imported_playbooks": 0,
            "imported_intents": 0,
            "skipped_playbooks": 0,
            "skipped_intents": 0,
            "errors": []
        }

        # Validate the import data format before processing
        if not self._validate_import_data(data):
            results["success"] = False
            results["errors"].append("Invalid import format")
            return results

        # Process playbook imports if present in data
        if "playbooks" in data:
            playbook_results = self._import_playbooks(data["playbooks"])
            results["imported_playbooks"] = playbook_results["imported"]
            results["skipped_playbooks"] = playbook_results["skipped"]
            results["errors"].extend(playbook_results["errors"])

        # Process intent/capability pack imports if present in data
        if "intents" in data or "capability_packs" in data:
            intents_data = data.get("intents", data.get("capability_packs", []))
            intent_results = self._import_intents(intents_data, profile_id)
            results["imported_intents"] = intent_results["imported"]
            results["skipped_intents"] = intent_results["skipped"]
            results["errors"].extend(intent_results["errors"])

        return results

    def _validate_import_data(self, data: Dict[str, Any]) -> bool:
        """Validate imported data format"""
        # Check for required version field
        if "export_version" not in data and "version" not in data:
            logger.warning("Missing version field in import data")
            return False

        # Accept data with either playbooks or intents
        has_content = (
            "playbooks" in data or
            "intents" in data or
            "capability_packs" in data
        )

        return has_content

    def _import_playbooks(self, playbooks_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Import playbooks from data

        Returns:
            Result summary
        """
        results = {
            "imported": 0,
            "skipped": 0,
            "errors": []
        }

        for pb_data in playbooks_data:
            try:
                # Check if playbook already exists
                playbook_code = pb_data.get("playbook_code")
                if not playbook_code:
                    results["skipped"] += 1
                    results["errors"].append(f"Playbook missing code: {pb_data.get('name', 'Unknown')}")
                    continue

                existing = self.playbook_store.get_playbook(playbook_code)
                if existing:
                    logger.info(f"Playbook {playbook_code} already exists, skipping")
                    results["skipped"] += 1
                    continue

                # Create playbook from imported data
                metadata = PlaybookMetadata(
                    playbook_code=playbook_code,
                    version=pb_data.get("version", "1.0.0"),
                    locale=pb_data.get("locale", "zh-TW"),
                    name=pb_data.get("name", playbook_code),
                    description=pb_data.get("description", ""),
                    tags=pb_data.get("tags", []),
                    entry_agent_type=pb_data.get("entry_agent_type"),
                    onboarding_task=pb_data.get("onboarding_task"),
                    icon=pb_data.get("icon"),
                    required_tools=pb_data.get("required_tools", []),
                    scope=pb_data.get("scope"),
                    owner={"type": "imported"},
                    created_at=_utc_now(),
                    updated_at=_utc_now()
                )

                playbook = Playbook(
                    metadata=metadata,
                    sop_content=pb_data.get("sop_content", "")
                )

                # Save to store
                self.playbook_store.create_playbook(playbook)
                results["imported"] += 1
                logger.info(f"Imported playbook: {playbook_code}")

            except Exception as e:
                results["errors"].append(f"Failed to import playbook: {str(e)}")
                logger.error(f"Failed to import playbook: {e}")

        return results

    def _import_intents(self, intents_data: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
        """
        Import intents from data

        Returns:
            Result summary
        """
        results = {
            "imported": 0,
            "skipped": 0,
            "errors": []
        }

        for intent_data in intents_data:
            try:
                # Parse priority
                priority_str = intent_data.get("priority", intent_data.get("priority_level", "medium"))
                try:
                    priority = PriorityLevel(priority_str.lower())
                except ValueError:
                    priority = PriorityLevel.MEDIUM

                # Parse status
                status_str = intent_data.get("status", "active")
                try:
                    status = IntentStatus(status_str.lower())
                except ValueError:
                    status = IntentStatus.ACTIVE

                # Create intent
                intent = IntentCard(
                    id=f"imported-{_utc_now().timestamp()}",
                    profile_id=profile_id,
                    title=intent_data.get("title", intent_data.get("name", "Untitled")),
                    description=intent_data.get("description", ""),
                    priority=priority,
                    status=status,
                    tags=intent_data.get("tags", []),
                    category=intent_data.get("category"),
                    created_at=_utc_now(),
                    updated_at=_utc_now()
                )

                # Save to store
                self.mindscape_store.create_intent(intent)
                results["imported"] += 1
                logger.info(f"Imported intent: {intent.title}")

            except Exception as e:
                results["errors"].append(f"Failed to import intent: {str(e)}")
                logger.error(f"Failed to import intent: {e}")

        return results
