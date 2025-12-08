"""
Workspace API Dependencies

FastAPI dependency injection for workspace routes.
Provides shared services and stores.
"""

from fastapi import Depends, HTTPException, Path
from typing import Optional
import logging

from ..models.workspace import Workspace

logger = logging.getLogger(__name__)
from ..services.mindscape_store import MindscapeStore
from ..services.intent_analyzer import IntentPipeline
from ..services.playbook_runner import PlaybookRunner
from ..services.playbook_service import PlaybookService
from ..services.conversation_orchestrator import ConversationOrchestrator
from ..services.stores.tasks_store import TasksStore
from ..services.stores.timeline_items_store import TimelineItemsStore
from ..services.stores.artifacts_store import ArtifactsStore
from ..core.ports.identity_port import IdentityPort
from ..adapters.local.local_identity_adapter import LocalIdentityAdapter

# Global singleton instances
_store = None
_intent_pipeline = None
_playbook_runner = None


def get_store() -> MindscapeStore:
    """Get MindscapeStore singleton"""
    global _store
    if _store is None:
        _store = MindscapeStore()
    return _store


def get_intent_pipeline(store: MindscapeStore = Depends(get_store)) -> IntentPipeline:
    """Get IntentPipeline singleton"""
    global _intent_pipeline
    if _intent_pipeline is None:
        playbook_service = PlaybookService(store=store)
        
        # Try to get llm_provider dynamically
        llm_provider = None
        try:
            from ..shared.llm_provider_helper import get_llm_provider_from_settings
            from ..services.agent_runner import LLMProviderManager
            llm_manager = LLMProviderManager()
            llm_provider = get_llm_provider_from_settings(llm_manager)
            logger.info("IntentPipeline: Successfully obtained llm_provider from settings")
        except Exception as e:
            logger.debug(f"IntentPipeline: Failed to get llm_provider from settings: {e}, will use None")
        
        _intent_pipeline = IntentPipeline(
            llm_provider=llm_provider,
            store=store,
            playbook_service=playbook_service
        )
    return _intent_pipeline


def get_playbook_runner() -> PlaybookRunner:
    """Get PlaybookRunner singleton"""
    global _playbook_runner
    if _playbook_runner is None:
        _playbook_runner = PlaybookRunner()
    return _playbook_runner


def get_workspace(
    workspace_id: str = Path(..., description="Workspace ID"),
    store: MindscapeStore = Depends(get_store)
) -> Workspace:
    """Get workspace by ID, raise 404 if not found"""
    # Note: Cannot access Request directly in dependency, will log in route handler instead
    logger.debug(f"get_workspace called for workspace_id: {workspace_id}")
    workspace = store.get_workspace(workspace_id)
    if not workspace:
        logger.error(f"Workspace not found: {workspace_id}")
        raise HTTPException(status_code=404, detail="Workspace not found")
    return workspace


def get_orchestrator(
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
    intent_pipeline: IntentPipeline = Depends(get_intent_pipeline),
    playbook_runner: PlaybookRunner = Depends(get_playbook_runner)
) -> ConversationOrchestrator:
    """Get ConversationOrchestrator with workspace locale"""
    # Get default_locale from workspace, or fallback to system settings
    if workspace and workspace.default_locale:
        default_locale = workspace.default_locale
    else:
        from ..services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore(db_path=store.db_path)
        language_setting = settings_store.get_setting("default_language")
        default_locale = language_setting.value if language_setting and language_setting.value else "zh-TW"
        logger.info(f"Workspace {workspace.id if workspace else 'None'} has no default_locale, using system setting: {default_locale}")

    return ConversationOrchestrator(
        store=store,
        intent_pipeline=intent_pipeline,
        playbook_runner=playbook_runner,
        default_locale=default_locale
    )


def get_tasks_store(store: MindscapeStore = Depends(get_store)) -> TasksStore:
    """Get TasksStore instance"""
    return TasksStore(store.db_path)


def get_timeline_items_store(store: MindscapeStore = Depends(get_store)) -> TimelineItemsStore:
    """Get TimelineItemsStore instance"""
    return TimelineItemsStore(store.db_path)


def get_artifacts_store(store: MindscapeStore = Depends(get_store)) -> ArtifactsStore:
    """Get ArtifactsStore instance"""
    return ArtifactsStore(store.db_path)


# Global singleton for IdentityPort
_identity_port = None


def get_identity_port_or_default() -> IdentityPort:
    """
    Get IdentityPort instance (defaults to LocalIdentityAdapter)

    Aligned with Port architecture. If no cloud adapter is provided,
    automatically creates LocalIdentityAdapter for backward compatibility.
    """
    global _identity_port
    if _identity_port is None:
        _identity_port = LocalIdentityAdapter()
    return _identity_port

