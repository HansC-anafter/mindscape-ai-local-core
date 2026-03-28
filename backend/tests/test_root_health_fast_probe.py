import pytest

from backend.app.app_bootstrap.root_health import build_root_health_payload


class _FakeIssue:
    def __init__(self, severity: str, message: str = "test") -> None:
        self.severity = severity
        self.message = message

    def to_dict(self):
        return {"severity": self.severity, "message": self.message}


class _FakeHealthChecker:
    def __init__(self) -> None:
        self.llm_probe_external = None
        self.ocr_called = False

    async def _check_llm_configuration(self, profile_id, issues, probe_external=True):
        self.llm_probe_external = probe_external
        return {
            "configured": True,
            "provider": "openai",
            "available": True,
        }

    async def _check_vector_db(self, issues):
        return {"connected": True}

    async def _check_backend_service(self, issues):
        return {"status": "healthy", "available": True}

    async def _check_ocr_service(self, issues):
        self.ocr_called = True
        return {"status": "healthy", "available": True}


@pytest.mark.asyncio
async def test_root_health_skips_expensive_ocr_probe():
    checker = _FakeHealthChecker()

    payload = await build_root_health_payload(health_checker=checker)

    assert checker.llm_probe_external is False
    assert checker.ocr_called is False
    assert payload["status"] == "healthy"
    assert payload["components"]["ocr_service"] == "skipped"
    assert payload["ocr_service"]["checked"] is False
    assert payload["ocr_service"]["reason"] == "fast_root_health_probe"


@pytest.mark.asyncio
async def test_root_health_degrades_when_checker_reports_warning():
    class _WarningChecker(_FakeHealthChecker):
        async def _check_vector_db(self, issues):
            issues.append(_FakeIssue("warning"))
            return {"connected": False}

    payload = await build_root_health_payload(health_checker=_WarningChecker())

    assert payload["status"] == "degraded"
    assert payload["vector_db_connected"] is False
    assert payload["issues"] == [{"severity": "warning", "message": "test"}]
