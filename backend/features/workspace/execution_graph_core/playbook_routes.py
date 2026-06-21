"""Playbook DAG routes for execution graph APIs."""

import logging

from fastapi import HTTPException

from backend.features.workspace.execution_graph_core.models import (
    PlaybookDAGResponse,
    PlaybookStepResponse,
)

logger = logging.getLogger(__name__)


async def get_playbook_dag(
    playbook_code: str,
) -> PlaybookDAGResponse:
    """
    Get playbook details and step DAG for expansion view.

    Returns the playbook structure including metadata, steps, and IO definitions.
    """
    try:
        from backend.app.services.playbook_registry import PlaybookRegistry

        registry = PlaybookRegistry()
        playbook_run = await registry.get_playbook(playbook_code)

        if not playbook_run:
            raise HTTPException(
                status_code=404,
                detail=f"Playbook not found: {playbook_code}",
            )

        playbook_json = playbook_run.playbook_json

        steps = []
        if playbook_json and playbook_json.steps:
            for step in playbook_json.steps:
                steps.append(
                    PlaybookStepResponse(
                        id=step.id,
                        tool=step.tool,
                        tool_slot=step.tool_slot,
                        depends_on=step.depends_on or [],
                        has_gate=step.gate is not None,
                        gate_type=step.gate.type if step.gate else None,
                    )
                )

        return PlaybookDAGResponse(
            playbook_code=playbook_code,
            name=(
                playbook_run.playbook.metadata.name
                if playbook_run.playbook
                else playbook_code
            ),
            description=(
                playbook_run.playbook.metadata.description
                if playbook_run.playbook
                else None
            ),
            steps=steps,
            inputs=(
                {key: value.dict() for key, value in (playbook_json.inputs or {}).items()}
                if playbook_json
                else {}
            ),
            outputs=(
                {
                    key: value.dict()
                    for key, value in (playbook_json.outputs or {}).items()
                }
                if playbook_json
                else {}
            ),
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get playbook DAG: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


def register_playbook_routes(router) -> None:
    """Register playbook routes on the public execution graph router."""
    router.get("/playbook/{playbook_code}", response_model=PlaybookDAGResponse)(
        get_playbook_dag
    )
