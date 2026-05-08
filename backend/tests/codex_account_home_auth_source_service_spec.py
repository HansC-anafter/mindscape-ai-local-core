import json
import base64
import hashlib
from types import SimpleNamespace

from backend.app.services.codex_account_home_auth_source_service import (
    CodexAccountHomeAuthSourceService,
)
from backend.app.services.codex_pool_health import HEALTH_METADATA_KEY


def _jwt(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"header.{encoded}.signature"


def test_account_home_auth_source_inventory_reads_materialized_auth_json(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "access_token": "access-a",
                    "refresh_token": "refresh-a",
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = SimpleNamespace(
        id="runtime-a",
        auth_type="host_session",
        extra_metadata={
            "CODEX_HOME": str(codex_home),
            "login_email": "account-a@example.test",
            "account_key": "account-a",
            HEALTH_METADATA_KEY: {
                "seed_kind": "account_home",
                "health_state": "healthy",
            },
        },
    )

    sources = CodexAccountHomeAuthSourceService(
        runtime_loader=lambda: [runtime],
    ).inventory_sources()

    assert len(sources) == 1
    assert sources[0]["source_type"] == "account_home_auth_json"
    assert sources[0]["login_email"] == "account-a@example.test"
    assert sources[0]["account_key"] == "account-a"
    assert sources[0]["has_access"] is True
    assert sources[0]["has_refresh"] is True
    assert sources[0]["source_event_id"]


def test_account_home_auth_source_inventory_prefers_auth_identity_over_seed_metadata(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-a"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "workspace-account",
                    "access_token": "access-a",
                    "refresh_token": "refresh-a",
                    "id_token": _jwt(
                        {
                            "email": "fresh@example.test",
                            "https://api.openai.com/auth": {
                                "chatgpt_user_id": "fresh-user-id",
                            },
                        }
                    ),
                },
            }
        ),
        encoding="utf-8",
    )
    runtime = SimpleNamespace(
        id="runtime-a",
        auth_type="host_session",
        extra_metadata={
            "CODEX_HOME": str(codex_home),
            "login_email": "stale@example.test",
            "account_key": "stale-account-key",
            HEALTH_METADATA_KEY: {
                "seed_kind": "account_home",
                "health_state": "healthy",
            },
        },
    )

    sources = CodexAccountHomeAuthSourceService(
        runtime_loader=lambda: [runtime],
    ).inventory_sources()

    assert sources[0]["login_email"] == "fresh@example.test"
    assert sources[0]["account_key"] == hashlib.sha256(
        b"account:workspace-account:user:fresh-user-id"
    ).hexdigest()[:24]


def test_account_home_auth_source_account_key_distinguishes_workspace_scope(tmp_path):
    runtimes = []
    for account_id in ("personal-account", "workspace-account"):
        codex_home = tmp_path / "accounts" / account_id
        codex_home.mkdir(parents=True)
        (codex_home / "auth.json").write_text(
            json.dumps(
                {
                    "auth_mode": "chatgpt",
                    "tokens": {
                        "account_id": account_id,
                        "access_token": f"access-{account_id}",
                        "refresh_token": f"refresh-{account_id}",
                        "id_token": _jwt(
                            {
                                "email": "same@example.test",
                                "https://api.openai.com/auth": {
                                    "chatgpt_user_id": "same-user-id",
                                },
                            }
                        ),
                    },
                }
            ),
            encoding="utf-8",
        )
        runtimes.append(
            SimpleNamespace(
                id=f"runtime-{account_id}",
                auth_type="host_session",
                extra_metadata={
                    "CODEX_HOME": str(codex_home),
                    HEALTH_METADATA_KEY: {
                        "seed_kind": "account_home",
                        "health_state": "healthy",
                    },
                },
            )
        )

    sources = CodexAccountHomeAuthSourceService(
        runtime_loader=lambda: runtimes,
    ).inventory_sources()

    assert len({source["account_key"] for source in sources}) == 2


def test_account_home_identity_details_include_personal_workspace_scope(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-personal"
    codex_home.mkdir(parents=True)
    (codex_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "personal-account",
                    "access_token": "access",
                    "refresh_token": "refresh",
                    "id_token": _jwt(
                        {
                            "email": "agent@example.test",
                            "sub": "oauth-subject",
                            "https://api.openai.com/auth": {
                                "chatgpt_account_id": "personal-account",
                                "chatgpt_plan_type": "free",
                                "chatgpt_user_id": "user-a",
                                "organizations": [
                                    {
                                        "id": "org-personal",
                                        "title": "Personal",
                                        "role": "owner",
                                        "is_default": True,
                                    }
                                ],
                            },
                        }
                    ),
                },
            }
        ),
        encoding="utf-8",
    )

    details = CodexAccountHomeAuthSourceService.identity_details_for_codex_home(
        str(codex_home)
    )

    assert details["auth_account_id"] == "personal-account"
    assert details["auth_chatgpt_user_id"] == "user-a"
    assert details["account_scope_type"] == "personal"
    assert details["account_scope_label"] == "Personal"
    assert details["account_scope_role"] == "owner"
    assert details["account_plan_type"] == "free"
    assert details["account_organization_id"] == "org-personal"


def test_account_home_auth_source_inventory_ignores_unmaterialized_browser_state(tmp_path):
    codex_home = tmp_path / "accounts" / "acct-browser-only"
    codex_home.mkdir(parents=True)
    runtime = SimpleNamespace(
        id="runtime-browser",
        auth_type="host_session",
        extra_metadata={
            "CODEX_HOME": str(codex_home),
            "login_email": "browser@example.test",
            HEALTH_METADATA_KEY: {
                "seed_kind": "account_home",
                "health_state": "healthy",
            },
        },
    )

    sources = CodexAccountHomeAuthSourceService(
        runtime_loader=lambda: [runtime],
    ).inventory_sources()

    assert sources == []


def test_account_home_auth_source_inventory_excludes_primary_and_captured_archives(tmp_path):
    primary_home = tmp_path / "primary"
    primary_home.mkdir()
    (primary_home / "auth.json").write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "primary-account",
                    "access_token": "primary-access",
                    "refresh_token": "primary-refresh",
                },
            }
        ),
        encoding="utf-8",
    )
    pool_root = tmp_path / "codex-home-pool"
    archive_root = pool_root / "captured-primary-auth"
    archive_root.mkdir(parents=True)
    archive_path = archive_root / "archiveaccount-20260507T120000000000Z.auth.json"
    archive_path.write_text(
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "tokens": {
                    "account_id": "archiveaccount",
                    "access_token": "archive-access",
                    "refresh_token": "archive-refresh",
                },
            }
        ),
        encoding="utf-8",
    )

    sources = CodexAccountHomeAuthSourceService(
        runtime_loader=lambda: [],
        primary_codex_home=str(primary_home),
        managed_pool_root=str(pool_root),
        include_non_runtime_sources=True,
    ).inventory_sources()

    assert sources == []
