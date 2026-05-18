"""Context bridge helpers for MeetingPromptsMixin."""

from typing import Any, List

from backend.app.services.orchestration.meeting._prompt_context import (
    append_workspace_identity,
    build_asset_map_context,
    build_lens_context,
    build_previous_decisions_context,
    build_project_context,
    build_workflow_evidence_context,
    format_workspace_identity,
)


class MeetingPromptContextBridgeMixin:
    def _build_workspace_instruction_block(self) -> str:
        """Build workspace instruction block for meeting agent turns.

        Meeting agents have their own role definitions (facilitator/planner/
        critic/executor). Workspace instruction is filtered to avoid
        role conflict:
          - persona:    EXCLUDED (would override agent role)
          - anti_goals: EXCLUDED (would reject project-scoped tasks)
          - goals, style_rules, domain_context: INCLUDED as reference

        Returns raw body (no delimiters); caller wraps in its own block.
        Brief fallback is disabled to prevent unfiltered persona leaking.
        """
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        workspace = getattr(self, "workspace", None)
        block, _ = build_workspace_instruction_block(
            workspace,
            caller="meeting",
            exclude_fields=("persona", "anti_goals"),
            fallback_to_brief=False,
            raw_body=True,
        )
        return block
    def _build_project_context(self) -> str:
        """Fetch project data and recent activity to provide meeting context."""
        return build_project_context(self)

    def _build_asset_map_context(self) -> str:
        """Build workspace group asset map for cross-workspace dispatch routing."""
        return build_asset_map_context(self)

    @staticmethod
    def _format_workspace_identity(ws: Any, parts: List[str]) -> None:
        """Append workspace identity lines from blueprint + suggestions."""
        format_workspace_identity(ws, parts)

    def _append_workspace_identity(
        self, ws_store: Any, ws_id: str, parts: List[str]
    ) -> None:
        """Look up a workspace by ID and append its identity card."""
        append_workspace_identity(self, ws_store, ws_id, parts)

    def _build_lens_context(self) -> str:
        """Build lens context block for prompt injection."""
        return build_lens_context(self)

    def _build_previous_decisions_context(self) -> str:
        """Build previous meeting decisions context from DECISION_FINAL events."""
        return build_previous_decisions_context(self)

    def _build_workflow_evidence_context(self) -> str:
        """Build workflow evidence packet for prompt injection."""
        return build_workflow_evidence_context(self)
