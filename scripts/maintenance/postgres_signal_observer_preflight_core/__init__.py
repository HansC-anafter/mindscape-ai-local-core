"""Target-scoped PostgreSQL signal observer preflight."""

from .preflight import ObserverPreflightConfig, collect_observer_preflight

__all__ = ["ObserverPreflightConfig", "collect_observer_preflight"]
