"""Target-scoped PostgreSQL signal observer preflight."""

from .preflight import ObserverPreflightConfig, collect_observer_preflight
from .permit_binding import (
    build_ownership_grant,
    build_ownership_request,
    materialize_ownership_grant,
    receipt_bound_incident_id,
)

__all__ = [
    "ObserverPreflightConfig",
    "build_ownership_grant",
    "build_ownership_request",
    "collect_observer_preflight",
    "materialize_ownership_grant",
    "receipt_bound_incident_id",
]
