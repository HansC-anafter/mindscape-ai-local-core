"""Public facade for pack-owned typed task identity projections."""

from backend.app.services.task_projection_adapter_core.dispatcher import (
    build_task_display_inputs,
    load_task_display_input_overlays,
    project_task_identity,
)
from backend.app.services.task_projection_adapter_core.models import (
    ALLOWED_PROJECTION_REASONS,
    TaskProjectionAdapterDefinition,
)
from backend.app.services.task_projection_adapter_core.registry import (
    register_definition,
    register_manifest,
    reset_registry_for_tests,
    resolve_definition,
    unregister_definition,
)

__all__ = [
    "ALLOWED_PROJECTION_REASONS",
    "TaskProjectionAdapterDefinition",
    "build_task_display_inputs",
    "load_task_display_input_overlays",
    "project_task_identity",
    "register_definition",
    "register_manifest",
    "reset_registry_for_tests",
    "resolve_definition",
    "unregister_definition",
]
