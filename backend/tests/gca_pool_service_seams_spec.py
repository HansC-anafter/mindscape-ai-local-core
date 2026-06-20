from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from backend.app.services.gca_pool_service import GCAPoolService
from backend.app.services.gca_pool_service_core import token_refresh


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = [
    REPO_ROOT / "backend/app/services/gca_pool_service.py",
    REPO_ROOT / "backend/app/services/gca_pool_service_core/__init__.py",
    REPO_ROOT / "backend/app/services/gca_pool_service_core/account_state.py",
    REPO_ROOT / "backend/app/services/gca_pool_service_core/preview.py",
    REPO_ROOT / "backend/app/services/gca_pool_service_core/token_refresh.py",
]


def test_facade_serializes_runtime_pool_dict_without_db_session():
    cooldown_until = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    last_used_at = datetime(2026, 6, 21, 12, 5, tzinfo=timezone.utc)
    runtime = SimpleNamespace(
        id="gca-runtime",
        auth_status="connected",
        auth_config={"identity": "person@example.test"},
        pool_enabled=True,
        pool_priority=7,
        cooldown_until=cooldown_until,
        last_used_at=last_used_at,
        last_error_code="429",
    )

    result = GCAPoolService._to_pool_dict(runtime)

    assert result == {
        "id": "gca-runtime",
        "email": "person@example.test",
        "auth_status": "connected",
        "pool_enabled": True,
        "pool_priority": 7,
        "cooldown_until": cooldown_until.isoformat(),
        "last_used_at": last_used_at.isoformat(),
        "last_error_code": "429",
    }


def test_facade_preview_preserves_preferred_and_substitution_policy():
    now = datetime.now(timezone.utc)
    preferred_cooling = {
        "id": "gca-preferred",
        "auth_status": "connected",
        "pool_enabled": True,
        "pool_priority": 0,
        "cooldown_until": (now + timedelta(minutes=10)).isoformat(),
        "last_used_at": None,
    }
    available_later_priority = {
        "id": "gca-later-priority",
        "auth_status": "connected",
        "pool_enabled": True,
        "pool_priority": 5,
        "cooldown_until": None,
        "last_used_at": None,
    }
    available_first_priority = {
        "id": "gca-first-priority",
        "auth_status": "expired",
        "pool_enabled": True,
        "pool_priority": 1,
        "cooldown_until": None,
        "last_used_at": (now - timedelta(minutes=2)).isoformat(),
    }
    service = GCAPoolService()
    service.list_pool = lambda: [
        available_later_priority,
        preferred_cooling,
        available_first_priority,
    ]

    missing_preference = service.preview_active_runtime()
    assert missing_preference["status"] == "unavailable"
    assert missing_preference["selected_runtime_id"] is None
    assert missing_preference["available_count"] == 2
    assert missing_preference["cooling_count"] == 1

    pinned_cooling = service.preview_active_runtime(
        preferred_runtime_id="gca-preferred",
        allow_runtime_substitution=False,
    )
    assert pinned_cooling["status"] == "cooldown"
    assert pinned_cooling["selected_runtime_id"] is None
    assert pinned_cooling["account"]["id"] == "gca-preferred"

    substituted = service.preview_active_runtime(
        preferred_runtime_id="gca-preferred",
        allow_runtime_substitution=True,
    )
    assert substituted["status"] == "available"
    assert substituted["selected_runtime_id"] == "gca-first-priority"
    assert substituted["preferred_runtime_id"] == "gca-preferred"
    assert substituted["preferred_status"] == "cooldown"


def test_token_refresh_helper_uses_single_commit_callback(monkeypatch):
    import backend.app.routes.core.gca_constants as gca_constants

    monkeypatch.setattr(gca_constants, "get_gca_client_id", lambda: "client-id")
    monkeypatch.setattr(gca_constants, "get_gca_client_secret", lambda: "client-secret")

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return json.dumps(
                {"access_token": "new-access-token", "expires_in": 1800}
            ).encode()

    captured_request = {}

    def fake_urlopen(req, timeout):
        captured_request["url"] = req.full_url
        captured_request["timeout"] = timeout
        captured_request["method"] = req.get_method()
        captured_request["content_type"] = req.get_header("Content-type")
        return FakeResponse()

    monkeypatch.setattr(token_refresh.urllib.request, "urlopen", fake_urlopen)

    runtime = SimpleNamespace(
        id="gca-runtime",
        auth_config={},
        auth_status="expired",
    )
    db = object()
    token_data = {
        "idp_refresh_token": "refresh-token",
        "idp_access_token": "old-access-token",
        "idp_token_expiry": 1,
        "google_client_id": "old-client",
        "google_client_secret": "old-secret",
        "gcp_project": "project-1",
    }

    class FakeAuthService:
        def encrypt_token_blob(self, payload):
            return {"encrypted": dict(payload)}

    commits = []

    def commit_runtime_updates(observed_db, *runtimes):
        commits.append((observed_db, runtimes))

    service = GCAPoolService()
    service._commit_runtime_updates = commit_runtime_updates
    new_token = service._try_refresh(
        runtime,
        FakeAuthService(),
        token_data,
        db,
    )

    assert new_token == "new-access-token"
    assert captured_request == {
        "url": "https://oauth2.googleapis.com/token",
        "timeout": 10,
        "method": "POST",
        "content_type": "application/x-www-form-urlencoded",
    }
    assert token_data["idp_access_token"] == "new-access-token"
    assert token_data["idp_token_expiry"] > 1
    assert "google_client_id" not in token_data
    assert "google_client_secret" not in token_data
    assert runtime.auth_status == "connected"
    assert runtime.auth_config["encrypted"]["idp_access_token"] == "new-access-token"
    assert commits == [(db, (runtime,))]

    runtime_2 = SimpleNamespace(
        id="gca-runtime-2",
        auth_config={},
        auth_status="expired",
    )
    token_data_2 = {
        "idp_refresh_token": "refresh-token",
        "idp_access_token": "old-access-token",
        "idp_token_expiry": 1,
    }
    commits.clear()
    direct_token = token_refresh.try_refresh_token(
        runtime_2,
        FakeAuthService(),
        token_data_2,
        db,
        commit_runtime_updates,
    )

    assert direct_token == "new-access-token"
    assert commits == [(db, (runtime_2,))]


def test_source_seams_do_not_create_duplicate_resource_paths():
    source = "\n".join(path.read_text() for path in SOURCE_FILES)

    forbidden_terms = [
        "APIRouter",
        "include_router",
        "setInterval",
        "setTimeout",
        "create_task(",
        "asyncio.create_task",
        "Thread(",
        "Process(",
        "Queue(",
        "PGBOUNCER_ADMIN_URL",
        "DB_POOL_SIZE",
        "DB_MAX_OVERFLOW",
        "create_engine(",
    ]
    for term in forbidden_terms:
        assert term not in source

    assert source.count("class GCAPoolService") == 1
    assert source.count("def get_active_token(") == 1
    assert source.count("def report_quota_exhausted(") == 1
    assert source.count("def _get_db(") == 1
