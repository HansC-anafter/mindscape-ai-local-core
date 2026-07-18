"""Target-scoped PostgreSQL signal observer preflight."""

from .preflight import ObserverPreflightConfig, collect_observer_preflight
from .permit_binding import (
    build_ownership_grant,
    build_ownership_request,
    receipt_bound_incident_id,
)

__all__ = [
    "ObserverPreflightConfig",
    "build_ownership_grant",
    "build_ownership_request",
    "collect_observer_preflight",
    "receipt_bound_incident_id",
]
