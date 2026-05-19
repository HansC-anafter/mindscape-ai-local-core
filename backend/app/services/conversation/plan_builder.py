"""Execution plan builder facade."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...models.workspace import ExecutionPlan, SideEffectLevel, TaskPlan
from ...services.conversation.plan_builder_core.execution_plan import (
    generate_execution_plan as generate_execution_plan_helper,
)
from ...services.conversation.plan_builder_core.llm_generation import (
    generate_llm_plan as generate_llm_plan_helper,
)
from ...services.conversation.plan_builder_core.llm_trace import utc_now as _utc_now
from ...services.conversation.plan_builder_core.pack_policy import (
    check_pack_tools_configured as check_pack_tools_configured_helper,
    determine_side_effect_level as determine_side_effect_level_helper,
    get_pack_id_from_playbook_code as get_pack_id_from_playbook_code_helper,
    is_pack_available as is_pack_available_helper,
)
from ...services.conversation.plan_builder_core.runtime import (
    ensure_external_backend_loaded as ensure_external_backend_loaded_helper,
    select_model_for_plan as select_model_for_plan_helper,
)


class PlanBuilder:
    """Build execution plans and determine pack side-effect policy."""

    def __init__(
        self,
        store,
        default_locale: str = "en",
        capability_profile: Optional[str] = None,
        stage_router: Optional[Any] = None,
        model_name: Optional[str] = None,
    ):
        """Initialize PlanBuilder."""
        self.store = store
        self.default_locale = default_locale
        self.capability_profile = capability_profile
        self.stage_router = stage_router
        self.model_name = model_name
        from ...services.config_store import ConfigStore

        self.config_store = ConfigStore()
        self.external_backend = None
        self._external_backend_loaded = False
        self._llm_manager_cache: Dict[str, Any] = {}

    def _select_model_for_plan(
        self, risk_level: str = "read", profile_id: Optional[str] = None
    ) -> str:
        """Delegate model selection to the extracted runtime helper."""
        return select_model_for_plan_helper(
            self,
            risk_level=risk_level,
            profile_id=profile_id,
        )

    async def _ensure_external_backend_loaded(self, profile_id: Optional[str] = None):
        """Delegate external backend loading to the extracted runtime helper."""
        await ensure_external_backend_loaded_helper(self, profile_id=profile_id)

    async def _create_or_link_phase(
        self,
        execution_plan: "ExecutionPlan",
        project_id: str,
        message_id: str,
        project_assignment_decision: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Retained facade for compatibility with callers/tests."""
        from ...services.conversation.plan_builder_core.runtime import (
            create_or_link_phase as create_or_link_phase_helper,
        )

        await create_or_link_phase_helper(
            self,
            execution_plan=execution_plan,
            project_id=project_id,
            message_id=message_id,
            project_assignment_decision=project_assignment_decision,
        )

    def is_pack_available(self, pack_id: str) -> bool:
        """Delegate pack availability checks to the extracted helper."""
        return is_pack_available_helper(pack_id)

    def check_pack_tools_configured(self, pack_id: str) -> bool:
        """Delegate tool-configuration checks to the extracted helper."""
        return check_pack_tools_configured_helper(pack_id)

    def determine_side_effect_level(self, pack_id: str) -> SideEffectLevel:
        """Delegate side-effect policy lookup to the extracted helper."""
        return determine_side_effect_level_helper(pack_id)

    async def _generate_llm_plan(
        self,
        message: str,
        files: List[str],
        workspace_id: str,
        profile_id: str,
        available_packs: List[str],
        project_id: Optional[str] = None,
        project_assignment_decision: Optional[Dict[str, Any]] = None,
        thread_id: Optional[str] = None,
    ) -> List[TaskPlan]:
        """Generate an execution plan using the extracted LLM helper."""
        return await generate_llm_plan_helper(
            self,
            message=message,
            files=files,
            workspace_id=workspace_id,
            profile_id=profile_id,
            available_packs=available_packs,
            project_id=project_id,
            project_assignment_decision=project_assignment_decision,
            thread_id=thread_id,
        )

    async def generate_execution_plan(
        self,
        message: str,
        files: List[str],
        workspace_id: str,
        profile_id: str,
        message_id: Optional[str] = None,
        use_llm: bool = True,
        project_id: Optional[str] = None,
        project_assignment_decision: Optional[Dict[str, Any]] = None,
        effective_playbooks: Optional[List[Dict[str, Any]]] = None,
        available_playbooks: Optional[List[Dict[str, Any]]] = None,
        routing_decision: Optional[Any] = None,
        thread_id: Optional[str] = None,
    ) -> ExecutionPlan:
        """Generate an execution plan using LLM-first, rule-based fallback."""
        return await generate_execution_plan_helper(
            self,
            message=message,
            files=files,
            workspace_id=workspace_id,
            profile_id=profile_id,
            message_id=message_id,
            use_llm=use_llm,
            project_id=project_id,
            project_assignment_decision=project_assignment_decision,
            effective_playbooks=effective_playbooks,
            available_playbooks=available_playbooks,
            routing_decision=routing_decision,
            thread_id=thread_id,
        )

    def _get_pack_id_from_playbook_code(self, playbook_code: str) -> Optional[str]:
        """Delegate playbook-to-pack resolution to the extracted helper."""
        return get_pack_id_from_playbook_code_helper(playbook_code)
