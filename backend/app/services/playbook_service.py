"""
Playbook Service
Unified service layer for all playbook operations.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.app.models.playbook import (
    Playbook,
    PlaybookInvocationContext,
    PlaybookMetadata,
    PlaybookOwnerType,
)
from backend.app.services.playbook_loaders import PlaybookJsonLoader
from backend.app.services.playbook_registry import PlaybookRegistry, PlaybookSource

from .playbook_service_execution import (
    execute_playbook_for_service,
    get_execution_result_for_service,
    get_execution_status_for_service,
    load_playbook_run_for_service,
)
from .playbook_service_forking import fork_playbook_for_service
from .playbook_service_metadata import (
    filter_playbooks_by_runtime_tier,
    list_by_owner_type_for_service,
    metadata_to_dict,
)
from .playbook_service_models import ExecutionMode, ExecutionResult
from .playbook_service_validation import (
    validate_edit_permission_for_playbook,
    validate_playbook_slots_for_service,
)

logger = logging.getLogger(__name__)


class PlaybookService:
    """Unified service facade for playbook operations."""

    def __init__(self, store=None, cloud_client=None, cloud_extension_manager=None):
        self.store = store

        if cloud_extension_manager:
            self.cloud_extension_manager = cloud_extension_manager
        elif cloud_client:
            from ...services.cloud_extension_manager import CloudExtensionManager

            self.cloud_extension_manager = CloudExtensionManager.instance()
            logger.warning(
                "Using deprecated cloud_client parameter. Please migrate to cloud_extension_manager."
            )
        else:
            self.cloud_extension_manager = None

        self.registry = PlaybookRegistry(
            store,
            cloud_extension_manager=self.cloud_extension_manager,
        )

        from backend.app.core.graph import (
            GraphExecutor,
            GraphSelector,
            GraphVariantRegistry,
        )

        self.graph_registry = GraphVariantRegistry()
        self.graph_selector = GraphSelector(self.graph_registry)
        self.graph_executor = GraphExecutor()

    async def get_playbook(
        self,
        playbook_code: str,
        locale: str = "zh-TW",
        workspace_id: Optional[str] = None,
        runtime_tier: Optional[str] = None,
    ) -> Optional[Playbook]:
        logger.info(
            "PlaybookService.get_playbook called: code=%s, locale=%s, workspace_id=%s",
            playbook_code,
            locale,
            workspace_id,
        )
        if locale is None:
            import traceback

            logger.error(
                "PlaybookService.get_playbook: locale is None for %s! Stack trace:\n%s",
                playbook_code,
                traceback.format_stack(),
            )
            raise ValueError(
                f"locale cannot be None when calling get_playbook for {playbook_code}"
            )

        playbook = await self.registry.get_playbook(playbook_code, locale, workspace_id)
        if playbook and runtime_tier:
            playbook_runtime_tier = getattr(playbook.metadata, "runtime_tier", None)
            if playbook_runtime_tier == "cloud_only" and runtime_tier == "local":
                logger.warning(
                    "Playbook %s requires cloud execution but local was requested",
                    playbook_code,
                )
                return None
        return playbook

    async def list_playbooks(
        self,
        workspace_id: Optional[str] = None,
        locale: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[PlaybookSource] = None,
        tags: Optional[List[str]] = None,
        runtime_tier: Optional[str] = None,
    ) -> List[PlaybookMetadata]:
        playbooks = await self.registry.list_playbooks(
            workspace_id=workspace_id,
            locale=locale,
            category=category,
            source=source,
            tags=tags,
        )
        return filter_playbooks_by_runtime_tier(playbooks, runtime_tier)

    async def fork_playbook(
        self,
        source_playbook_code: str,
        target_playbook_code: str,
        workspace_id: str,
        profile_id: str,
        locale: str = "zh-TW",
    ) -> Optional[Playbook]:
        return await fork_playbook_for_service(
            service=self,
            source_playbook_code=source_playbook_code,
            target_playbook_code=target_playbook_code,
            workspace_id=workspace_id,
            profile_id=profile_id,
            locale=locale,
            logger=logger,
        )

    async def validate_playbook_slots(
        self,
        playbook_code: str,
        workspace_id: str,
        locale: str = "zh-TW",
        project_id: Optional[str] = None,
    ) -> tuple[bool, List[str], Dict[str, str]]:
        return await validate_playbook_slots_for_service(
            store=self.store,
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            locale=locale,
            project_id=project_id,
            logger=logger,
        )

    def validate_edit_permission(
        self,
        playbook: Playbook,
        edit_type: str = "sop",
    ) -> tuple[bool, Optional[str]]:
        return validate_edit_permission_for_playbook(playbook, edit_type)

    async def execute_playbook(
        self,
        playbook_code: str,
        workspace_id: str,
        profile_id: str,
        inputs: Dict[str, Any],
        execution_mode: ExecutionMode = ExecutionMode.ASYNC,
        locale: str = "zh-TW",
        context: Optional[PlaybookInvocationContext] = None,
        project_id: Optional[str] = None,
    ) -> ExecutionResult:
        return await execute_playbook_for_service(
            service=self,
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            profile_id=profile_id,
            inputs=inputs,
            execution_mode=execution_mode,
            locale=locale,
            context=context,
            project_id=project_id,
            logger=logger,
        )

    async def get_execution_status(self, execution_id: str) -> Optional[str]:
        return await get_execution_status_for_service(
            store=self.store,
            execution_id=execution_id,
            logger=logger,
        )

    async def get_execution_result(
        self,
        execution_id: str,
    ) -> Optional[ExecutionResult]:
        return await get_execution_result_for_service(
            store=self.store,
            execution_id=execution_id,
            logger=logger,
        )

    async def load_playbook_run(
        self,
        playbook_code: str,
        locale: str = "zh-TW",
        workspace_id: Optional[str] = None,
    ) -> Optional["PlaybookRun"]:
        return await load_playbook_run_for_service(
            service=self,
            playbook_code=playbook_code,
            locale=locale,
            workspace_id=workspace_id,
            logger=logger,
        )

    async def list_by_owner_type(
        self,
        owner_type: PlaybookOwnerType,
        owner_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return await list_by_owner_type_for_service(
            service=self,
            owner_type=owner_type,
            owner_id=owner_id,
        )

    async def list_for_workspace(self, workspace_id: str) -> List[Dict[str, Any]]:
        return await self.list_by_owner_type(
            owner_type=PlaybookOwnerType.WORKSPACE,
            owner_id=workspace_id,
        )

    async def list_for_user(self, user_id: str) -> List[Dict[str, Any]]:
        return await self.list_by_owner_type(
            owner_type=PlaybookOwnerType.USER,
            owner_id=user_id,
        )

    def _metadata_to_dict(self, metadata: PlaybookMetadata) -> Dict[str, Any]:
        return metadata_to_dict(metadata)


__all__ = [
    "ExecutionMode",
    "ExecutionResult",
    "PlaybookJsonLoader",
    "PlaybookService",
]
