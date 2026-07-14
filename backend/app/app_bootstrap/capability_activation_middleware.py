from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.pack_activation_service import PackActivationService
from backend.app.services.capability_api_loader import (
    activate_capability_api_code,
    capability_api_registration_complete,
    find_seeded_capability_for_path,
    get_capability_api_activation_policy,
    refresh_seeded_capability_descriptors,
)

logger = logging.getLogger(__name__)

_ACTIVATION_TASKS_STATE_KEY = "capability_request_activation_tasks"


def _activation_tasks(request: Request) -> dict[str, asyncio.Task]:
    tasks = getattr(request.app.state, _ACTIVATION_TASKS_STATE_KEY, None)
    if tasks is None:
        tasks = {}
        setattr(request.app.state, _ACTIVATION_TASKS_STATE_KEY, tasks)
    return tasks


async def _activate_capability_once(
    request: Request,
    *,
    capability_code: str,
    activation_service: PackActivationService,
) -> None:
    if capability_api_registration_complete(request.app, capability_code):
        return

    tasks = _activation_tasks(request)
    task = tasks.get(capability_code)
    if task is None or task.done():
        task = asyncio.create_task(
            asyncio.to_thread(
                activate_capability_api_code,
                app=request.app,
                capability_code=capability_code,
                activation_mode="request_activate",
                activation_service=activation_service,
            )
        )
        tasks[capability_code] = task
    try:
        await asyncio.shield(task)
    finally:
        if task.done() and tasks.get(capability_code) is task:
            tasks.pop(capability_code, None)


async def ensure_capability_activation_for_request(
    request: Request,
) -> Optional[JSONResponse]:
    """
    Lazily activate seeded capability APIs on first request when startup policy is seed_only.
    """
    if get_capability_api_activation_policy() != "seed_only":
        return None

    if request.method.upper() == "OPTIONS":
        return None

    capability_code = find_seeded_capability_for_path(request.app, request.url.path)
    if (
        not capability_code
        and request.url.path.startswith("/api/v1/capabilities/")
    ):
        refresh_seeded_capability_descriptors(request.app)
        capability_code = find_seeded_capability_for_path(request.app, request.url.path)
    if not capability_code:
        return None

    if capability_api_registration_complete(request.app, capability_code):
        return None

    activation_service = getattr(
        request.app.state, "capability_activation_service", None
    ) or PackActivationService()

    try:
        started_at = time.monotonic()
        await _activate_capability_once(
            request,
            capability_code=capability_code,
            activation_service=activation_service,
        )
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        if elapsed_ms >= 1000:
            logger.info(
                "Request-time capability activation completed for %s in %dms",
                capability_code,
                elapsed_ms,
            )
    except Exception as exc:
        logger.error(
            "Request-time capability activation failed for %s (%s): %s",
            capability_code,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    f"Capability '{capability_code}' failed to activate for "
                    f"path {request.url.path}: {exc}"
                )
            },
        )

    return None
