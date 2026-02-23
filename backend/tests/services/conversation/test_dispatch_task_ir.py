"""
Tests for dispatch_task_ir in pipeline_meeting.

Verifies dispatch proceeds regardless of store.db_path presence.
Regression test for Phase 2 db_path dead-code guard removal.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest


class TestDispatchTaskIR:
    """Verify dispatch_task_ir works regardless of store.db_path presence.

    dispatch_task_ir() uses inline imports that trigger a broken import
    chain through stores/__init__.py. We inject fake modules via
    sys.modules to isolate the function under test.
    """

    @pytest.mark.asyncio
    async def test_dispatch_proceeds_without_db_path(self):
        """Store without db_path attribute should not block dispatch."""
        fake_phase = MagicMock()
        fake_phase.preferred_engine = "playbook:generic"

        fake_task_ir = MagicMock()
        fake_task_ir.task_id = "task-dispatch-001"
        fake_task_ir.get_next_executable_phases.return_value = [fake_phase]
        fake_task_ir.lower_to_actuation_plan.return_value = None

        # Store with NO db_path attribute
        store_no_dbpath = MagicMock(spec=[])

        mock_ir_store = MagicMock()
        mock_ir_store.replace_task_ir.return_value = True
        mock_ir_store_cls = MagicMock(return_value=mock_ir_store)

        mock_handler = MagicMock()

        async def _fake_initiate(*a, **kw):
            return {"success": True}

        mock_handler.initiate_task_execution = _fake_initiate
        mock_handler_cls = MagicMock(return_value=mock_handler)

        mock_registry_cls = MagicMock()

        # Inject fake modules for inline imports
        mod_pg_ir = types.ModuleType(
            "backend.app.services.stores.postgres.task_ir_store"
        )
        mod_pg_ir.PostgresTaskIRStore = mock_ir_store_cls

        mod_handler = types.ModuleType("backend.app.services.handoff_handler")
        mod_handler.HandoffHandler = mock_handler_cls

        mod_registry = types.ModuleType("backend.app.services.artifact_registry")
        mod_registry.ArtifactRegistry = mock_registry_cls

        target_modules = {
            "backend.app.services.stores.postgres.task_ir_store": mod_pg_ir,
            "backend.app.services.handoff_handler": mod_handler,
            "backend.app.services.artifact_registry": mod_registry,
        }

        saved = {k: sys.modules.get(k) for k in target_modules}
        sys.modules.update(target_modules)
        try:
            from backend.app.services.conversation.pipeline_meeting import (
                dispatch_task_ir,
            )

            result = await dispatch_task_ir(
                task_ir=fake_task_ir,
                store=store_no_dbpath,
            )
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v

        assert result is not None
        assert result["success"] is True

        # Call contract: handler constructed and dispatch called
        mock_handler_cls.assert_called_once()
        mock_ir_store.replace_task_ir.assert_called_once_with(fake_task_ir)
        fake_task_ir.lower_to_actuation_plan.assert_called_once()
