from typing import Any


async def build_root_health_payload(health_checker=None) -> dict[str, Any]:
    """Build the fast root /health payload without external service probes."""
    if health_checker is None:
        from backend.app.services.system_health_checker import SystemHealthChecker

        health_checker = SystemHealthChecker()

    issues = []

    llm_status = await health_checker._check_llm_configuration(
        "default-user",
        issues,
        probe_external=False,
    )
    vector_db_status = await health_checker._check_vector_db(issues)
    backend_status = await health_checker._check_backend_service(issues)

    ocr_status = {
        "status": "skipped",
        "available": None,
        "checked": False,
        "reason": "fast_root_health_probe",
    }

    overall_status = "healthy"
    if any(i.severity == "error" for i in issues):
        overall_status = "unhealthy"
    elif any(i.severity == "warning" for i in issues):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "service": "my-agent-mindscape-backend",
        "version": "1.0.0",
        "components": {
            "backend": backend_status.get("status", "unknown"),
            "llm_configured": llm_status.get("configured", False),
            "llm_available": llm_status.get("available", False),
            "vector_db_connected": vector_db_status.get("connected", False),
            "ocr_service": ocr_status.get("status", "unknown"),
        },
        "llm_configured": llm_status.get("configured", False),
        "llm_available": llm_status.get("available", False),
        "llm_provider": llm_status.get("provider"),
        "vector_db_connected": vector_db_status.get("connected", False),
        "ocr_service": ocr_status,
        "issues": [issue.to_dict() for issue in issues] if issues else [],
    }
