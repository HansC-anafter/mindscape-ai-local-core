"""Remote execution helpers for PlaybookRunExecutor."""

from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

DispatchRemoteExecution = Callable[..., Awaitable[Dict[str, Any]]]
ResolveAndAcquireBackend = Callable[[str], Tuple[str, Optional[str]]]
ReleaseBackend = Callable[[Optional[str]], None]
ExecutionDispatchHelpers = Callable[
    [],
    Tuple[
        DispatchRemoteExecution,
        ResolveAndAcquireBackend,
        ReleaseBackend,
    ],
]


def normalize_execution_backend_hint(
    inputs: Optional[Dict[str, Any]],
) -> Optional[str]:
    """Normalize caller-supplied execution backend hints."""
    if not isinstance(inputs, dict):
        return None
    value = inputs.get("execution_backend")
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"auto", "runner", "in_process", "remote"}:
        return normalized
    return None


async def maybe_dispatch_remote_execution(
    *,
    playbook_code: str,
    profile_id: str,
    normalized_inputs: Dict[str, Any],
    workspace_id: Optional[str],
    project_id: Optional[str],
    execution_dispatch_helpers_fn: ExecutionDispatchHelpers,
) -> Optional[Dict[str, Any]]:
    """Dispatch a playbook remotely when the caller requested the remote backend."""
    requested_backend = normalize_execution_backend_hint(normalized_inputs)
    if requested_backend != "remote":
        return None

    (
        dispatch_remote_execution,
        resolve_and_acquire_backend,
        release_backend,
    ) = execution_dispatch_helpers_fn()

    final_backend, pool_acquired_backend = resolve_and_acquire_backend(
        requested_backend
    )
    try:
        if final_backend != "remote":
            normalized_inputs["execution_backend"] = final_backend
            return None

        remote_job_type = normalized_inputs.get("remote_job_type")
        if remote_job_type not in {"playbook", "tool", "chain"}:
            remote_job_type = "playbook"

        remote_request_payload = normalized_inputs.get("remote_request_payload")
        if not isinstance(remote_request_payload, dict):
            remote_request_payload = None

        remote_capability_code = normalized_inputs.get("remote_capability_code")
        if not isinstance(remote_capability_code, str) or not remote_capability_code:
            remote_capability_code = None

        tenant_id = normalized_inputs.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            tenant_id = None

        execution_id = normalized_inputs.get("execution_id")
        if not isinstance(execution_id, str) or not execution_id:
            execution_id = None

        trace_id = normalized_inputs.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id:
            trace_id = None

        return await dispatch_remote_execution(
            playbook_code=playbook_code,
            inputs=normalized_inputs,
            workspace_id=workspace_id,
            profile_id=profile_id,
            project_id=project_id,
            tenant_id=tenant_id,
            execution_id=execution_id,
            trace_id=trace_id,
            remote_job_type=remote_job_type,
            remote_request_payload=remote_request_payload,
            capability_code=remote_capability_code,
        )
    finally:
        release_backend(pool_acquired_backend)
