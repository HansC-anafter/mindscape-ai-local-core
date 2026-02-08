"""
Playbook Scope Resolver

Resolves which playbooks are available (effective) for a given context:
- tenant_id
- workspace_id
- user_id
- project_id / project_profile

This ensures that only "legal and applicable" playbooks enter the execution pipeline.
"""

import logging
from typing import List, Optional, Dict, Any
from backend.app.models.playbook import Playbook, PlaybookOwnerType, PlaybookVisibility
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.project.project_manager import ProjectManager

logger = logging.getLogger(__name__)


class PlaybookScopeResolver:
    """
    Resolves effective playbooks for a given execution context

    Decision factors:
    1. Playbook owner_type + visibility (who can see/use)
    2. ProjectCapabilityProfile (what capabilities are allowed in this project)
    3. Project type matching (writing project shouldn't see devops playbooks)
    4. Tool whitelist (if project has tool restrictions)
    """

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.project_manager = ProjectManager(store)
        from backend.app.services.playbook_service import PlaybookService

        self.playbook_service = PlaybookService(store)

    async def resolve_effective_playbooks(
        self,
        tenant_id: Optional[str],
        workspace_id: str,
        user_id: str,
        project_id: Optional[str] = None,
        project_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Resolve effective playbooks for execution context

        Args:
            tenant_id: Tenant ID (optional, for multi-tenant)
            workspace_id: Workspace ID
            user_id: Current user ID
            project_id: Project ID (optional)
            project_profile: ProjectCapabilityProfile (optional)

        Returns:
            List of effective playbooks (dict format for ExecutionPlanGenerator)
        """
        all_candidates = await self._list_visible_playbooks(
            tenant_id=tenant_id, workspace_id=workspace_id, user_id=user_id
        )

        scoped = [
            pb
            for pb in all_candidates
            if self._is_playbook_visible_to_user_in_workspace(
                pb, user_id, workspace_id, tenant_id
            )
        ]

        if project_profile:
            scoped = [
                pb
                for pb in scoped
                if self._matches_project_capability_profile(pb, project_profile)
            ]

        if project_id:
            project = await self.project_manager.get_project(
                project_id, workspace_id=workspace_id
            )
            if project:
                scoped = [
                    pb for pb in scoped if self._matches_project_type(pb, project)
                ]

        executable_playbooks = [
            pb
            for pb in scoped
            if pb.get("visibility") != PlaybookVisibility.PUBLIC_TEMPLATE
        ]
        template_playbooks = [
            pb
            for pb in scoped
            if pb.get("visibility") == PlaybookVisibility.PUBLIC_TEMPLATE
        ]

        logger.info(
            f"Resolved {len(executable_playbooks)} executable playbooks, {len(template_playbooks)} templates "
            f"from {len(all_candidates)} candidates "
            f"(workspace={workspace_id}, user={user_id}, project={project_id})"
        )

        return executable_playbooks

    async def _list_visible_playbooks(
        self, tenant_id: Optional[str], workspace_id: str, user_id: str
    ) -> List[Dict[str, Any]]:
        """
        List all playbooks visible to this context

        This method delegates to PlaybookService for raw queries,
        then combines results.

        Includes:
        - System playbooks (owner_type=system)
        - Tenant playbooks (owner_type=tenant, tenant_id matches)
        - Workspace playbooks (owner_type=workspace, workspace_id matches)
        - User playbooks (owner_type=user, user_id matches)
        """
        all_candidates = []

        system_playbooks = await self.playbook_service.list_by_owner_type(
            owner_type=PlaybookOwnerType.SYSTEM
        )
        all_candidates.extend(system_playbooks)

        if tenant_id:
            tenant_playbooks = await self.playbook_service.list_by_owner_type(
                owner_type=PlaybookOwnerType.TENANT, owner_id=tenant_id
            )
            all_candidates.extend(tenant_playbooks)

        if workspace_id:
            workspace_playbooks = await self.playbook_service.list_for_workspace(
                workspace_id
            )
            all_candidates.extend(workspace_playbooks)
        # Note: When workspace_id is None, we still get system playbooks from above
        # and can optionally include all playbooks for testing

        user_playbooks = await self.playbook_service.list_for_user(user_id)
        all_candidates.extend(user_playbooks)

        unique_by_code = {}
        for pb in all_candidates:
            # Handle both dict and PlaybookMetadata objects
            if isinstance(pb, dict):
                code = pb.get("playbook_code")
                owner_type = pb.get("owner_type")
            else:
                # PlaybookMetadata object
                code = getattr(pb, "playbook_code", None)
                owner_type = getattr(pb, "owner_type", None)

            if code and code not in unique_by_code:
                # Convert to dict if needed
                if not isinstance(pb, dict):
                    pb_dict = (
                        pb.dict()
                        if hasattr(pb, "dict")
                        else pb.model_dump() if hasattr(pb, "model_dump") else {}
                    )
                else:
                    pb_dict = pb
                unique_by_code[code] = pb_dict
            elif code:
                existing = unique_by_code[code]
                existing_priority = self._get_owner_priority(
                    existing.get("owner_type")
                    if isinstance(existing, dict)
                    else getattr(existing, "owner_type", None)
                )
                new_priority = self._get_owner_priority(owner_type)
                if new_priority < existing_priority:
                    # Convert to dict if needed
                    if not isinstance(pb, dict):
                        pb_dict = (
                            pb.dict()
                            if hasattr(pb, "dict")
                            else pb.model_dump() if hasattr(pb, "model_dump") else {}
                        )
                    else:
                        pb_dict = pb
                    unique_by_code[code] = pb_dict

        return list(unique_by_code.values())

    def _get_owner_priority(self, owner_type: Any) -> int:
        """
        Get priority for owner type (lower = higher priority)

        Used for deduplication: prefer system > tenant > workspace > user
        """
        if isinstance(owner_type, str):
            owner_type = PlaybookOwnerType(owner_type)

        priority_map = {
            PlaybookOwnerType.SYSTEM: 0,
            PlaybookOwnerType.TENANT: 1,
            PlaybookOwnerType.WORKSPACE: 2,
            PlaybookOwnerType.USER: 3,
            PlaybookOwnerType.EXTERNAL_PROVIDER: 4,
        }
        return priority_map.get(owner_type, 99)

    def _is_playbook_visible_to_user_in_workspace(
        self,
        playbook: Dict[str, Any],
        user_id: str,
        workspace_id: str,
        tenant_id: Optional[str],
    ) -> bool:
        """
        Check if playbook is visible to user in workspace

        Rules:
        - private: Only if owner_id == user_id
        - workspace_shared:
          * If owner_type=WORKSPACE: visible to all users in that workspace
          * If owner_type=USER: requires explicit workspace sharing via shared_with_workspaces
        - tenant_shared: Only if owner_type=TENANT (workspace-owned playbooks cannot be tenant_shared)
        - public_template: Always visible (but separated from executable playbooks)
        """
        owner_type_raw = playbook.get("owner_type", PlaybookOwnerType.USER)
        owner_type = (
            owner_type_raw
            if isinstance(owner_type_raw, PlaybookOwnerType)
            else PlaybookOwnerType(owner_type_raw)
        )

        visibility_raw = playbook.get("visibility", PlaybookVisibility.WORKSPACE_SHARED)
        visibility = (
            visibility_raw
            if isinstance(visibility_raw, PlaybookVisibility)
            else PlaybookVisibility(visibility_raw)
        )

        owner_id = playbook.get("owner_id", "")
        shared_with_workspaces = playbook.get("shared_with_workspaces", [])

        if visibility == PlaybookVisibility.PRIVATE:
            return owner_id == user_id

        if visibility == PlaybookVisibility.WORKSPACE_SHARED:
            if owner_type == PlaybookOwnerType.SYSTEM:
                return True
            if owner_type == PlaybookOwnerType.WORKSPACE:
                return owner_id == workspace_id
            if owner_type == PlaybookOwnerType.USER:
                if owner_id == user_id:
                    return True
                return workspace_id in shared_with_workspaces

        if visibility == PlaybookVisibility.TENANT_SHARED:
            if owner_type == PlaybookOwnerType.TENANT:
                return tenant_id and owner_id == tenant_id
            if owner_type == PlaybookOwnerType.WORKSPACE:
                logger.warning(
                    f"Playbook {playbook.get('playbook_code')} has owner_type=WORKSPACE but visibility=TENANT_SHARED. "
                    f"This combination is not allowed. Use owner_type=TENANT instead."
                )
                return False

        if visibility == PlaybookVisibility.PUBLIC_TEMPLATE:
            return True

        return False

    def _matches_project_capability_profile(
        self, playbook: Dict[str, Any], project_profile: Dict[str, Any]
    ) -> bool:
        """
        Check if playbook matches project capability profile

        Project profile may have:
        - enabled_capabilities: List of allowed capability tags
        - enabled_playbook_ids: Whitelist of specific playbook IDs
        - blocked_playbook_ids: Blacklist of specific playbook IDs
        - enabled_tools: List of allowed tools (v2 feature, not implemented in v1)
        - blocked_tools: List of blocked tools (v2 feature, not implemented in v1)

        allowed_tools in PlaybookMetadata is a v1 reserved field, not enforced in v1.
        """
        playbook_code = playbook.get("playbook_code", "")
        blocked = project_profile.get("blocked_playbook_ids", [])
        if playbook_code in blocked:
            return False

        enabled = project_profile.get("enabled_playbook_ids", [])
        if enabled and playbook_code not in enabled:
            return False

        enabled_capabilities = project_profile.get("enabled_capabilities", [])
        if enabled_capabilities:
            playbook_tags = playbook.get("capability_tags", [])
            if not any(tag in enabled_capabilities for tag in playbook_tags):
                return False

        return True

    def _matches_project_type(
        self, playbook: Dict[str, Any], project: "Project"
    ) -> bool:
        """
        Check if playbook matches project type

        If playbook has project_types, it must include project.type
        """
        playbook_project_types = playbook.get("project_types", [])
        if not playbook_project_types:
            return True

        project_type = getattr(project, "type", None)
        if not project_type:
            return True

        return project_type in playbook_project_types
