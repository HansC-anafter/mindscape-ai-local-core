from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from cryptography.fernet import Fernet

import backend.app.services.runtime_auth_service as runtime_auth_module
from backend.app.services.runtime_auth_service import RuntimeAuthService
from backend.app.services.runtime_auth_service_core import credential_codec
from backend.app.services.runtime_auth_service_core import token_refresh


REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILES = [
    REPO_ROOT / "backend/app/services/runtime_auth_service.py",
    REPO_ROOT / "backend/app/services/runtime_auth_service_core/__init__.py",
    REPO_ROOT / "backend/app/services/runtime_auth_service_core/key_resolution.py",
    REPO_ROOT / "backend/app/services/runtime_auth_service_core/credential_codec.py",
    REPO_ROOT / "backend/app/services/runtime_auth_service_core/token_refresh.py",
]


def _service(monkeypatch) -> RuntimeAuthService:
    monkeypatch.setenv("RUNTIME_ENCRYPTION_KEY", Fernet.generate_key().decode())
    return RuntimeAuthService()


def test_facade_preserves_credential_and_token_blob_codec(monkeypatch):
    service = _service(monkeypatch)
    credentials = {
        "api_key": "api-secret",
        "client_secret": "client-secret",
        "client_id": "client-id",
    }

    encrypted_credentials = service.encrypt_credentials(credentials)

    assert encrypted_credentials["api_key"] != "api-secret"
    assert encrypted_credentials["client_secret"] != "client-secret"
    assert service.decrypt_credentials(encrypted_credentials) == credentials

    token_config = service.encrypt_token_blob(
        {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expiry": 12345,
            "identity": "runtime@example.test",
        }
    )

    assert token_config["identity"] == "runtime@example.test"
    assert token_config["token_blob"]
    assert service.decrypt_token_blob(token_config) == {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "expiry": 12345,
        "identity": "runtime@example.test",
    }
    assert service.validate_auth_config("none", None) is True
    assert service.validate_auth_config("api_key", {"api_key": "secret"}) is True
    assert service.validate_auth_config("oauth2", token_config) is True


def test_facade_preserves_token_expiry_rules(monkeypatch):
    service = _service(monkeypatch)
    monkeypatch.setattr(credential_codec.time, "time", lambda: 100.0)

    assert service._is_token_expired({"expiry": 99}) is True
    assert service._is_token_expired({"expiry": 101}) is False
    assert service._is_token_expired({"expiry": 0}) is False
    assert service._is_token_expired({"expiry": "0", "idp_token_expiry": 99}) is True
    assert service._is_token_expired({"idp_token_expiry": 101}) is False
    assert service._is_token_expired({"expiry": "not-a-number"}) is False


def test_expired_oauth_without_refresh_marks_runtime_once(monkeypatch):
    service = _service(monkeypatch)
    runtime = SimpleNamespace(
        id="runtime-auth-expired",
        auth_type="oauth2",
        auth_config=service.encrypt_token_blob(
            {
                "access_token": "expired-access-token",
                "expiry": 1,
            }
        ),
        auth_status="connected",
    )
    observed = []

    def fake_commit(db, committed_runtime):
        observed.append((db, committed_runtime))

    db = object()
    monkeypatch.setattr(runtime_auth_module, "_commit_runtime_registration", fake_commit)

    headers = asyncio.run(service.get_auth_headers(runtime, db=db))

    assert headers == {}
    assert runtime.auth_status == "expired"
    assert observed == [(db, runtime)]


def test_oidc_refresh_helper_uses_single_commit_callback(monkeypatch):
    service = _service(monkeypatch)
    runtime = SimpleNamespace(
        id="runtime-auth-oidc",
        config_url="https://provider.example.test/settings",
        auth_config={},
    )
    token_data = {
        "refresh_token": "old-refresh-token",
        "token_source": "oidc",
    }
    observed = []
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 900,
            }

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, data):
            captured["url"] = url
            captured["data"] = data
            return FakeResponse()

    def fake_commit(db, committed_runtime):
        observed.append((db, committed_runtime))

    db = object()
    monkeypatch.setattr(token_refresh.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(runtime_auth_module, "_commit_runtime_registration", fake_commit)

    access_token = asyncio.run(
        service._refresh_oauth_token(runtime, token_data, db=db)
    )

    assert access_token == "new-access-token"
    assert captured["timeout"] == 10.0
    assert captured["url"] == "https://provider.example.test/api/v1/oidc/token"
    assert captured["data"] == {
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh-token",
        "client_id": "runtime-oauth",
    }
    assert observed == [(db, runtime)]
    decrypted = service.decrypt_token_blob(runtime.auth_config)
    assert decrypted["access_token"] == "new-access-token"
    assert decrypted["refresh_token"] == "new-refresh-token"
    assert decrypted["expiry"] > 0


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
        "sessionmaker(",
    ]
    for term in forbidden_terms:
        assert term not in source

    assert source.count("class RuntimeAuthService") == 1
    assert source.count("def get_auth_headers(") == 1
    assert source.count("def _refresh_oauth_token(") == 1
    assert source.count("def refresh_oauth_token(") == 1
    assert source.count("def _commit_runtime_registration(") == 1
