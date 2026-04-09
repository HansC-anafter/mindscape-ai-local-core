import os
from typing import Any


_FAST_REASON = "fast_root_health_probe"


def _first_nonempty(*values: str | None) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _fast_llm_status() -> dict[str, Any]:
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    vertex_project_id = _first_nonempty(
        os.getenv("VERTEX_AI_PROJECT_ID"),
        os.getenv("GOOGLE_CLOUD_PROJECT"),
    )
    vertex_credentials = _first_nonempty(
        os.getenv("VERTEX_AI_SERVICE_ACCOUNT_JSON"),
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
    )

    provider = _first_nonempty(os.getenv("LLM_PROVIDER"), os.getenv("DEFAULT_LLM_PROVIDER"))
    configured = False

    if openai_key:
        provider = "openai"
        configured = True
    elif anthropic_key:
        provider = "anthropic"
        configured = True
    elif vertex_project_id and vertex_credentials:
        provider = "vertex-ai"
        configured = True

    if provider is None:
        provider = "openai"

    return {
        "configured": configured,
        "available": configured,
        "provider": provider,
        "checked": False,
        "reason": _FAST_REASON,
    }


def _fast_vector_db_status() -> dict[str, Any]:
    configured = bool(
        _first_nonempty(
            os.getenv("DATABASE_URL_VECTOR"),
            os.getenv("DATABASE_URL"),
            os.getenv("POSTGRES_VECTOR_HOST"),
            os.getenv("POSTGRES_CORE_HOST"),
            os.getenv("POSTGRES_HOST"),
        )
    )
    return {
        "connected": configured,
        "checked": False,
        "reason": _FAST_REASON,
    }


async def _build_detailed_payload(health_checker) -> dict[str, Any]:
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
        "reason": _FAST_REASON,
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


async def build_root_health_payload(health_checker=None) -> dict[str, Any]:
    """Build the fast root /health payload without blocking probes on DB/provider IO."""
    if health_checker is not None:
        return await _build_detailed_payload(health_checker)

    llm_status = _fast_llm_status()
    vector_db_status = _fast_vector_db_status()
    ocr_status = {
        "status": "skipped",
        "available": None,
        "checked": False,
        "reason": _FAST_REASON,
    }

    return {
        "status": "healthy",
        "service": "my-agent-mindscape-backend",
        "version": "1.0.0",
        "components": {
            "backend": "healthy",
            "llm_configured": llm_status["configured"],
            "llm_available": llm_status["available"],
            "vector_db_connected": vector_db_status["connected"],
            "ocr_service": ocr_status["status"],
        },
        "llm_configured": llm_status["configured"],
        "llm_available": llm_status["available"],
        "llm_provider": llm_status["provider"],
        "vector_db_connected": vector_db_status["connected"],
        "ocr_service": ocr_status,
        "issues": [],
    }
