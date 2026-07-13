"""Runtime policy transition and original-path verification gates."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping
from .http import HttpClient, HttpResponse
from .io import CommandExecutor, CutoverError
from .origin import OriginTopologyGate
from .runtime_enrollment import (
    validate_enrollment_candidates as validate_enrollment_candidate_events,
    verify_enrollment_assertions as verify_signed_enrollment_assertions,
)
from .runtime_public_transport import (
    assert_principal_response,
    principal_request,
    public_path_request,
)
from .runtime_acceptance import (
    verify_actual_gateway_cache_latency,
    verify_effective_policies as verify_effective_policy_snapshots,
    verify_pending_coherence,
    verify_public_matrix as verify_public_acceptance_matrix,
    verify_workspace_api_records,
)
from .secure_inputs import (
    EXPECTED_FINGERPRINT,
    EXPECTED_TARGET_CAPABILITIES,
    SecureInputs,
)


RUNTIME_POLICY_URL = (
    "http://localhost:8300/api/v1/capabilities/mindscape_cloud_integration/"
    "mobile-workbench-gateway/runtime-policy"
)
HEALTH_URL = "http://localhost:8300/api/v1/host/services/mobile-workbench-gateway/health"
AUDIT_URL = "http://localhost:8300/api/v1/host/services/mobile-workbench-gateway/audit"
POLICY_PATH_PREFIX = (
    "/api/v1/capabilities/mindscape_cloud_integration/"
    "mobile-workbench-gateway/workspaces"
)


class RuntimeGate:
    """Apply one closed transition path and verify effective authorization."""
    def __init__(
        self,
        *,
        repo_root: Path,
        executor: CommandExecutor,
        http: HttpClient,
        public_origin: str = "https://remote-workbench.mindscapeai.app",
    ) -> None:
        self.repo_root = repo_root
        self.executor = executor
        self.http = http
        self.public_origin = public_origin.rstrip("/")
        self.launcher = repo_root / "scripts/start_remote_workbench_tunnel.sh"
        self.health_url = HEALTH_URL
        self.audit_url = AUDIT_URL
        self.origin = OriginTopologyGate(repo_root=repo_root, executor=executor)

    def activate_supervisor(self) -> None:
        self.executor.run(
            [str(self.repo_root / "scripts/install-remote-workbench-bridge-macos.sh"), "install"],
            timeout_seconds=600.0,
        )
    def _launcher(self, *args: str) -> None:
        self.executor.run([str(self.launcher), *args], timeout_seconds=60.0)

    def verify_supervisor(self) -> dict[str, Any]:
        """Require the installed live supervisor to run the current canonical build."""
        raw = self.executor.run(
            [str(self.launcher), "supervisor", "verify", "--json"],
            timeout_seconds=30.0,
        )
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as error:
            raise CutoverError("Supervisor verification output is malformed") from error
        expected_keys = {
            "activation_conformant",
            "argv",
            "checked_at",
            "current_build_id",
            "launchd_running",
            "live_build_id",
            "maintenance",
            "pid",
            "state",
            "status_fresh",
        }
        expected_argv = [
            str(self.repo_root / ".venv/bin/python"),
            str(self.repo_root / "scripts/remote_workbench_bridge_monitor.py"),
        ]
        if (
            not isinstance(payload, dict)
            or set(payload) != expected_keys
            or payload.get("activation_conformant") is not True
            or payload.get("launchd_running") is not True
            or payload.get("status_fresh") is not True
            or payload.get("argv") != expected_argv
            or payload.get("current_build_id") != payload.get("live_build_id")
            or not isinstance(payload.get("current_build_id"), str)
            or not payload.get("current_build_id")
            or type(payload.get("pid")) is not int
            or payload.get("pid") <= 0
            or type(payload.get("maintenance")) is not bool
            or (
                payload.get("state")
                != ("maintenance" if payload.get("maintenance") else "ready")
            )
            or not isinstance(payload.get("checked_at"), str)
        ):
            raise CutoverError("Live supervisor does not match the current canonical build")
        return payload

    def inspect_origin(self, secure_dir: Path, workspace_id: str) -> dict[str, Any]:
        return self.origin.inspect(secure_dir, workspace_id)

    def reconcile_origin(
        self,
        drift: Mapping[str, Any],
        *,
        secure_dir: Path,
        workspace_id: str,
    ) -> dict[str, Any]:
        return self.origin.reconcile(
            drift,
            secure_dir=secure_dir,
            workspace_id=workspace_id,
        )

    def recover_origin(self, secure_dir: Path) -> bool: return self.origin.recover_persisted(secure_dir)
    def verify_workspace_records(self, target: str, inheritance: str) -> None: verify_workspace_api_records(self, (target, inheritance))
    def safe_close(self, reason: str) -> None:
        """Enter maintenance and stop the tunnel, preserving both on failure."""

        first_error: Exception | None = None
        try:
            self._launcher("maintenance", "enter", reason)
        except Exception as error:  # noqa: BLE001 - the stop attempt is mandatory
            first_error = error
        try:
            self._launcher("stop")
        except Exception as error:  # noqa: BLE001 - preserve the first failure
            if first_error is None:
                first_error = error
        if first_error is not None:
            raise CutoverError("Failed to close the public tunnel safely") from first_error

    def exit_maintenance(self) -> None:
        """Exit maintenance only after every acceptance gate has passed."""

        self._launcher("maintenance", "exit")

    def reopen_transport(self) -> None:
        """Start the canonical tunnel only after its remote ingress lock exists."""

        self._launcher("ensure")

    def close_and_prove(self, assertion_path: Path, workspace_id: str) -> None:
        """Close the public tunnel and require both local and edge evidence."""

        self.safe_close("authorization_transition")
        self._assert_public_unreachable(assertion_path, workspace_id)

    def get_runtime_policy(self) -> dict[str, Any]:
        """Read the singleton policy from the local-only frontend path."""

        return self.http.get_json(
            RUNTIME_POLICY_URL, timeout_seconds=5.0, max_response_bytes=32_768
        )

    def get_effective_policy(self, workspace_id: str) -> dict[str, Any]:
        """Read one effective workspace projection from the existing facade."""

        return self.http.get_json(
            f"http://localhost:8300{POLICY_PATH_PREFIX}/{workspace_id}/policy",
            timeout_seconds=5.0,
            max_response_bytes=32_768,
        )

    @staticmethod
    def policy_body(snapshot: Mapping[str, Any], expected_revision: int) -> dict[str, Any]:
        """Build the exact full-replacement PUT body from a runtime snapshot."""

        return {
            "expected_revision": expected_revision,
            "access_issuer": snapshot.get("access_issuer"),
            "access_audience": snapshot.get("access_audience"),
            "remote_access_state": snapshot.get("remote_access_state"),
            "local_core_super_admins": snapshot.get("local_core_super_admins") or [],
        }

    @staticmethod
    def _normalized_admins(values: Any) -> list[dict[str, str]]:
        if not isinstance(values, list):
            raise CutoverError("Runtime policy administrators are malformed")
        normalized = []
        for item in values:
            if not isinstance(item, Mapping):
                raise CutoverError("Runtime policy administrator is malformed")
            normalized.append(
                {
                    "subject": str(item.get("subject") or ""),
                    "email": str(item.get("email") or "").lower(),
                    "status": str(item.get("status") or ""),
                }
            )
        return sorted(normalized, key=lambda item: (item["email"], item["subject"]))

    def assert_policy_readback(
        self,
        payload: Mapping[str, Any],
        expected: Mapping[str, Any],
    ) -> None:
        """Require exact auth config, state, source, and administrator readback."""

        if payload.get("id") != "remote-workbench-runtime":
            raise CutoverError("Runtime policy singleton id mismatch")
        for key in ("access_issuer", "access_audience", "remote_access_state"):
            if payload.get(key) != expected.get(key):
                raise CutoverError(f"Runtime policy readback mismatch: {key}")
        if self._normalized_admins(payload.get("local_core_super_admins")) != self._normalized_admins(
            expected.get("local_core_super_admins")
        ):
            raise CutoverError("Runtime policy administrator readback mismatch")
        nullable = expected.get("access_issuer") is None
        expected_fingerprint = None if nullable else EXPECTED_FINGERPRINT
        expected_row_source = "default_deny" if nullable else "persisted_policy"
        if payload.get("auth_config_fingerprint") != expected_fingerprint:
            raise CutoverError("Runtime policy fingerprint readback mismatch")
        if payload.get("auth_config_source") != "runtime_policy":
            raise CutoverError("Runtime policy auth source readback mismatch")
        if payload.get("source") != expected_row_source:
            raise CutoverError("Runtime policy row source readback mismatch")
        if not isinstance(payload.get("revision"), int):
            raise CutoverError("Runtime policy revision is missing")

    def assert_initial_seed(self, payload: Mapping[str, Any], revision: int) -> None:
        """Block reruns until an explicit backout restores the exact initial seed."""

        expected = {
            "id": "remote-workbench-runtime",
            "access_issuer": None,
            "access_audience": None,
            "auth_config_fingerprint": None,
            "auth_config_source": "runtime_policy",
            "remote_access_state": "enrollment_only",
            "local_core_super_admins": [],
            "revision": revision,
            "source": "default_deny",
        }
        for key, value in expected.items():
            if payload.get(key) != value:
                raise CutoverError(
                    "Runtime policy is not the exact initial seed; run explicit backout"
                )

    def _assert_public_unreachable(self, assertion_path: Path, workspace_id: str) -> None:
        status_raw = self.executor.run(
            [str(self.launcher), "status", "--json"],
            timeout_seconds=15.0,
        )
        try:
            status = json.loads(status_raw)
        except json.JSONDecodeError as error:
            raise CutoverError("Canonical launcher status is malformed") from error
        if (
            status.get("running") is not False
            or status.get("maintenance") is not True
        ):
            raise CutoverError("Canonical launcher did not prove a closed maintenance state")
        token = assertion_path.read_text(encoding="utf-8").strip()
        try:
            response = self.http.request(
                "GET",
                f"{self.public_origin}/workspaces/{workspace_id}",
                headers={"Cookie": f"CF_Authorization={token}"},
                timeout_seconds=5.0,
            )
        except CutoverError as error:
            raise CutoverError("Public origin closure proof was inconclusive") from error
        if not 500 <= response.status <= 599:
            raise CutoverError("Public edge did not expose a closed-origin 5xx response")

    def _recreate_frontend(self) -> None:
        self.executor.run(
            self.origin.compose_command(
                "up",
                "-d",
                "--force-recreate",
                "--no-deps",
                "frontend",
            ),
            timeout_seconds=180.0,
        )

    def _assert_health(self, expected: Mapping[str, Any], revision: int) -> None:
        payload = self.http.get_json(
            HEALTH_URL, timeout_seconds=20.0, max_response_bytes=32_768
        )
        gateway = payload.get("gateway")
        if not isinstance(gateway, Mapping):
            raise CutoverError("Gateway health projection is missing")
        nullable = expected.get("access_issuer") is None
        expected_values = {
            "startup_config_get_count": 1,
            "remote_access_state": expected.get("remote_access_state"),
            "auth_config_fingerprint": None if nullable else EXPECTED_FINGERPRINT,
            "auth_config_source": "runtime_policy",
            "runtime_policy_revision": revision,
            "remote_listener_ready": not nullable,
            "jwt_signature_verification_required": True,
            "jwt_issuer_ready": not nullable,
            "jwt_audience_ready": not nullable,
            "effective_policy_cache_entries": 0,
            "capability_support_cache_entries": 0,
            "upstream_effective_policy_calls": 0,
            "upstream_capability_support_calls": 0,
        }
        for key, value in expected_values.items():
            if gateway.get(key) != value:
                raise CutoverError(f"Gateway startup health mismatch: {key}")

    def _prewarm_backend(self, workspace_id: str) -> None:
        self.http.get_json(
            f"http://localhost:8200{POLICY_PATH_PREFIX}/{workspace_id}/policy",
            timeout_seconds=20.0,
            max_response_bytes=32_768,
        )
        for capability in EXPECTED_TARGET_CAPABILITIES:
            self.http.get_json(
                "http://localhost:8200/api/v1/capability-packs/installed-capabilities/"
                f"{capability}/mobile-workbench-gateway-support",
                timeout_seconds=20.0,
                max_response_bytes=4_096,
            )

    def transition(
        self,
        body: Mapping[str, Any],
        *,
        assertion_path: Path,
        workspace_id: str,
        reopen: bool,
    ) -> dict[str, Any]:
        """Stop, PUT/read back, recreate once, verify empty cache, then optionally reopen."""

        self.close_and_prove(assertion_path, workspace_id)
        expected_revision = body.get("expected_revision")
        if type(expected_revision) is not int:
            raise CutoverError("Transition expected_revision is invalid")
        next_revision = expected_revision + 1
        put_response = self.http.put_json(
            RUNTIME_POLICY_URL,
            body,
            timeout_seconds=10.0,
            max_response_bytes=32_768,
        )
        if put_response.get("revision") != next_revision:
            raise CutoverError("Runtime policy PUT revision did not advance by exactly one")
        readback = self.get_runtime_policy()
        self.assert_policy_readback(readback, body)
        if readback.get("revision") != next_revision:
            raise CutoverError("Runtime policy GET revision does not match the PUT revision")
        self._recreate_frontend()
        self._assert_health(body, next_revision)
        if body.get("access_issuer") is not None:
            self._prewarm_backend(workspace_id)
        if reopen:
            self.reopen_transport()
        return readback

    def _assert_principal_response(
        self,
        response: HttpResponse,
        *,
        allowed: bool,
        expected_reason: str | None,
        upgrade: bool,
    ) -> None:
        assert_principal_response(
            response,
            allowed=allowed,
            expected_reason=expected_reason,
            upgrade=upgrade,
        )

    def _principal_request(
        self,
        assertion_path: Path,
        workspace_id: str,
        *,
        upgrade: bool,
        denied_capability: bool = False,
    ) -> HttpResponse:
        return principal_request(
            self,
            assertion_path,
            workspace_id,
            upgrade=upgrade,
            denied_capability=denied_capability,
        )

    def _public_path_request(
        self,
        assertion_path: Path,
        path: str,
        *,
        workspace_id: str,
        upgrade: bool = False,
    ) -> HttpResponse:
        return public_path_request(
            self,
            assertion_path,
            path,
            workspace_id=workspace_id,
            upgrade=upgrade,
        )

    def verify_enrollment_assertions(self, inputs: SecureInputs, workspace_id: str) -> None:
        verify_signed_enrollment_assertions(self, inputs, workspace_id)

    @classmethod
    def validate_enrollment_candidates(
        cls,
        audit: Mapping[str, Any],
        *,
        inputs: SecureInputs,
        workspace_id: str,
        started_at: Any,
    ) -> None:
        validate_enrollment_candidate_events(
            audit,
            inputs=inputs,
            workspace_id=workspace_id,
            started_at=started_at,
        )

    def verify_effective_policies(
        self,
        inputs: SecureInputs,
        *,
        target_workspace_id: str,
        inheritance_workspace_id: str,
        state: str,
        revision: int,
    ) -> None:
        verify_effective_policy_snapshots(
            self,
            inputs,
            target_workspace_id=target_workspace_id,
            inheritance_workspace_id=inheritance_workspace_id,
            state=state,
            revision=revision,
        )

    def verify_pending_coherence(
        self,
        runtime_readback: Mapping[str, Any],
        workspace_id: str,
    ) -> None:
        verify_pending_coherence(
            self,
            runtime_readback=runtime_readback,
            workspace_id=workspace_id,
        )

    def verify_public_matrix(self, inputs: SecureInputs, workspace_id: str) -> None:
        verify_public_acceptance_matrix(self, inputs, workspace_id)

    def verify_gateway_latency(self, inputs: SecureInputs, workspace_id: str) -> dict[str, Any]:
        return verify_actual_gateway_cache_latency(self, inputs, workspace_id)
