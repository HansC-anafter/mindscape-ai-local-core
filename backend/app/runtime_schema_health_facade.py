"""Public facade seam for additive runtime schema diagnostics."""

from backend.app.services.runtime_schema_health import RuntimeSchemaHealthFacade

_FACADE = RuntimeSchemaHealthFacade()


def get_runtime_schema_health_facade() -> RuntimeSchemaHealthFacade:
    return _FACADE


__all__ = ["RuntimeSchemaHealthFacade", "get_runtime_schema_health_facade"]
