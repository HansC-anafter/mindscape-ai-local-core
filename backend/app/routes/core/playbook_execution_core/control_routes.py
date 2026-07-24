import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from backend.app.routes.core.execution_dispatch import (
    build_external_authorization_context,
    dispatch_remote_execution,
    get_execution_mode,
    release_backend,
    resolve_and_acquire_backend,
)
from backend.app.routes.core.execution_hooks import async_invoke_lifecycle_hook
from backend.app.routes.core.execution_metadata import (
    resolve_runner_metadata,
    should_route_through_runner,
)
from backend.app.routes.core.execution_schemas import (
    StartExecutionRequest,
)
from backend.app.services.runner_topology import DEFAULT_LOCAL_QUEUE_PARTITION
from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.services.workspace_capability_admission import (
    AdmissionDenied,
)
from backend.app.services.workspace_capability_admission.external_execution_adapter import (
    ExternalAuthorizationDenied,
)
from backend.app.services.playbook_execution_admission import (
    admit_playbook_root,
)

from .state import _utc_now, logger, playbook_executor, playbook_service

router = APIRouter()

@router.post("/execute/start")
async def start_playbook_execution(
    http_request: Request,
    playbook_code: str = Query(..., description="Playbook code to execute"),
    profile_id: str = Query("default-user", description="Profile ID"),
    workspace_id: Optional[str] = Query(
        None,
        description="Workspace ID for state persistence (required for multi-turn conversations)",
    ),
    project_id: Optional[str] = Query(
        None, description="Project ID for sandbox context"
    ),
    target_language: Optional[str] = Query(
        None, description="Target language for output (e.g., 'zh-TW', 'en')"
    ),
    variant_id: Optional[str] = Query(
        None, description="Optional personalized variant ID to use"
    ),
    auto_execute: Optional[bool] = Query(
        None, description="If true, skip confirmations and execute tools directly"
    ),
    execution_backend: Optional[str] = Query(
        None,
        description="Neutral execution backend hint: auto|runner|in_process. Routing is always decided by backend.",
    ),
    product_surface_id: Optional[str] = Query(None),
    active_group_id: Optional[str] = Query(None),
    observed_topology_revision: Optional[int] = Query(None, ge=1),
    auth: AuthContext = Depends(get_current_user),
    request: Optional[StartExecutionRequest] = Body(
        None, description="Optional inputs for the playbook"
    ),
):
    """
    Start a new Playbook execution

    Returns the execution_id and initial assistant message

    Note: workspace_id is required for multi-turn conversations to persist execution state.
    Without it, /continue calls will fail with "Execution not found".

    Set auto_execute=true to skip confirmations and execute tools directly (useful for automated testing).
    """
    try:
        inputs = request.inputs if request else None
        final_target_language = target_language or (
            request.target_language if request else None
        )
        final_variant_id = variant_id or (request.variant_id if request else None)
        final_remote_job_type = (
            request.remote_job_type
            if request and request.remote_job_type
            else (
                inputs.get("remote_job_type")
                if isinstance(inputs, dict) and inputs.get("remote_job_type")
                else "playbook"
            )
        )
        final_remote_request_payload = (
            request.remote_request_payload
            if request and isinstance(request.remote_request_payload, dict)
            else (
                inputs.get("remote_request_payload")
                if isinstance(inputs, dict)
                and isinstance(inputs.get("remote_request_payload"), dict)
                else None
            )
        )
        final_remote_capability_code = (
            request.remote_capability_code
            if request and request.remote_capability_code
            else (
                inputs.get("remote_capability_code")
                if isinstance(inputs, dict) and inputs.get("remote_capability_code")
                else None
            )
        )

        # Auto-assign variant if not explicitly provided
        if not final_variant_id:
            try:
                from backend.app.services.variant_assigner import assign_variant

                final_variant_id = assign_variant(
                    playbook_code=playbook_code,
                    variant_id=final_variant_id,
                    registry=playbook_service.registry,
                    workspace_id=workspace_id,
                    target_language=final_target_language,
                )
            except Exception as e:
                logger.warning(f"Variant auto-assignment failed (non-fatal): {e}")
        final_auto_execute = auto_execute or (request.auto_execute if request else None)
        final_execution_backend = (
            (
                execution_backend
                or (request.execution_backend if request else None)
                or "auto"
            )
            if isinstance(
                execution_backend
                or (request.execution_backend if request else None)
                or "auto",
                str,
            )
            else "auto"
        )
        final_execution_backend = (final_execution_backend or "auto").strip().lower()
        if final_execution_backend not in {"auto", "runner", "in_process", "remote"}:
            final_execution_backend = "auto"

        # Extract workspace_id and project_id from inputs if not provided as query params
        # (must happen before any backend branch that needs workspace_id)
        final_workspace_id = workspace_id or (
            inputs.get("workspace_id") if inputs else None
        )
        final_project_id = project_id or (inputs.get("project_id") if inputs else None)

        # Pool-aware backend selection
        final_execution_backend, pool_acquired_backend = resolve_and_acquire_backend(
            final_execution_backend
        )
        admission = None
        root_execution_id = (
            request.execution_id
            if request and request.execution_id
            else str(uuid.uuid4())
        )
        trace_id = (
            request.trace_id
            if request and request.trace_id
            else root_execution_id
        )
        if final_workspace_id:
            resolved_surface = product_surface_id or (
                inputs.get("product_surface_id")
                if isinstance(inputs, dict)
                else None
            )
            admission = await admit_playbook_root(
                workspace_id=final_workspace_id,
                product_surface_id=resolved_surface,
                active_group_id=active_group_id,
                observed_topology_revision=observed_topology_revision,
                playbook_code=playbook_code,
                execution_backend=final_execution_backend,
                remote_ingress_verified=(
                    http_request.headers.get(
                        "x-mindscape-remote-ingress"
                    ) == "remote_workbench"
                ),
                auth=auth,
                trace_id=trace_id,
                root_execution_id=root_execution_id,
            )
            if inputs is None:
                inputs = {}
            inputs["execution_admission_snapshot"] = (
                admission.snapshot.model_dump(mode="json")
            )

        # Remote backend: dispatch to cloud control plane via CloudConnector
        if final_execution_backend == "remote":
            try:
                return await dispatch_remote_execution(
                    playbook_code=playbook_code,
                    inputs=inputs,
                    workspace_id=final_workspace_id,
                    profile_id=profile_id,
                    project_id=final_project_id,
                    tenant_id=request.tenant_id if request else None,
                    execution_id=root_execution_id,
                    trace_id=trace_id,
                    remote_job_type=final_remote_job_type,
                    remote_request_payload=final_remote_request_payload,
                    capability_code=final_remote_capability_code,
                    external_authorization_context=(
                        build_external_authorization_context(
                            admission.external_decision
                            if admission is not None
                            else None
                        )
                    ),
                )
            finally:
                release_backend(pool_acquired_backend)

        # Inject auto_execute into inputs for downstream processing
        if final_auto_execute and inputs:
            inputs["auto_execute"] = True
        elif final_auto_execute:
            inputs = {"auto_execute": True}

        # Inject neutral execution backend hint into inputs for downstream processing
        if inputs and isinstance(inputs, dict):
            inputs["execution_backend"] = final_execution_backend
        elif inputs is None:
            inputs = {"execution_backend": final_execution_backend}

        # Update user_meta use_count when playbook is executed
        try:
            from backend.app.services.mindscape_store import MindscapeStore

            store = MindscapeStore()
            await asyncio.to_thread(
                store.update_user_meta,
                profile_id,
                playbook_code,
                {
                    "increment_use_count": True,
                    "last_used_at": _utc_now().isoformat(),
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to update user_meta for playbook {playbook_code}: {e}"
            )

        playbook_run = await playbook_service.load_playbook_run(
            playbook_code=playbook_code,
            locale="zh-TW",
            workspace_id=final_workspace_id,
        )
        runner_metadata = resolve_runner_metadata(playbook_run)
        exec_mode = get_execution_mode()
        prefer_runner = should_route_through_runner(
            playbook_run=playbook_run,
            requested_backend=final_execution_backend,
            env_execution_mode=exec_mode,
        )
        if prefer_runner and final_execution_backend == "in_process":
            logger.warning(
                "Ignoring execution_backend=in_process for runner-only playbook %s",
                playbook_code,
            )
            final_execution_backend = "runner"

        if prefer_runner:
            if (
                playbook_run
                and playbook_run.get_execution_mode() == "workflow"
                and playbook_run.has_json()
            ):
                execution_id = (
                    admission.snapshot.root_execution_id
                    if admission is not None
                    else root_execution_id
                )
                normalized_inputs = inputs.copy() if isinstance(inputs, dict) else {}
                normalized_inputs["execution_id"] = execution_id
                normalized_inputs["execution_backend"] = final_execution_backend
                if final_workspace_id and "workspace_id" not in normalized_inputs:
                    normalized_inputs["workspace_id"] = final_workspace_id
                if final_project_id and "project_id" not in normalized_inputs:
                    normalized_inputs["project_id"] = final_project_id
                if profile_id and "profile_id" not in normalized_inputs:
                    normalized_inputs["profile_id"] = profile_id

                from backend.app.services.stores.tasks_store import TasksStore
                from backend.app.services.mindscape_store import MindscapeStore
                from backend.app.models.workspace import (
                    PlaybookExecution,
                    Task,
                    TaskStatus,
                )

                store = MindscapeStore()
                tasks_store = TasksStore()
                executions_store = store.playbook_executions

                # Calculate total_steps from playbook for frontend progress display
                total_steps = (
                    len(playbook_run.playbook_json.steps)
                    if playbook_run.playbook_json and playbook_run.playbook_json.steps
                    else 1
                )
                playbook_name = (
                    playbook_run.playbook.metadata.name
                    if playbook_run.playbook and playbook_run.playbook.metadata
                    else playbook_code
                )

                if executions_store and final_workspace_id:
                    await asyncio.to_thread(
                        executions_store.create_execution,
                        PlaybookExecution(
                            id=execution_id,
                            workspace_id=final_workspace_id,
                            playbook_code=playbook_code,
                            thread_id=(
                                normalized_inputs.get("thread_id")
                                if isinstance(normalized_inputs, dict)
                                else None
                            ),
                            intent_instance_id=None,
                            status="queued",
                            phase="queue",
                            last_checkpoint=None,
                            progress_log_path=None,
                            feature_list_path=None,
                            metadata={
                                "execution_mode": "runner",
                                "execution_backend_hint": final_execution_backend,
                                "playbook_name": playbook_name,
                                "resource_class": runner_metadata.get("resource_class"),
                                "queue_partition": runner_metadata.get("queue_partition")
                                or runner_metadata.get("queue_shard")
                                or DEFAULT_LOCAL_QUEUE_PARTITION,
                                "queue_shard": runner_metadata.get("queue_shard")
                                or DEFAULT_LOCAL_QUEUE_PARTITION,
                                "runner_profile_hint": runner_metadata.get(
                                    "runner_profile_hint"
                                ),
                                "runtime_affinity": runner_metadata.get(
                                    "runtime_affinity"
                                ),
                            },
                            created_at=_utc_now(),
                            updated_at=_utc_now(),
                        ),
                    )

                await asyncio.to_thread(
                    tasks_store.create_task,
                    Task(
                        id=execution_id,
                        workspace_id=final_workspace_id,
                        message_id=str(uuid.uuid4()),
                        execution_id=execution_id,
                        project_id=final_project_id,
                        pack_id=playbook_code,
                        task_type="playbook_execution",
                        status=TaskStatus.PENDING,
                        queue_shard=runner_metadata.get("queue_shard")
                        or DEFAULT_LOCAL_QUEUE_PARTITION,
                        execution_context={
                            "playbook_code": playbook_code,
                            "playbook_name": playbook_name,
                            "execution_id": execution_id,
                            "status": "queued",
                            "execution_mode": "runner",
                            "execution_backend_hint": final_execution_backend,
                            "inputs": normalized_inputs,
                            "workspace_id": final_workspace_id,
                            "project_id": final_project_id,
                            "profile_id": profile_id,
                            "total_steps": total_steps,
                            "current_step_index": 0,
                            **(
                                {
                                    "execution_admission_snapshot": (
                                        admission.snapshot.model_dump(
                                            mode="json"
                                        )
                                    )
                                }
                                if admission is not None
                                else {}
                            ),
                            **runner_metadata,
                        },
                        created_at=_utc_now(),
                        started_at=None,
                    ),
                )

                # on_queue hooks are non-critical. Schedule them after enqueue
                # so queue callers do not wait on extra synchronous work.
                lifecycle_hooks_config = runner_metadata.get("lifecycle_hooks")
                if isinstance(lifecycle_hooks_config, dict):
                    on_queue = lifecycle_hooks_config.get("on_queue")
                    if on_queue and isinstance(on_queue, dict):
                        asyncio.create_task(
                            async_invoke_lifecycle_hook(
                                hook_name="on_queue",
                                hook_spec=on_queue,
                                normalized_inputs=normalized_inputs,
                                execution_context={
                                    "execution_id": execution_id,
                                    "workspace_id": final_workspace_id,
                                    "playbook_code": playbook_code,
                                },
                            )
                        )

                return {
                    "execution_mode": "workflow",
                    "playbook_code": playbook_code,
                    "execution_id": execution_id,
                    "status": "queued",
                    "result": {
                        "status": "queued",
                        "execution_id": execution_id,
                        "note": "Execution queued",
                    },
                }

        # Use unified executor (automatically selects execution mode)
        result = await playbook_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=inputs,
            workspace_id=final_workspace_id,
            project_id=final_project_id,
            target_language=final_target_language,
            variant_id=final_variant_id,
        )

        # Handle different return formats
        if result.get("execution_mode") == "conversation":
            # For conversation mode, result.result contains PlaybookRunner response
            return result.get("result", result)
        else:
            # For workflow mode, return workflow result with execution_id
            return {
                "execution_mode": result.get("execution_mode"),
                "playbook_code": result.get("playbook_code"),
                "execution_id": result.get("execution_id"),
                **result.get("result", {}),
            }
    except AdmissionDenied as e:
        raise HTTPException(
            status_code=403,
            detail={"error": e.code},
        ) from e
    except ExternalAuthorizationDenied as e:
        raise HTTPException(
            status_code=403,
            detail={"error": e.code},
        ) from e
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start playbook: {str(e)}"
        )
