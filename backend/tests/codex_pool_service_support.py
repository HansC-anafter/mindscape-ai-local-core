from types import SimpleNamespace

from backend.app.services.codex_pool_health import HEALTH_METADATA_KEY


def _runtime(
    runtime_id,
    *,
    health_state="healthy",
    auth_type="host_session",
    seed_kind="real_home",
):
    extra_metadata = {
        HEALTH_METADATA_KEY: {
            "health_state": health_state,
            "seed_kind": seed_kind,
        }
    }
    if seed_kind == "real_home":
        extra_metadata["CODEX_HOME"] = f"/Users/shock/.codex/{runtime_id}"
    if seed_kind == "account_home":
        extra_metadata["CODEX_HOME"] = (
            f"/Users/shock/.mindscape/runtime/codex-home-pool/accounts/acct-{runtime_id}"
        )
        extra_metadata["login_email"] = f"{runtime_id}@example.test"
    return SimpleNamespace(
        id=runtime_id,
        auth_type=auth_type,
        extra_metadata=extra_metadata,
    )
