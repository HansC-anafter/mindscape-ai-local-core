"""Single post-fan-in handoff into the group knowledge writer."""

import asyncio
import logging
from typing import Any, Dict, Optional

from backend.app.services.knowledge_projection.contracts import (
    GroupSynthesisHandoff,
)


logger = logging.getLogger(__name__)


async def commit_group_synthesis(orchestrator: Any, task_ir_id: str) -> Optional[Dict]:
    snapshot = orchestrator._group_execution.snapshot
    committer = orchestrator._group_synthesis_committer
    if snapshot is None or committer is None:
        return None
    claims = []
    for phase_id in sorted(orchestrator._phase_results):
        result = orchestrator._phase_results[phase_id]
        phase_claims = result.get("group_synthesis_claims")
        if isinstance(phase_claims, list):
            claims.extend(phase_claims)
    if not claims:
        return None
    try:
        handoff = GroupSynthesisHandoff(
            run_id=task_ir_id,
            group_id=snapshot.group_id,
            topology_snapshot_id=snapshot.id,
            policy_revision="group_synthesis_v1",
            claims=claims,
        )
        receipt = await asyncio.to_thread(committer.commit, handoff)
        return receipt.model_dump(mode="json")
    except Exception as exc:
        logger.exception("Group synthesis commit failed for task %s", task_ir_id)
        return {"status": "failed", "error": str(exc)[:500]}
