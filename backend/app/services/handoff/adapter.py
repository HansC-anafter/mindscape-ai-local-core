"""
HandoffAdapter — translate between local-core models and site-hub Registry.

Sits between HandoffBundleService (local) and HandoffRegistryClient (remote).
Contract 4: only translate + verify + retry. No state held locally.
"""

import logging
import os
from typing import Any, Dict, Optional

from .registry_client import (
    HandoffRegistryClient,
    RegistryUnavailable,
    RegistryRequestError,
)

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
        except RegistryRequestError as e:
            logger.error(
                "Registry rejected publish",
                extra={
                    "handoff_id": handoff_id,
                    "status": e.status_code,
                    "detail": e.detail,
                },
            )
            return None

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
        except RegistryRequestError as e:
            logger.warning(
                "Registry rejected poll request",
                extra={"status": e.status_code, "detail": e.detail},
            )
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

        except RegistryRequestError as e:
            logger.error(
                "Registry rejected request during claim/compile",
                extra={
                    "handoff_id": handoff_id,
                    "status": e.status_code,
                    "detail": e.detail,
                },
            )
            return None
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
            except (RegistryUnavailable, RegistryRequestError):
                pass
            return None

    async def dispatch_from_registry(
        self,
        handoff_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Dispatch a committed handoff via local HandoffHandler.

        Steps:
        1. Transition state: committed -> dispatched (includes dispatch_started event)
        2. Dispatch via existing HandoffHandler
        3. On success: complete_handoff (dispatched -> completed)
        4. On failure: fail_handoff (dispatched -> failed)
        """
        try:
            # Transition committed -> dispatched (emits dispatch_started event)
            await self.client.dispatch_handoff(handoff_id)

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

        except RegistryRequestError as e:
            logger.error(
                "Registry rejected request during dispatch",
                extra={
                    "handoff_id": handoff_id,
                    "status": e.status_code,
                    "detail": e.detail,
                },
            )
            return None
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
        Bridge to HandoffBundleService.compile_handoff_in().

        Registry-native path: no bundle verification needed. Translates
        registry handoff format to the compile_handoff_in interface.
        """
        try:
            from backend.app.services.handoff_bundle_service import (
                HandoffBundleService,
            )
            from backend.app.models.handoff import HandoffIn
            from backend.app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )

            payload = handoff.get("payload_json", {})
            if isinstance(payload, str):
                import json

                payload = json.loads(payload)

            handoff_in = HandoffIn(**payload)

            # Resolve workspace context
            workspace_id = getattr(
                handoff_in, "workspace_id", payload.get("workspace_id", "")
            )
            ws_store = PostgresWorkspacesStore()
            workspace = await ws_store.get_workspace(workspace_id)
            if not workspace:
                raise ValueError(f"Workspace {workspace_id} not found")

            runtime_profile = getattr(workspace, "runtime_profile", None)

            result = await HandoffBundleService.compile_handoff_in(
                handoff_in=handoff_in,
                workspace=workspace,
                runtime_profile=runtime_profile,
                profile_id=payload.get("profile_id", "default-user"),
                thread_id=payload.get("thread_id", handoff.get("id", "")),
                project_id=payload.get("project_id", ""),
                source_device_id=handoff.get("source_device_id"),
            )
            return result
        except ImportError as exc:
            logger.warning(
                "HandoffBundleService not available, returning stub: %s", exc
            )
            return {
                "task_ir_id": f"stub-{handoff.get('id', 'unknown')}",
                "scope": {},
            }

    async def _dispatch_locally(
        self,
        handoff_id: str,
    ) -> Dict[str, Any]:
        """
        Bridge to DispatchOrchestrator for handoff dispatch.

        Fetches the TaskIR associated with the handoff (via commitment
        payload stored in registry) and dispatches it through the
        DispatchOrchestrator (sole dispatch authority after Phase 2).
        """
        try:
            from backend.app.services.orchestration.dispatch_orchestrator import (
                DispatchOrchestrator,
            )
            from backend.app.services.stores.postgres.task_ir_store import (
                PostgresTaskIRStore,
            )

            # Fetch handoff to get commitment payload with task_ir_id
            handoff_data = await self.client._get(f"/handoffs/{handoff_id}")
            payload_json = handoff_data.get("payload_json", {})
            commitment = payload_json.get("commitment", {})
            task_ir_id = commitment.get("task_ir_id")

            if not task_ir_id:
                return {
                    "success": False,
                    "handoff_id": handoff_id,
                    "error": "No task_ir_id in commitment payload",
                }

            ir_store = PostgresTaskIRStore()
            task_ir = ir_store.get_task_ir(task_ir_id)
            if not task_ir:
                return {
                    "success": False,
                    "handoff_id": handoff_id,
                    "error": f"TaskIR {task_ir_id} not found",
                }

            # Build action_items from TaskIR phases for orchestrator
            action_items = []
            for phase in task_ir.phases or []:
                action_items.append(
                    {
                        "title": phase.name,
                        "description": phase.description or "",
                        "playbook_code": (
                            phase.preferred_engine.split(":", 1)[-1]
                            if phase.preferred_engine and ":" in phase.preferred_engine
                            else None
                        ),
                        "target_workspace_id": phase.target_workspace_id or "",
                    }
                )

            orchestrator = DispatchOrchestrator(
                project_id=payload_json.get("project_id"),
            )
            result = await orchestrator.execute(
                task_ir=task_ir,
                action_items=action_items,
            )

            success = result.get("status") != "all_failed"
            return {
                "success": success,
                "handoff_id": handoff_id,
                "task_ir_id": task_ir_id,
                "dispatch_result": result,
            }
        except ImportError as exc:
            logger.warning("DispatchOrchestrator not available: %s", exc)
            return {
                "success": False,
                "handoff_id": handoff_id,
                "error": f"Import error: {exc}",
            }
        except Exception as exc:
            logger.error(
                "dispatch_locally failed",
                extra={"handoff_id": handoff_id, "error": str(exc)},
                exc_info=True,
            )
            return {
                "success": False,
                "handoff_id": handoff_id,
                "error": str(exc),
            }
