"""Start-execution orchestration for the playbook runner facade."""

import logging
import uuid
from typing import Any, Dict, Optional

from backend.app.services.playbook import PlaybookConversationManager, ToolListLoader
from backend.app.services.playbook_runner_core.bootstrap import (
    load_playbook_bundle,
    resolve_project_execution_context,
    resolve_variant,
)
from backend.app.services.playbook_runner_core.execution_runtime import (
    get_llm_provider,
    load_and_apply_executor_route_context,
    run_playbook_chat_completion,
    run_playbook_tool_loop,
)
from backend.app.services.playbook_runner_core.run_state import (
    build_run_state_changed_event,
)
from backend.app.services.playbook_runner_core.session_state import (
    preserve_sandbox_id_in_execution_context,
)

logger = logging.getLogger(__name__)


async def start_playbook_execution(
    runner: Any,
    *,
    playbook_code: str,
    profile_id: str,
    inputs: Optional[Dict[str, Any]] = None,
    workspace_id: Optional[str] = None,
    project_id: Optional[str] = None,
    target_language: Optional[str] = None,
    variant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Start a new playbook execution through the runner facade."""
    execution_id = ""
    last_run_state = "UNKNOWN"
    try:
        thread_id = inputs.get("thread_id") if inputs else None
        if thread_id and inputs:
            inputs = await runner.context_injector.inject_context(
                execution_id="",
                thread_id=thread_id,
                inputs=inputs,
            )

        from backend.app.services.playbook_loaders.json_loader import (
            PlaybookJsonLoader,
        )

        playbook, playbook_json, locale, total_steps = await load_playbook_bundle(
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            inputs=inputs,
            get_workspace_fn=runner.store.get_workspace,
            get_playbook_fn=runner.playbook_service.get_playbook,
            load_playbook_json_fn=PlaybookJsonLoader.load_playbook_json,
        )

        variant = resolve_variant(
            registry=runner.playbook_service.registry,
            playbook_code=playbook_code,
            variant_id=variant_id,
        )

        profile = runner.store.get_profile(profile_id)

        from backend.app.services.project.project_manager import ProjectManager
        from backend.app.services.project.project_sandbox_manager import (
            ProjectSandboxManager,
        )
        from backend.app.services.sandbox.playbook_integration import (
            SandboxPlaybookAdapter,
        )

        project_manager = ProjectManager(runner.store)
        sandbox_adapter = SandboxPlaybookAdapter(runner.store)
        legacy_sandbox_manager = ProjectSandboxManager(runner.store)

        async def _get_project(*, project_id: str, workspace_id: Optional[str]):
            return await project_manager.get_project(
                project_id,
                workspace_id=workspace_id,
            )

        async def _get_unified_sandbox(*, project_id: str, workspace_id: Optional[str]):
            sandbox_id = await sandbox_adapter.get_or_create_sandbox_for_project(
                project_id=project_id,
                workspace_id=workspace_id,
            )
            project_sandbox_path = (
                await sandbox_adapter.get_sandbox_path_for_compatibility(
                    project_id=project_id,
                    workspace_id=workspace_id,
                )
            )
            return sandbox_id, project_sandbox_path

        async def _get_legacy_sandbox_path(
            *, project_id: str, workspace_id: Optional[str]
        ):
            return await legacy_sandbox_manager.get_sandbox_path(
                project_id,
                workspace_id,
            )

        project_context = await resolve_project_execution_context(
            project_id=project_id,
            inputs=inputs,
            workspace_id=workspace_id,
            get_project_fn=_get_project,
            get_unified_sandbox_fn=_get_unified_sandbox,
            get_legacy_sandbox_path_fn=_get_legacy_sandbox_path,
        )
        project_id = project_context["project_id"]
        project_obj = project_context["project_obj"]
        project_sandbox_path = project_context["project_sandbox_path"]
        sandbox_id = project_context["sandbox_id"]
        if sandbox_id:
            if inputs is None:
                inputs = {}
            inputs["sandbox_id"] = sandbox_id

        execution_id = str(uuid.uuid4())

        try:
            ready_event = build_run_state_changed_event(
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                execution_id=execution_id,
                previous_state="UNKNOWN",
                new_state="READY",
                reason="playbook_execution_started",
                playbook_code=playbook_code,
                inputs=inputs,
            )
            runner.store.create_event(ready_event)
            last_run_state = "READY"
            logger.info(
                f"Emitted RUN_STATE_CHANGED event: UNKNOWN → READY for execution {execution_id}"
            )
        except Exception as exc:
            logger.warning(f"Failed to emit RUN_STATE_CHANGED event: {exc}")

        thread_id = inputs.get("thread_id") if inputs else None
        if thread_id and inputs:
            inputs = await runner.context_injector.inject_context(
                execution_id=execution_id,
                thread_id=thread_id,
                inputs=inputs,
            )

        if workspace_id:
            runner.task_manager.create_execution_task(
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                playbook_code=playbook_code,
                playbook_name=playbook.metadata.name,
                inputs=inputs,
                total_steps=total_steps,
            )

        final_target_language = (
            target_language or (inputs.get("target_language") if inputs else None) or None
        )
        final_locale = inputs.get("locale") if inputs else None
        auto_execute = inputs.get("auto_execute", False) if inputs else False

        conv_manager = PlaybookConversationManager(
            playbook=playbook,
            profile=profile,
            project=project_obj,
            locale=final_locale,
            target_language=final_target_language,
            workspace_id=workspace_id,
            auto_execute=auto_execute,
        )

        if auto_execute:
            logger.info(
                f"PlaybookRunner: Auto-execute mode enabled for execution {execution_id}"
            )

        if project_sandbox_path and inputs:
            inputs["project_sandbox_path"] = str(project_sandbox_path)
            logger.info(f"Project sandbox path set in inputs: {project_sandbox_path}")

        if workspace_id:
            profile_id_for_tools = profile_id if profile else None
            cached_tools_str = ToolListLoader.load_tools_for_workspace(
                workspace_id=workspace_id,
                profile_id=profile_id_for_tools,
            )
            if cached_tools_str:
                conv_manager.cached_tools_str = cached_tools_str
                logger.info(
                    f"PlaybookRunner: Loaded {len(cached_tools_str)} characters of tools list for workspace {workspace_id}"
                )
            else:
                logger.warning(
                    f"PlaybookRunner: Failed to load tools list for workspace {workspace_id}, playbook may not have access to tools"
                )

        if variant:
            conv_manager.variant = variant
            conv_manager.skip_steps = variant.get("skip_steps", [])
            conv_manager.custom_checklist = variant.get("custom_checklist", [])
            if variant.get("execution_params"):
                if inputs:
                    inputs.update(variant["execution_params"])
                else:
                    inputs = variant["execution_params"]

        runner.active_conversations[execution_id] = conv_manager
        route_context = await load_and_apply_executor_route_context(
            runner,
            conv_manager,
            workspace_id,
        )
        provider = get_llm_provider(runner, profile_id)

        from backend.app.shared.i18n_loader import load_i18n_string

        default_start_message = load_i18n_string(
            "playbook.start_execution",
            locale=conv_manager.locale,
            default="Starting Playbook execution.",
        )
        user_message = None
        if inputs:
            user_message = (
                inputs.get("user_message")
                or inputs.get("message")
                or inputs.get("original_message")
            )
        initial_message = user_message if user_message else default_start_message
        conv_manager.add_user_message(initial_message)

        assistant_response = await run_playbook_chat_completion(
            runner=runner,
            conv_manager=conv_manager,
            profile_id=profile_id,
            provider=provider,
            route_context=route_context,
            purpose="playbook_runner.start",
            workspace_id=workspace_id,
            log_playbook_code=playbook_code,
        )

        try:
            running_event = build_run_state_changed_event(
                profile_id=profile_id,
                project_id=project_id,
                workspace_id=workspace_id,
                execution_id=execution_id,
                previous_state="READY",
                new_state="RUNNING",
                reason="tool_execution_started",
                playbook_code=playbook_code,
                inputs=inputs,
            )
            runner.store.create_event(running_event)
            last_run_state = "RUNNING"
            logger.info(
                f"Emitted RUN_STATE_CHANGED event: READY → RUNNING for execution {execution_id}"
            )
        except Exception as exc:
            logger.warning(f"Failed to emit RUN_STATE_CHANGED event: {exc}")

        context = inputs or {}
        sandbox_id_from_context = context.get("sandbox_id")
        max_iterations = 15 if auto_execute else 5
        assistant_response, used_tools = await run_playbook_tool_loop(
            runner=runner,
            conv_manager=conv_manager,
            assistant_response=assistant_response,
            execution_id=execution_id,
            profile_id=profile_id,
            provider=provider,
            workspace_id=workspace_id,
            sandbox_id=sandbox_id_from_context,
            max_iterations=max_iterations,
            log_tool_loop=True,
            swallow_tool_loop_errors=True,
        )

        structured_output = conv_manager.extract_structured_output(assistant_response)
        is_complete = structured_output is not None

        project_id = inputs.get("project_id") if inputs else None
        playbook_code = playbook.metadata.playbook_code if playbook else None
        step_event, total_steps = runner.step_recorder.record_initial_step(
            execution_id=execution_id,
            profile_id=profile_id,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            conv_manager=conv_manager,
            assistant_response=assistant_response,
            playbook_json=playbook_json,
            playbook=playbook,
            project_id=project_id,
        )

        if is_complete and structured_output and step_event:
            runner.step_recorder.finalize_step_with_output(
                step_event=step_event,
                execution_id=execution_id,
                structured_output=structured_output,
            )

        if is_complete:
            conv_manager.extracted_data = structured_output
            runner.task_manager.update_task_status_to_succeeded(
                execution_id=execution_id,
                structured_output=structured_output,
            )

            try:
                done_event = build_run_state_changed_event(
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    previous_state="RUNNING",
                    new_state="DONE",
                    reason="execution_completed",
                    playbook_code=playbook_code,
                    inputs=inputs,
                )
                runner.store.create_event(done_event)
                logger.info(
                    f"Emitted RUN_STATE_CHANGED event: RUNNING → DONE for execution {execution_id}"
                )
            except Exception as exc:
                logger.warning(f"Failed to emit RUN_STATE_CHANGED event: {exc}")

            runner.cleanup_execution(execution_id)
            logger.info(f"Cleaned up execution {execution_id} from active_conversations")

        try:
            await runner.state_store.save_execution_state(execution_id, conv_manager)
        except Exception as exc:
            logger.warning(f"Failed to save initial execution state: {exc}", exc_info=True)

        sandbox_id = context.get("sandbox_id") if context else None
        if sandbox_id and workspace_id:
            try:
                from backend.app.services.stores.tasks_store import TasksStore

                tasks_store = TasksStore()
                if preserve_sandbox_id_in_execution_context(
                    execution_id=execution_id,
                    sandbox_id=sandbox_id,
                    get_task_by_execution_id_fn=tasks_store.get_task_by_execution_id,
                    update_task_fn=lambda task_id, execution_context: tasks_store.update_task(
                        task_id,
                        execution_context=execution_context,
                    ),
                ):
                    logger.info(
                        f"Preserved sandbox_id={sandbox_id} in execution_context for execution {execution_id}"
                    )
            except Exception as exc:
                logger.warning(
                    f"Failed to preserve sandbox_id in execution_context: {exc}",
                    exc_info=True,
                )

        plan = None
        if playbook_json and playbook_json.steps:
            plan = [step.model_dump() for step in playbook_json.steps]

        result = {
            "execution_id": execution_id,
            "playbook_code": playbook_code,
            "playbook_name": playbook.metadata.name,
            "message": assistant_response,
            "is_complete": is_complete,
            "conversation_history": conv_manager.conversation_history,
            "plan": plan,
        }

        thread_id = inputs.get("thread_id") if inputs else None
        if thread_id:
            try:
                await runner.context_injector.extract_context_updates(
                    execution_id=execution_id,
                    thread_id=thread_id,
                    execution_result=result,
                )
            except Exception as exc:
                logger.warning(
                    f"Failed to extract Story Thread context updates: {exc}",
                    exc_info=True,
                )

        return result

    except Exception as exc:
        logger.error(f"Failed to start playbook execution: {exc}", exc_info=True)
        if workspace_id:
            runner.task_manager.update_task_status_to_failed(execution_id, str(exc))
        if execution_id:
            try:
                failed_event = build_run_state_changed_event(
                    profile_id=profile_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    previous_state=last_run_state,
                    new_state="FAILED",
                    reason="execution_failed",
                    playbook_code=playbook_code,
                    inputs=inputs,
                )
                runner.store.create_event(failed_event)
                logger.info(
                    "Emitted RUN_STATE_CHANGED event: RUNNING → FAILED for execution %s",
                    execution_id,
                )
            except Exception as emit_error:
                logger.warning(
                    "Failed to emit FAILED RUN_STATE_CHANGED event: %s",
                    emit_error,
                )
        raise
