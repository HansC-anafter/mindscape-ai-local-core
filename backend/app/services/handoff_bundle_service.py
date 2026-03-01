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

import logging
import os
from typing import Any, Dict, List, Optional

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
        )

        session_store = MeetingSessionStore()
        workspace_id = getattr(workspace, "id", handoff_in.workspace_id)
        session = session_store.get_active_session(workspace_id, project_id)
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
            )
            session_store.create(session)

        from backend.app.services.mindscape_store import MindscapeStore

        engine = MeetingEngine(
            session=session,
            store=MindscapeStore(),
            workspace=workspace,
            runtime_profile=runtime_profile,
            profile_id=profile_id,
            thread_id=thread_id,
            project_id=project_id,
            model_name=model_name,
            uploaded_files=None,  # Handoff bundles don't carry uploaded files
        )

        intake_message = (
            f"[Handoff Intake] {handoff_in.intent_summary}\n"
            f"Goals: {', '.join(handoff_in.goals)}\n"
            f"Source: {source_device_id or 'unknown'}"
        )

        meeting_result = await engine.run(intake_message, handoff_in=handoff_in)

        result = {
            "status": "compiled",
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

        logger.info(
            "Intake complete: handoff %s -> TaskIR %s (persisted=%s)",
            handoff_in.handoff_id,
            result["task_ir_id"],
            result["persisted"],
        )
        return result
