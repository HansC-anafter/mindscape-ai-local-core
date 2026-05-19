"""Mind Lens resolution helper for CoordinatorFacade."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def resolve_mind_lens(*, execution_plan: Any, ctx: Any) -> None:
    """Resolve Mind Lens data when the optional cloud endpoint is configured."""
    if ctx.mind_lens is not None:
        return

    try:
        import httpx

        cloud_api_url = os.getenv("CLOUD_API_URL")
        if cloud_api_url:
            playbook_id = None
            if execution_plan.tasks:
                first_task = execution_plan.tasks[0]
                playbook_id = getattr(first_task, "playbook_id", None)

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{cloud_api_url}/mind-lens/resolve",
                    json={
                        "user_id": ctx.actor_id,
                        "workspace_id": ctx.workspace_id,
                        "playbook_id": playbook_id,
                        "role_hint": None,
                    },
                    timeout=5.0,
                )
                if response.status_code == 200:
                    ctx.mind_lens = response.json()
    except Exception as exc:
        logger.debug("Mind Lens not available: %s", exc)
