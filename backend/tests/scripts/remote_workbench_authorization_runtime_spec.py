from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.http import HttpResponse
from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover.runtime import RuntimeGate
from remote_workbench_authorization_cutover.secure_inputs import (
    EXPECTED_ISSUER,
    EXPECTED_TARGET_WORKSPACE_ID,
    SecureInputs,
)


class RuntimeExecutor:
    def __init__(self, status: dict) -> None:
        self.status = status
        self.calls: list[list[str]] = []

    def run(self, args, *, timeout_seconds=60.0, input_text=None) -> str:
        self.calls.append(list(args))
        return json.dumps(self.status)


class RuntimeHttp:
    def __init__(self, response: HttpResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict] = []

    def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _runtime(http: RuntimeHttp, status: dict | None = None) -> RuntimeGate:
    return RuntimeGate(
        repo_root=REPO_ROOT,
        executor=RuntimeExecutor(status or {}),
        http=http,
    )


def _supervisor_payload(*, maintenance: bool = False) -> dict:
    return {
        "activation_conformant": True,
        "argv": [
            str(REPO_ROOT / ".venv/bin/python"),
            str(REPO_ROOT / "scripts/remote_workbench_bridge_monitor.py"),
        ],
        "checked_at": "2026-07-13T06:00:00Z",
        "current_build_id": "build-a",
        "launchd_running": True,
        "live_build_id": "build-a",
        "maintenance": maintenance,
        "pid": 123,
        "state": "maintenance" if maintenance else "ready",
        "status_fresh": True,
    }


def test_supervisor_activation_and_final_exact_verifier_schema() -> None:
    executor = RuntimeExecutor(_supervisor_payload(maintenance=True))
    runtime = RuntimeGate(repo_root=REPO_ROOT, executor=executor, http=object())

    runtime.activate_supervisor()
    assert runtime.verify_supervisor()["state"] == "maintenance"

    assert executor.calls[0] == [
        str(REPO_ROOT / "scripts/install-remote-workbench-bridge-macos.sh"),
        "install",
    ]
    assert executor.calls[1] == [
        str(REPO_ROOT / "scripts/start_remote_workbench_tunnel.sh"),
        "supervisor",
        "verify",
        "--json",
    ]
    for field, value in (("launchd_running", False), ("state", "ready")):
        payload = _supervisor_payload(maintenance=True)
        payload[field] = value
        with pytest.raises(CutoverError, match="current canonical build"):
            _runtime(RuntimeHttp(HttpResponse(200, {}, b"{}")), payload).verify_supervisor()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "persisted_policy"),
        ("remote_access_state", "enforced"),
        ("access_issuer", EXPECTED_ISSUER),
        ("local_core_super_admins", [{"email": "hans@anafter.co"}]),
    ],
)
def test_initial_seed_rejects_any_partially_configured_runtime(field, value) -> None:
    payload = {
        "id": "remote-workbench-runtime",
        "access_issuer": None,
        "access_audience": None,
        "auth_config_fingerprint": None,
        "auth_config_source": "runtime_policy",
        "remote_access_state": "enrollment_only",
        "local_core_super_admins": [],
        "revision": 7,
        "source": "default_deny",
    }
    payload[field] = value
    with pytest.raises(CutoverError, match="exact initial seed"):
        _runtime(RuntimeHttp(HttpResponse(200, {}, b"{}"))).assert_initial_seed(payload, 7)


def test_workflow_activation_and_origin_reconcile_order_is_single_path() -> None:
    source = (
        REPO_ROOT / "scripts/remote_workbench_authorization_cutover/workflow.py"
    ).read_text(encoding="utf-8")
    edge = source.index("self.edge.verify()")
    idle = source.index("self.release.require_no_active_install_jobs()", edge)
    pause = source.index('"06a-infra"', idle)
    backup = source.index("self.release.verify_or_create_backup()", pause)
    activate = source.index("self.runtime.activate_supervisor()", backup)
    verify = source.index("self.runtime.verify_supervisor()", activate)
    inspect = source.index("self.runtime.inspect_origin", verify)
    close = source.index("self.runtime.close_and_prove", inspect)
    reconcile = source.index("self.runtime.reconcile_origin", close)
    database = source.index("self.release.verify_database_pools()", reconcile)
    known_good = source.index("self.release.capture_known_good", database)

    assert edge < idle < pause < backup < activate < verify < inspect
    assert inspect < close < reconcile < database < known_good


def test_workspace_api_records_require_both_exact_real_workspace_ids() -> None:
    class WorkspaceHttp:
        def __init__(self) -> None: self.calls: list[str] = []
        def get_json(self, url, **_kwargs):
            self.calls.append(url)
            return {"id": url.rstrip("/").split("/")[-2]}

    http = WorkspaceHttp()
    RuntimeGate(repo_root=REPO_ROOT, executor=RuntimeExecutor({}), http=http).verify_workspace_records(
        EXPECTED_TARGET_WORKSPACE_ID,
        "e81713b4-385e-4755-96d5-1ceca4ec9e99",
    )
    assert len(http.calls) == 2

    class MissingHttp:
        def get_json(self, _url, **_kwargs): return {"id": "wrong"}

    with pytest.raises(CutoverError, match="workspace API row"):
        RuntimeGate(
            repo_root=REPO_ROOT,
            executor=RuntimeExecutor({}),
            http=MissingHttp(),
        ).verify_workspace_records(
            EXPECTED_TARGET_WORKSPACE_ID,
            "e81713b4-385e-4755-96d5-1ceca4ec9e99",
        )


def test_public_request_uses_access_cookie_not_origin_assertion(tmp_path: Path) -> None:
    assertion = tmp_path / "principal.jwt"
    assertion.write_text("signed-access-cookie", encoding="utf-8")
    http = RuntimeHttp(HttpResponse(403, {}, b"{}"))

    _runtime(http)._principal_request(
        assertion,
        EXPECTED_TARGET_WORKSPACE_ID,
        upgrade=False,
    )

    headers = http.calls[0]["headers"]
    assert headers == {
        "Cookie": "CF_Authorization=signed-access-cookie",
        "Referer": (
            "https://remote-workbench.mindscapeai.app/workspaces/"
            f"{EXPECTED_TARGET_WORKSPACE_ID}"
        ),
    }
    assert "Cf-Access-Jwt-Assertion" not in headers


def test_closed_origin_requires_launcher_contract_and_observable_edge_5xx(
    tmp_path: Path,
) -> None:
    assertion = tmp_path / "principal.jwt"
    assertion.write_text("signed-access-cookie", encoding="utf-8")
    status = {"running": False, "maintenance": True, "contract_conformant": True}
    _runtime(RuntimeHttp(HttpResponse(530, {}, b"")), status)._assert_public_unreachable(
        assertion,
        EXPECTED_TARGET_WORKSPACE_ID,
    )

    inconclusive = _runtime(RuntimeHttp(CutoverError("network exception")), status)
    with pytest.raises(CutoverError, match="inconclusive"):
        inconclusive._assert_public_unreachable(assertion, EXPECTED_TARGET_WORKSPACE_ID)

    redirect = _runtime(RuntimeHttp(HttpResponse(302, {}, b"")), status)
    with pytest.raises(CutoverError, match="5xx"):
        redirect._assert_public_unreachable(assertion, EXPECTED_TARGET_WORKSPACE_ID)


def test_runtime_readback_separates_auth_config_source_from_row_source() -> None:
    runtime = _runtime(RuntimeHttp(HttpResponse(200, {}, b"{}")))
    expected = {
        "access_issuer": None,
        "access_audience": None,
        "remote_access_state": "enrollment_only",
        "local_core_super_admins": [],
    }
    payload = {
        "id": "remote-workbench-runtime",
        **expected,
        "auth_config_fingerprint": None,
        "auth_config_source": "runtime_policy",
        "source": "default_deny",
        "revision": 0,
    }
    runtime.assert_policy_readback(payload, expected)
    payload["auth_config_source"] = "default_deny"
    with pytest.raises(CutoverError, match="auth source"):
        runtime.assert_policy_readback(payload, expected)
    payload["auth_config_source"] = "runtime_policy"
    payload["source"] = "persisted_policy"
    with pytest.raises(CutoverError, match="row source"):
        runtime.assert_policy_readback(payload, expected)


def test_allowed_public_contract_rejects_redirects_and_non_upgrade_responses() -> None:
    runtime = _runtime(RuntimeHttp(HttpResponse(200, {}, b"{}")))
    runtime._assert_principal_response(
        HttpResponse(200, {}, b""),
        allowed=True,
        expected_reason=None,
        upgrade=False,
    )
    runtime._assert_principal_response(
        HttpResponse(101, {}, b""),
        allowed=True,
        expected_reason=None,
        upgrade=True,
    )
    with pytest.raises(CutoverError, match="expected upstream"):
        runtime._assert_principal_response(
            HttpResponse(302, {}, b""),
            allowed=True,
            expected_reason=None,
            upgrade=False,
        )
    with pytest.raises(CutoverError, match="expected upstream"):
        runtime._assert_principal_response(
            HttpResponse(404, {}, b""),
            allowed=True,
            expected_reason=None,
            upgrade=True,
        )


def test_admin_capability_mismatch_uses_resolved_workspace_for_http_and_upgrade(
    tmp_path: Path,
) -> None:
    assertion = tmp_path / "principal.jwt"
    assertion.write_text("signed-access-cookie", encoding="utf-8")
    response = HttpResponse(
        403,
        {
            "x-mindscape-remote-auth-stage": "principal_verified",
            "x-mindscape-remote-auth-reason": "capability_not_allowed",
        },
        b"{}",
    )
    http = RuntimeHttp(response)
    runtime = _runtime(http)

    for upgrade in (False, True):
        result = runtime._principal_request(
            assertion,
            EXPECTED_TARGET_WORKSPACE_ID,
            upgrade=upgrade,
            denied_capability=True,
        )
        runtime._assert_principal_response(
            result,
            allowed=False,
            expected_reason="capability_not_allowed",
            upgrade=upgrade,
        )

    for call in http.calls:
        assert (
            "/installed-capabilities/mindscape_cloud_integration?workspace_id="
            f"{EXPECTED_TARGET_WORKSPACE_ID}"
        ) in call["url"]
        assert call["headers"]["Referer"].endswith(EXPECTED_TARGET_WORKSPACE_ID)
    assert "Upgrade" not in http.calls[0]["headers"]
    assert http.calls[1]["headers"]["Upgrade"] == "websocket"

    with pytest.raises(CutoverError, match="expected authorization stage"):
        runtime._assert_principal_response(
            HttpResponse(
                403,
                {
                    "x-mindscape-remote-auth-stage": "principal_verified",
                    "x-mindscape-remote-auth-reason": "capability_path_not_allowed",
                },
                b"{}",
            ),
            allowed=False,
            expected_reason="capability_not_allowed",
            upgrade=False,
        )


def _candidate_inputs(tmp_path: Path) -> SecureInputs:
    return SecureInputs(
        directory=tmp_path,
        policy={
            "access_issuer": EXPECTED_ISSUER,
            "local_core_super_admins": [
                {
                    "email": "hans@anafter.co",
                    "subject": "subject-hans",
                    "status": "active",
                },
                {
                    "email": "pproo.reader@gmail.com",
                    "subject": "subject-pproo",
                    "status": "active",
                },
            ],
        },
        jwt_paths={},
        jwt_claims={
            "hans": {
                "iss": EXPECTED_ISSUER,
                "email": "hans@anafter.co",
                "sub": "subject-hans",
            },
            "pproo": {
                "iss": EXPECTED_ISSUER,
                "email": "pproo.reader@gmail.com",
                "sub": "subject-pproo",
            },
            "outsider": {
                "iss": EXPECTED_ISSUER,
                "email": "outsider@example.com",
                "sub": "subject-outsider",
            },
        },
    )


def _candidate_event(email: str, subject: str, timestamp: datetime) -> dict:
    return {
        "timestamp": timestamp.isoformat(),
        "workspace_id": EXPECTED_TARGET_WORKSPACE_ID,
        "reason_code": "remote_access_enrollment_only",
        "subject_candidate": {
            "issuer": EXPECTED_ISSUER,
            "email": email,
            "subject": subject,
        },
    }


class EnrollmentHttp:
    def __init__(self, events: list[dict]) -> None:
        self.events = events
        self.request_count = 0
        self.audit_get_count = 0

    def request(self, method, url, **kwargs) -> HttpResponse:
        self.request_count += 1
        return HttpResponse(
            403,
            {
                "x-mindscape-remote-auth-stage": "principal_verified",
                "x-mindscape-remote-auth-reason": "remote_access_enrollment_only",
            },
            b"{}",
        )

    def get_json(self, url, **_kwargs) -> dict:
        self.audit_get_count += 1
        return {"events": self.events}


def test_enrollment_discovery_uses_three_requests_and_exactly_one_audit_get(
    tmp_path: Path,
) -> None:
    captured = datetime.now(timezone.utc) + timedelta(seconds=1)
    http = EnrollmentHttp(
        [
            _candidate_event("hans@anafter.co", "subject-hans", captured),
            _candidate_event("pproo.reader@gmail.com", "subject-pproo", captured),
        ]
    )
    base = _candidate_inputs(tmp_path)
    jwt_paths = {}
    for label in ("hans", "pproo", "outsider"):
        path = tmp_path / f"{label}.jwt"
        path.write_text(f"{label}-access-cookie", encoding="utf-8")
        jwt_paths[label] = path
    inputs = SecureInputs(
        directory=base.directory,
        policy=base.policy,
        jwt_paths=jwt_paths,
        jwt_claims=base.jwt_claims,
    )

    RuntimeGate(
        repo_root=REPO_ROOT,
        executor=RuntimeExecutor({}),
        http=http,
    ).verify_enrollment_assertions(inputs, EXPECTED_TARGET_WORKSPACE_ID)

    assert http.request_count == 3
    assert http.audit_get_count == 1


def test_enrollment_candidate_validation_rejects_missing_candidate(tmp_path: Path) -> None:
    started = datetime.now(timezone.utc)
    audit = {
        "events": [
            _candidate_event("hans@anafter.co", "subject-hans", started + timedelta(seconds=1))
        ]
    }
    with pytest.raises(CutoverError, match="missing or ambiguous"):
        RuntimeGate.validate_enrollment_candidates(
            audit,
            inputs=_candidate_inputs(tmp_path),
            workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
            started_at=started,
        )


def test_enrollment_candidate_validation_rejects_mismatch(tmp_path: Path) -> None:
    started = datetime.now(timezone.utc)
    audit = {
        "events": [
            _candidate_event("hans@anafter.co", "subject-hans", started + timedelta(seconds=1)),
            _candidate_event(
                "pproo.reader@gmail.com",
                "wrong-subject",
                started + timedelta(seconds=1),
            ),
        ]
    }
    with pytest.raises(CutoverError, match="signed evidence"):
        RuntimeGate.validate_enrollment_candidates(
            audit,
            inputs=_candidate_inputs(tmp_path),
            workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
            started_at=started,
        )


def test_enrollment_candidate_validation_rejects_ambiguous_candidate(
    tmp_path: Path,
) -> None:
    started = datetime.now(timezone.utc)
    hans = _candidate_event(
        "hans@anafter.co",
        "subject-hans",
        started + timedelta(seconds=1),
    )
    audit = {
        "events": [
            hans,
            dict(hans),
            _candidate_event(
                "pproo.reader@gmail.com",
                "subject-pproo",
                started + timedelta(seconds=1),
            ),
        ]
    }
    with pytest.raises(CutoverError, match="missing or ambiguous"):
        RuntimeGate.validate_enrollment_candidates(
            audit,
            inputs=_candidate_inputs(tmp_path),
            workspace_id=EXPECTED_TARGET_WORKSPACE_ID,
            started_at=started,
        )
