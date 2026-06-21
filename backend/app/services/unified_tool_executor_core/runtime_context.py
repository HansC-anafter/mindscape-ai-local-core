from typing import Any, Dict
import inspect
import logging

logger = logging.getLogger("backend.app.services.unified_tool_executor")


def _build_capability_runtime_context() -> Dict[str, Any]:
    try:
        from backend.app.services.service_endpoint_registry import (
            build_runtime_service_endpoint_context,
        )

        return build_runtime_service_endpoint_context()
    except Exception:
        logger.debug("Capability runtime context unavailable", exc_info=True)
        return {"service_endpoints": {"version": 1, "endpoints": []}}


def _inject_runtime_context(
    tool_kwargs: Dict[str, Any],
    signature: inspect.Signature,
) -> Dict[str, Any]:
    injected = dict(tool_kwargs)
    runtime_context = None
    if "runtime_context" in signature.parameters:
        runtime_context = _build_capability_runtime_context()
        injected.setdefault("runtime_context", runtime_context)
    if "execution_context" in signature.parameters:
        runtime_context = runtime_context or _build_capability_runtime_context()
        injected.setdefault("execution_context", {"runtime_context": runtime_context})
    return injected
