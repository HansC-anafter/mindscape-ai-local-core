"""Private execution intent resolver seams."""

from backend.app.services.execution_intent_resolver_core.control_plane import (
    detect_runtime_block_reason,
    inspect_cloud_connector_connected_state,
    normalize_control_plane_site_key,
    probe_control_plane_runtime_availability,
    resolve_execution_control_api_base,
)
from backend.app.services.execution_intent_resolver_core.generic_snapshot import (
    GenericFrozenSnapshotResolverMixin,
)
from backend.app.services.execution_intent_resolver_core.ig_reference import (
    IGReferenceIntentResolverMixin,
    extract_ig_reference_execution_intent,
    resolve_ig_reference_execution_intent,
)
from backend.app.services.execution_intent_resolver_core.types import (
    ExecutionIntentResolution,
)
from backend.app.services.execution_intent_resolver_core.workload import (
    WorkloadIntentMixin,
    extract_route_metadata,
    extract_workload_execution_intent_model,
    has_prebuilt_remote_routes,
    normalize_optional_string,
    should_park_on_control_plane_unavailable,
    should_use_render_control_plane_preflight,
)

__all__ = [
    "ExecutionIntentResolution",
    "GenericFrozenSnapshotResolverMixin",
    "IGReferenceIntentResolverMixin",
    "WorkloadIntentMixin",
    "detect_runtime_block_reason",
    "extract_ig_reference_execution_intent",
    "extract_route_metadata",
    "extract_workload_execution_intent_model",
    "has_prebuilt_remote_routes",
    "inspect_cloud_connector_connected_state",
    "normalize_control_plane_site_key",
    "normalize_optional_string",
    "probe_control_plane_runtime_availability",
    "resolve_execution_control_api_base",
    "resolve_ig_reference_execution_intent",
    "should_park_on_control_plane_unavailable",
    "should_use_render_control_plane_preflight",
]
