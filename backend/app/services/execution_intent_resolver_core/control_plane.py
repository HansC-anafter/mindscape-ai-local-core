from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.app.models.runtime_execution_intent import WorkloadExecutionIntent
from backend.app.utils.cloud_integration import get_cloud_integration_api_base
from backend.app.services.execution_intent_resolver_core.workload import (
    normalize_optional_string,
    should_park_on_control_plane_unavailable,
    should_use_render_control_plane_preflight,
)


logger = logging.getLogger("backend.app.services.execution_intent_resolver")


def normalize_control_plane_site_key(
    intent_model: WorkloadExecutionIntent,
) -> Optional[str]:
    return normalize_optional_string(intent_model.site_key) or normalize_optional_string(
        os.getenv("SITE_KEY")
    )


def inspect_cloud_connector_connected_state() -> Optional[bool]:
    try:
        from backend.app.main import app

        connector = getattr(app.state, "cloud_connector", None)
    except Exception:
        connector = None

    if connector is None:
        return None

    try:
        is_connected = getattr(connector, "is_connected", None)
        if callable(is_connected):
            return bool(is_connected())
        return bool(is_connected)
    except Exception:
        logger.warning(
            "ExecutionIntentResolver: failed to inspect cloud connector state",
            exc_info=True,
        )
        return None


def resolve_execution_control_api_base() -> Optional[str]:
    return (
        normalize_optional_string(os.getenv("EXECUTION_CONTROL_API_URL"))
        or normalize_optional_string(os.getenv("SITE_HUB_API_URL"))
        or normalize_optional_string(os.getenv("CLOUD_API_URL"))
        or normalize_optional_string(get_cloud_integration_api_base())
    )


def probe_control_plane_runtime_availability(
    *,
    site_key: Optional[str],
    target_device_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    normalized_site_key = normalize_optional_string(site_key)
    if not normalized_site_key:
        return None

    base_url = resolve_execution_control_api_base()
    if not base_url:
        return None

    params = {"site_key": normalized_site_key}
    normalized_device_id = normalize_optional_string(target_device_id)
    if normalized_device_id:
        params["device_id"] = normalized_device_id

    request_url = (
        f"{base_url.rstrip('/')}/api/v1/executions/availability?{urlencode(params)}"
    )
    headers: Dict[str, str] = {}
    api_key = normalize_optional_string(os.getenv("CLOUD_API_KEY")) or normalize_optional_string(
        os.getenv("CLOUD_PROVIDER_TOKEN")
    )
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    device_id = normalize_optional_string(os.getenv("DEVICE_ID"))
    if device_id:
        headers["X-Device-Id"] = device_id

    try:
        with urlopen(Request(request_url, headers=headers), timeout=2.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.info(
            "ExecutionIntentResolver: control-plane runtime availability probe failed for site_key=%s device_id=%s",
            normalized_site_key,
            normalized_device_id,
            exc_info=True,
        )
        return None

    if not isinstance(payload, dict):
        return None
    return payload


def detect_runtime_block_reason(
    *,
    intent_model: Optional[WorkloadExecutionIntent],
    resolved_scope: Optional[str],
    route_metadata: Optional[Dict[str, Any]],
) -> Optional[str]:
    if not should_use_render_control_plane_preflight(
        intent_model=intent_model,
        resolved_scope=resolved_scope,
        route_metadata=route_metadata,
    ):
        return None

    connected = inspect_cloud_connector_connected_state()
    # When the app-level connector is configured but not connected yet, strict
    # cloud-required workloads would fail immediately in the workflow seam.
    if connected is False and should_park_on_control_plane_unavailable(intent_model):
        return "cloud_connector_disconnected"
    return None
