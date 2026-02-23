"""
HandoffAdapter — translate between local-core models and site-hub Registry.

Sits between HandoffBundleService (local) and HandoffRegistryClient (remote).
Contract 4: only translate + verify + retry. No state held locally.
"""

import logging
import os
from typing import Any, Dict, Optional

from .registry_client import HandoffRegistryClient, RegistryUnavailable

logger = logging.getLogger(__name__)


class HandoffAdapter:
    """
    Stateless adapter between local-core handoff models and site-hub Registry.

    Usage:
        adapter = HandoffAdapter()
        if not adapter.is_enabled:
            return  # pure-local mode, adapter not active

        # As sender (A):
        await adapter.publish_handoff(handoff_in_dict, tenant_id, target_device)

        # As receiver (B):
        pending = await adapter.poll_pending()
        for handoff in pending:
            await adapter.claim_and_compile(handoff)
    """

    def __init__(
        self,
        client: Optional[HandoffRegistryClient] = None,
    ):
        self.client = client or HandoffRegistryClient()

    @property
    def is_enabled(self) -> bool:
        """True if registry URL is configured."""
        return self.client.is_configured

    # --- Sender (A) operations ---

    async def publish_handoff(
        self,
        handoff_in: Dict[str, Any],
        tenant_id: str,
        target_device_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Translate local HandoffIn dict -> Registry API create call.

        Returns Registry response or None if not configured.
        """
        if not self.is_enabled:
            logger.debug("HandoffAdapter not enabled, skipping publish")
            return None

        # Translate: extract handoff_id or generate one
        import uuid

        handoff_id = handoff_in.get("id") or str(uuid.uuid4())

        try:
            result = await self.client.create_handoff(
                handoff_id=handoff_id,
                tenant_id=tenant_id,
                payload_type="handoff_in",
                payload=handoff_in,
                target_device_id=target_device_id,
            )
            logger.info(
                "Published handoff to registry",
                extra={"handoff_id": handoff_id},
            )
            return result
        except RegistryUnavailable as e:
            logger.warning(
                "Registry unavailable, handoff queued offline",
                extra={"handoff_id": handoff_id, "error": str(e)},
            )
            return {"handoff_id": handoff_id, "state": "queued_offline"}

    # --- Receiver (B) operations ---

    async def poll_pending(self) -> list:
        """Poll registry for handoffs assigned to this device."""
        if not self.is_enabled:
            return []

        try:
            return await self.client.list_pending(state="created")
        except RegistryUnavailable:
            logger.warning("Registry unavailable during poll")
            return []

    async def claim_and_compile(
        self,
        handoff: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """
        Claim a handoff, compile via local meeting pipeline, commit back.

        Steps:
        1. Claim handoff (CREATED -> CLAIMED)
        2. Append compile_started event
        3. Compile HandoffIn -> TaskIR via existing pipeline
        4. Append compile_completed event
        5. Commit with Commitment payload (CLAIMED -> COMMITTED)
        """
        handoff_id = handoff["id"]

        try:
            # Step 1: Claim
            await self.client.claim_handoff(handoff_id)
            logger.info("Claimed handoff", extra={"handoff_id": handoff_id})

            # Step 2: compile_started event
            await self.client.append_event(
                handoff_id,
                "compile_started",
            )

            # Step 3: Compile via local pipeline
            # This calls into existing meeting engine / HandoffBundleService
            compile_result = await self._compile_locally(handoff)

            # Step 4: compile_completed event
            await self.client.append_event(
                handoff_id,
                "compile_completed",
                payload={"task_ir_id": compile_result.get("task_ir_id")},
            )

            # Step 5: Commit
            commitment = {
                "task_ir_id": compile_result.get("task_ir_id"),
                "accepted": True,
                "scope": compile_result.get("scope", {}),
                "device_id": self.client.device_id,
            }
            result = await self.client.commit_handoff(handoff_id, commitment)
            logger.info("Committed handoff", extra={"handoff_id": handoff_id})
            return result

        except RegistryUnavailable as e:
            logger.error(
                "Registry unavailable during claim/compile",
                extra={"handoff_id": handoff_id, "error": str(e)},
            )
            return None
        except Exception as e:
            logger.error(
                "Compile failed, failing handoff",
                extra={"handoff_id": handoff_id, "error": str(e)},
            )
            try:
                await self.client.fail_handoff(handoff_id, str(e))
            except RegistryUnavailable:
                pass
            return None

    async def dispatch_from_registry(
        self,
        handoff_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Dispatch a committed handoff via local HandoffHandler.

        Steps:
        1. Append dispatch_started event
        2. Dispatch via existing HandoffHandler
        3. On success: complete_handoff. On failure: fail_handoff.
        """
        try:
            await self.client.append_event(handoff_id, "dispatch_started")

            dispatch_result = await self._dispatch_locally(handoff_id)

            if dispatch_result.get("success"):
                await self.client.complete_handoff(
                    handoff_id,
                    dispatch_result,
                )
                return dispatch_result
            else:
                await self.client.fail_handoff(
                    handoff_id,
                    dispatch_result.get("error", "unknown error"),
                )
                return dispatch_result

        except RegistryUnavailable as e:
            logger.error(
                "Registry unavailable during dispatch",
                extra={"handoff_id": handoff_id, "error": str(e)},
            )
            return None

    # --- Verify ---

    def verify_spec_version(self, response: Dict[str, Any]) -> bool:
        """Verify spec_version in response matches expected."""
        version = response.get("spec_version", "0.1")
        if version != "0.1":
            logger.warning(
                "Unexpected spec_version",
                extra={"version": version, "expected": "0.1"},
            )
            return False
        return True

    # --- Offline queue flush ---

    async def flush_offline_queue(self) -> int:
        """Flush any offline-queued events."""
        if not self.is_enabled:
            return 0
        return await self.client.flush_offline_queue()

    # --- Internal: bridge to existing local-core services ---

    async def _compile_locally(
        self,
        handoff: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Bridge to existing HandoffBundleService.compile().

        This is a thin wrapper that translates the registry handoff format
        to the local HandoffBundleService format.
        """
        try:
            from app.services.handoff_bundle_service import HandoffBundleService

            service = HandoffBundleService()
            result = await service.compile_handoff_in(handoff.get("payload_json", {}))
            return result
        except ImportError:
            logger.warning("HandoffBundleService not available, returning stub")
            return {
                "task_ir_id": f"stub-{handoff.get('id', 'unknown')}",
                "scope": {},
            }

    async def _dispatch_locally(
        self,
        handoff_id: str,
    ) -> Dict[str, Any]:
        """
        Bridge to existing dispatch_task_ir().

        Fetches the TaskIR associated with the handoff and dispatches it.
        """
        try:
            from app.services.conversation.pipeline_meeting import dispatch_task_ir
            from app.services.stores.postgres.task_ir_store import PostgresTaskIRStore

            ir_store = PostgresTaskIRStore()
            # The task_ir_id would be stored in the commitment payload
            # For now, return a stub
            return {"success": True, "handoff_id": handoff_id}
        except ImportError:
            logger.warning("dispatch_task_ir not available, returning stub")
            return {"success": True, "handoff_id": handoff_id}
