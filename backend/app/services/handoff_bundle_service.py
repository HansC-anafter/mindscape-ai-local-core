"""
Handoff Bundle Service.

Stateless service for packaging, verifying, and intaking signed
handoff bundles. Bundles are ephemeral transport containers -- the
underlying HandoffIn / Commitment / TaskIR payloads are persisted
by their respective stores.

intake_and_compile() is the primary intake path: it verifies the
bundle, extracts the HandoffIn, and drives it through
MeetingEngine.run() to produce a compiled TaskIR.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from backend.app.models.handoff import Commitment, HandoffIn
from backend.app.models.signed_bundle import SignedHandoffBundle

logger = logging.getLogger(__name__)

HANDOFF_BUNDLE_SECRET_ENV = "HANDOFF_BUNDLE_SECRET"


def _get_secret_key(override: Optional[str] = None) -> str:
    """Resolve bundle signing secret.

    Args:
        override: Explicit key; falls back to env var.

    Returns:
        Secret key string.

    Raises:
        ValueError: If no secret key is available.
    """
    key = override or os.getenv(HANDOFF_BUNDLE_SECRET_ENV)
    if not key:
        raise ValueError(
            f"Handoff bundle secret not configured. "
            f"Set {HANDOFF_BUNDLE_SECRET_ENV} or pass secret_key explicitly."
        )
    return key


def _enum_value(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value)
    return str(value or "")


def _looks_like_orphan_compile_session(
    session: Any,
    existing_compile_job: Any,
) -> bool:
    """Return True when a compile session should not be reused.

    Two concrete shapes are treated as orphaned:
    1. Legacy shape: session exists but no compile_job row was ever created.
    2. Busy shape: a previous compile request already owns this session and its
       compile job is still ``accepted``/``running``. New compile intake must
       start a fresh session instead of multiplexing onto an in-flight one.
    3. Restart-stuck shape: session already converged, compile job is still
       marked running/accepted, but pipeline_stage has remained at
       ``generating`` past a conservative TTL. This means the live worker that
       was awaiting the post-convergence runtime result likely died/restarted,
       so reusing the session only strands future compiles behind stale state.
    """
    if session is None:
        return False

    if existing_compile_job is None:
        return (
            int(getattr(session, "round_count", 0) or 0) == 0
            and not list(getattr(session, "action_items", []) or [])
        )

    compile_status = _enum_value(getattr(existing_compile_job, "status", None)).lower()
    if compile_status not in {"accepted", "running"}:
        return False

    # Never multiplex a new compile request onto an already-running compile
    # session. Retries should replace the old session, not stack more compile
    # jobs onto the same in-flight meeting.
    return True


def _reuse_terminal_compile_result(
    session: Any,
    existing_compile_job: Any,
    *,
    incoming_handoff_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Return an idempotent compile result for same-handoff re-entry.

    A fresh active session can briefly outlive the compile job that created it
    while downstream dispatch/writer lanes finish landing. If the same handoff
    is replayed during that window, do not create a second compile job on the
    same session; return the terminal compile result that already owns it.
    """
    if session is None or existing_compile_job is None:
        return None

    existing_handoff_id = getattr(existing_compile_job, "handoff_id", None)
    if incoming_handoff_id and existing_handoff_id != incoming_handoff_id:
        return None

    compile_status = _enum_value(getattr(existing_compile_job, "status", None)).lower()
    if compile_status != "succeeded":
        return None

    result = getattr(existing_compile_job, "result", None) or {}
    if not isinstance(result, dict):
        result = {}

    reused_result = dict(result)
    reused_result.setdefault("status", "compiled")
    reused_result["compile_job_id"] = existing_compile_job.id
    reused_result["job_id"] = existing_compile_job.id
    reused_result["session_id"] = (
        reused_result.get("session_id")
        or getattr(session, "id", None)
        or getattr(existing_compile_job, "session_id", None)
    )
    reused_result.setdefault("persisted", False)
    reused_result["reused_compile_job"] = True
    return reused_result


def _build_compile_job_recovery_request(
    *,
    handoff_in: HandoffIn,
    workspace_id: str,
    project_id: str,
    thread_id: str,
    profile_id: str,
    model_name: Optional[str],
    source_device_id: Optional[str],
) -> Dict[str, Any]:
    return {
        "handoff_payload": json.loads(handoff_in.model_dump_json()),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "thread_id": thread_id,
        "profile_id": profile_id,
        "model_name": model_name,
        "source_device_id": source_device_id,
    }


class HandoffBundleService:
    """Bundle lifecycle: package, verify, intake."""

    # -- Packaging ----------------------------------------------------------

    @staticmethod
    def package_handoff(
        handoff_in: HandoffIn,
        source_device_id: str,
        secret_key: Optional[str] = None,
        target_device_id: Optional[str] = None,
    ) -> SignedHandoffBundle:
        """Package a HandoffIn into a signed, portable bundle.

        Args:
            handoff_in: The handoff request to package.
            source_device_id: Originating device identifier.
            secret_key: Signing secret (falls back to env var).
            target_device_id: Optional intended recipient.

        Returns:
            SignedHandoffBundle ready for transport.
        """
        key = _get_secret_key(secret_key)
        payload = handoff_in.model_dump(mode="json")
        bundle = SignedHandoffBundle.create(
            payload_type="handoff_in",
            payload=payload,
            source_device_id=source_device_id,
            secret_key=key,
            target_device_id=target_device_id,
        )
        logger.info(
            "Packaged handoff_in bundle for handoff %s",
            handoff_in.handoff_id,
        )
        return bundle

    @staticmethod
    def package_commitment(
        commitment: Commitment,
        source_device_id: str,
        secret_key: Optional[str] = None,
        target_device_id: Optional[str] = None,
    ) -> SignedHandoffBundle:
        """Package a Commitment into a signed bundle for return delivery.

        Args:
            commitment: The commitment response to package.
            source_device_id: Originating device identifier.
            secret_key: Signing secret (falls back to env var).
            target_device_id: Optional intended recipient.

        Returns:
            SignedHandoffBundle ready for transport.
        """
        key = _get_secret_key(secret_key)
        payload = commitment.model_dump(mode="json")
        bundle = SignedHandoffBundle.create(
            payload_type="commitment",
            payload=payload,
            source_device_id=source_device_id,
            secret_key=key,
            target_device_id=target_device_id,
        )
        logger.info(
            "Packaged commitment bundle for handoff %s",
            commitment.handoff_id,
        )
        return bundle

    # -- Verification -------------------------------------------------------

    @staticmethod
    def verify_bundle(
        bundle: SignedHandoffBundle,
        secret_key: Optional[str] = None,
    ) -> bool:
        """Verify bundle integrity and authenticity.

        Args:
            bundle: Bundle to verify.
            secret_key: Signing secret (falls back to env var).

        Returns:
            True if signature and content hash are valid.
        """
        key = _get_secret_key(secret_key)
        return bundle.verify(key)

    # -- Intake -------------------------------------------------------------

    @staticmethod
    def extract_payload(
        bundle: SignedHandoffBundle,
        secret_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify and extract typed payload from a bundle.

        Args:
            bundle: Incoming bundle to process.
            secret_key: Signing secret (falls back to env var).

        Returns:
            Dict with 'payload_type' and typed payload object.

        Raises:
            ValueError: If signature verification fails or payload_type unknown.
        """
        key = _get_secret_key(secret_key)
        if not bundle.verify(key):
            raise ValueError("Bundle signature verification failed")

        payload_type = bundle.payload_type
        payload_data = bundle.payload

        if payload_type == "handoff_in":
            typed = HandoffIn(**payload_data)
        elif payload_type == "commitment":
            typed = Commitment(**payload_data)
        elif payload_type == "result":
            typed = payload_data  # result is freeform for now
        else:
            raise ValueError(f"Unknown payload_type: {payload_type}")

        logger.info(
            "Extracted %s payload from bundle (source=%s)",
            payload_type,
            bundle.source_device_id,
        )
        return {"payload_type": payload_type, "payload": typed}

    # -- Full intake pipeline -----------------------------------------------

    @staticmethod
    async def intake_and_compile(
        bundle: SignedHandoffBundle,
        workspace: Any,
        runtime_profile: Any,
        profile_id: str,
        thread_id: str,
        project_id: str,
        secret_key: Optional[str] = None,
        model_name: Optional[str] = None,
        route_decision: Any = None,
    ) -> Dict[str, Any]:
        """Verify bundle, extract HandoffIn, and compile via MeetingEngine.

        This is the primary intake entry point. It drives the extracted
        HandoffIn through MeetingEngine.run() which produces a compiled
        TaskIR, persists it via PostgresTaskIRStore.

        Args:
            bundle: Incoming signed bundle (must contain handoff_in payload).
            workspace: Workspace ORM instance (provides session init context).
            runtime_profile: Active runtime profile for the workspace.
            profile_id: User profile ID.
            thread_id: Conversation thread ID.
            project_id: Project ID for meeting session scope.
            secret_key: Signing secret (falls back to env var).
            model_name: LLM model override.
            route_decision: RouteDecision from IngressRouter (ADR-R1).

        Returns:
            Dict with task_ir_id, session_id, persisted status.

        Raises:
            ValueError: If signature fails or payload_type is not handoff_in.
        """
        key = _get_secret_key(secret_key)
        if not bundle.verify(key):
            raise ValueError("Bundle signature verification failed")

        if bundle.payload_type != "handoff_in":
            raise ValueError(
                f"intake_and_compile requires handoff_in bundle, "
                f"got {bundle.payload_type}"
            )

        handoff_in = HandoffIn(**bundle.payload)

        return await HandoffBundleService.compile_handoff_in(
            handoff_in=handoff_in,
            workspace=workspace,
            runtime_profile=runtime_profile,
            profile_id=profile_id,
            thread_id=thread_id,
            project_id=project_id,
            model_name=model_name,
            source_device_id=bundle.source_device_id,
            route_decision=route_decision,
        )

    @staticmethod
    async def compile_handoff_in(
        handoff_in: HandoffIn,
        workspace: Any,
        runtime_profile: Any,
        profile_id: str,
        thread_id: str,
        project_id: str,
        model_name: Optional[str] = None,
        source_device_id: Optional[str] = None,
        route_decision: Any = None,
    ) -> Dict[str, Any]:
        """Compile a HandoffIn via MeetingEngine (no bundle verification).

        This is the Registry-native compile entry point. It accepts
        a pre-validated HandoffIn object and produces a TaskIR.

        Args:
            handoff_in: Pre-validated HandoffIn payload.
            workspace: Workspace ORM instance.
            runtime_profile: Active runtime profile.
            profile_id: User profile ID.
            thread_id: Conversation thread ID.
            project_id: Project ID for meeting scope.
            model_name: LLM model override.
            source_device_id: Originating device (for intake message).

        Returns:
            Dict with task_ir_id, session_id, persisted status.
        """
        from backend.app.services.orchestration.meeting import MeetingEngine
        from backend.app.services.stores.meeting_session_store import (
            MeetingSessionStore,
            is_active_session_fresh,
        )
        from backend.app.models.meeting_execution_context import (
            MeetingExecutionContext,
        )

        session_store = MeetingSessionStore()
        workspace_id = getattr(workspace, "id", handoff_in.workspace_id)
        executor_runtime = getattr(workspace, "resolved_executor_runtime", None)
        compile_job_id = str(uuid4())
        compile_job_store = None
        compile_job_created = False
        cleanup_compile_job_session_ids = []
        stale_compile_job_cleaned_session_ids = set()
        try:
            listed_sessions = session_store.list_by_workspace(
                workspace_id,
                project_id=project_id,
                limit=100,
                offset=0,
            )
            if not isinstance(listed_sessions, list):
                listed_sessions = list(listed_sessions or [])
            for candidate in listed_sessions:
                if project_id and getattr(candidate, "project_id", None) != project_id:
                    continue
                if thread_id and getattr(candidate, "thread_id", None) != thread_id:
                    continue
                if getattr(candidate, "is_active", False):
                    if is_active_session_fresh(candidate):
                        continue
                    cleanup_compile_job_session_ids.append(candidate.id)
                    continue
                cleanup_compile_job_session_ids.append(candidate.id)
        except Exception as exc:
            logger.warning(
                "[HandoffBundle] Failed to enumerate stale active sessions for workspace=%s project=%s thread=%s: %s",
                workspace_id,
                project_id,
                thread_id,
                exc,
            )

        try:
            from backend.app.models.compile_job import CompileJob, CompileJobStatus
            from backend.app.services.stores.compile_job_store import CompileJobStore

            compile_job_store = CompileJobStore()
        except Exception as exc:
            logger.warning("[HandoffBundle] Compile job store unavailable: %s", exc)

        try:
            session_store.close_stale_active_sessions(
                workspace_id,
                project_id=project_id,
                thread_id=thread_id,
                reason="stale_replaced_by_compile",
            )
        except Exception as exc:
            logger.warning(
                "[HandoffBundle] Failed to close stale active sessions for workspace=%s project=%s thread=%s: %s",
                workspace_id,
                project_id,
                thread_id,
                exc,
            )
        if cleanup_compile_job_session_ids and compile_job_store is not None:
            for stale_session_id in cleanup_compile_job_session_ids:
                try:
                    compile_job_store.mark_incomplete_for_session(
                        stale_session_id,
                        error="compile_session_replaced_by_new_intake",
                        metadata={"abort_reason": "stale_replaced_by_compile"},
                    )
                except Exception as exc:
                    logger.warning(
                        "[HandoffBundle] Failed to fail stale compile jobs for session=%s: %s",
                        stale_session_id,
                        exc,
                    )
                else:
                    stale_compile_job_cleaned_session_ids.add(stale_session_id)
        session = session_store.get_active_session(
            workspace_id,
            project_id,
            thread_id,
        )

        orphan_compile_session = False
        existing_compile_job = None
        if session and compile_job_store is not None:
            try:
                existing_compile_job = compile_job_store.get_latest_for_session(session.id)
                orphan_compile_session = _looks_like_orphan_compile_session(
                    session,
                    existing_compile_job,
                )
            except Exception as exc:
                logger.warning(
                    "[HandoffBundle] Failed to inspect existing compile session %s: %s",
                    session.id,
                    exc,
                )
                existing_compile_job = None

        if session and (orphan_compile_session or not is_active_session_fresh(session)):
            logger.info(
                "[HandoffBundle] Ignoring stale/orphan active session %s for workspace=%s project=%s",
                session.id,
                workspace_id,
                project_id,
            )
            if (
                compile_job_store is not None
                and session.id not in stale_compile_job_cleaned_session_ids
            ):
                try:
                    compile_job_store.mark_incomplete_for_session(
                        session.id,
                        error="compile_session_replaced_by_new_intake",
                        metadata={"abort_reason": "stale_replaced_by_compile"},
                    )
                except Exception as exc:
                    logger.warning(
                        "[HandoffBundle] Failed to fail stale compile jobs for session=%s: %s",
                        session.id,
                        exc,
                    )
            try:
                session_store.end_session(
                    session.id,
                    state_after={"abort_reason": "stale_replaced_by_compile"},
                )
            except Exception as exc:
                logger.warning(
                    "[HandoffBundle] Failed to close stale session %s: %s",
                    session.id,
                    exc,
                )
            session = None
            existing_compile_job = None

        reused_compile_result = _reuse_terminal_compile_result(
            session,
            existing_compile_job,
            incoming_handoff_id=getattr(handoff_in, "handoff_id", None),
        )
        if reused_compile_result is not None:
            logger.info(
                "[HandoffBundle] Reusing terminal compile job %s for active session %s handoff=%s",
                getattr(existing_compile_job, "id", None),
                getattr(session, "id", None),
                getattr(handoff_in, "handoff_id", None),
            )
            return reused_compile_result

        if not session:
            from backend.app.models.meeting_session import MeetingSession

            # Resolve lens_id via EffectiveLensResolver
            lens_id = None
            try:
                from backend.app.services.stores.graph_store import GraphStore
                from backend.app.services.lens.effective_lens_resolver import (
                    EffectiveLensResolver,
                )
                from backend.app.services.lens.session_override_store import (
                    InMemorySessionStore,
                )

                graph_store = GraphStore()
                session_override_store = InMemorySessionStore()
                resolver = EffectiveLensResolver(graph_store, session_override_store)
                effective = resolver.resolve(
                    profile_id=profile_id,
                    workspace_id=workspace_id,
                )
                lens_id = effective.global_preset_id
            except Exception as exc:
                logger.warning("[HandoffBundle] Failed to resolve lens_id: %s", exc)

            session = MeetingSession.new(
                workspace_id=workspace_id,
                project_id=project_id,
                thread_id=thread_id,
                lens_id=lens_id,
                agenda=(
                    [g[:200].strip() for g in (handoff_in.goals or []) if g.strip()][
                        :10
                    ]
                    or [handoff_in.intent_summary[:200].strip()]
                    if hasattr(handoff_in, "intent_summary")
                    and handoff_in.intent_summary
                    else None
                ),
            )
            session_store.create(session)

        if compile_job_store is not None:
            try:
                compile_job_store.create(
                    CompileJob(
                        id=compile_job_id,
                        workspace_id=workspace_id,
                        project_id=project_id,
                        thread_id=thread_id,
                        profile_id=profile_id,
                        session_id=session.id,
                        handoff_id=handoff_in.handoff_id,
                        source_device_id=source_device_id,
                        status=CompileJobStatus.RUNNING,
                        metadata={
                            "workspace_id": workspace_id,
                            "executor_runtime": executor_runtime,
                            "route_kind": getattr(route_decision, "route_kind", None),
                            "recovery_request": _build_compile_job_recovery_request(
                                handoff_in=handoff_in,
                                workspace_id=workspace_id,
                                project_id=project_id,
                                thread_id=thread_id,
                                profile_id=profile_id,
                                model_name=model_name,
                                source_device_id=source_device_id,
                            ),
                        },
                        started_at=datetime.now(timezone.utc),
                    )
                )
                compile_job_created = True
            except Exception as exc:
                logger.warning(
                    "[HandoffBundle] Failed to create compile job %s: %s",
                    compile_job_id,
                    exc,
                )

        from backend.app.services.conversation.pipeline_meeting import (
            build_execution_launcher,
        )
        from backend.app.services.mindscape_store import MindscapeStore

        execution_context = MeetingExecutionContext.assemble(
            workspace=workspace,
            runtime_profile=runtime_profile,
            route_decision=route_decision,
        )
        store = MindscapeStore()
        execution_launcher = build_execution_launcher(store)

        engine = MeetingEngine(
            session=session,
            store=store,
            workspace=workspace,
            runtime_profile=runtime_profile,
            profile_id=profile_id,
            thread_id=thread_id,
            project_id=project_id,
            execution_launcher=execution_launcher,
            model_name=model_name,
            executor_runtime=executor_runtime,
            uploaded_files=None,  # Handoff bundles don't carry uploaded files
            execution_context=execution_context,
        )

        intake_message = (
            f"[Handoff Intake] {handoff_in.intent_summary}\n"
            f"Goals: {', '.join(handoff_in.goals)}\n"
            f"Source: {source_device_id or 'unknown'}"
        )

        try:
            meeting_result = await engine.run(intake_message, handoff_in=handoff_in)
        except Exception as exc:
            if compile_job_store is not None and compile_job_created:
                try:
                    compile_job_store.mark_failed(
                        compile_job_id,
                        str(exc),
                        session_id=session.id,
                        metadata={
                            "workspace_id": workspace_id,
                            "executor_runtime": executor_runtime,
                        },
                    )
                except Exception as mark_exc:
                    logger.warning(
                        "[HandoffBundle] Failed to mark compile job %s failed: %s",
                        compile_job_id,
                        mark_exc,
                    )
            raise

        result = {
            "status": "compiled",
            "compile_job_id": compile_job_id,
            "job_id": compile_job_id,
            "session_id": meeting_result.session_id,
            "decision": meeting_result.decision,
            "action_items_count": len(meeting_result.action_items),
            "task_ir_id": None,
            "persisted": False,
        }

        # Persist compiled TaskIR via PostgresTaskIRStore
        if meeting_result.task_ir:
            result["task_ir_id"] = meeting_result.task_ir.task_id
            try:
                from backend.app.services.stores.postgres.task_ir_store import (
                    PostgresTaskIRStore,
                )

                ir_store = PostgresTaskIRStore()
                ir_store.replace_task_ir(meeting_result.task_ir)
                result["persisted"] = True
                logger.info(
                    "Persisted TaskIR %s from intake",
                    meeting_result.task_ir.task_id,
                )
            except Exception as exc:
                logger.warning(
                    "Failed to persist TaskIR from intake: %s",
                    exc,
                    exc_info=True,
                )

        if compile_job_store is not None and compile_job_created:
            try:
                compile_job_store.mark_succeeded(
                    compile_job_id,
                    session_id=meeting_result.session_id,
                    result=result,
                    metadata={
                        "workspace_id": workspace_id,
                        "executor_runtime": executor_runtime,
                    },
                )
            except Exception as exc:
                logger.warning(
                    "[HandoffBundle] Failed to mark compile job %s succeeded: %s",
                    compile_job_id,
                    exc,
                )

        logger.info(
            "Intake complete: handoff %s -> TaskIR %s (persisted=%s)",
            handoff_in.handoff_id,
            result["task_ir_id"],
            result["persisted"],
        )
        return result
