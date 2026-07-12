"""Durable identity checkpoint between enrollment and outsider enforcement."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .io import CutoverError, assert_private_file, write_private_json
from .policy_receipt import record_policy_intent
from .secure_inputs import SecureInputs, require_access_token_remaining


CHECKPOINT_NAME = "authorization-enrollment-checkpoint.json"
_COMMIT_PATTERN = re.compile(r"^[a-f0-9]{40}$")
_INSTALL_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_RUNTIME_KEYS = {
    "id",
    "revision",
    "access_issuer",
    "access_audience",
    "auth_config_fingerprint",
    "auth_config_source",
    "remote_access_state",
    "local_core_super_admins",
    "source",
}
_INSTALL_KEYS = {
    "install_id",
    "source_kind",
    "capability_code",
    "version",
    "manifest_hash",
}
_INGRESS_KEYS = {
    "tunnel_id",
    "config_version",
    "config_sha256",
    "config_src",
    "hostname",
    "service",
    "catch_all",
}


def checkpoint_path(directory: Path) -> Path:
    return directory / CHECKPOINT_NAME


def runtime_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project the complete policy identity needed for an exact resume."""

    admins = payload.get("local_core_super_admins")
    if not isinstance(admins, list) or len(admins) != 2:
        raise CutoverError("Enrollment checkpoint runtime administrators are malformed")
    normalized_admins: list[dict[str, str]] = []
    for admin in admins:
        if not isinstance(admin, Mapping):
            raise CutoverError("Enrollment checkpoint administrator is malformed")
        normalized_admins.append(
            {
                "email": str(admin.get("email") or "").strip().lower(),
                "subject": str(admin.get("subject") or "").strip(),
                "status": str(admin.get("status") or "").strip(),
            }
        )
    normalized_admins.sort(key=lambda item: (item["email"], item["subject"]))
    projected = {key: payload.get(key) for key in _RUNTIME_KEYS}
    projected["local_core_super_admins"] = normalized_admins
    if (
        projected["id"] != "remote-workbench-runtime"
        or type(projected["revision"]) is not int
        or projected["revision"] < 0
        or projected["remote_access_state"] != "enrollment_only"
        or projected["auth_config_source"] != "runtime_policy"
        or projected["source"] != "persisted_policy"
        or any(
            not item["email"]
            or not item["subject"]
            or item["status"] != "active"
            for item in normalized_admins
        )
    ):
        raise CutoverError("Enrollment checkpoint runtime identity is invalid")
    return projected


def install_identity(job: Mapping[str, Any]) -> dict[str, Any]:
    """Project the accepted install and activated manifest identity."""

    result = job.get("result_payload")
    activation = result.get("activation") if isinstance(result, Mapping) else None
    projected = {
        "install_id": job.get("install_id"),
        "source_kind": job.get("source_kind"),
        "capability_code": result.get("capability_code")
        if isinstance(result, Mapping)
        else None,
        "version": result.get("version") if isinstance(result, Mapping) else None,
        "manifest_hash": activation.get("manifest_hash")
        if isinstance(activation, Mapping)
        else None,
    }
    if (
        not _INSTALL_ID_PATTERN.fullmatch(str(projected["install_id"] or ""))
        or projected["source_kind"] != "file_upload"
        or projected["capability_code"] != "mindscape_cloud_integration"
        or not isinstance(projected["version"], str)
        or not projected["version"]
        or not _HASH_PATTERN.fullmatch(str(projected["manifest_hash"] or ""))
    ):
        raise CutoverError("Enrollment checkpoint install identity is invalid")
    return projected


def ingress_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Project the exact remotely-managed ingress configuration identity."""

    projected = {key: payload.get(key) for key in _INGRESS_KEYS}
    if (
        not isinstance(projected["tunnel_id"], str)
        or not projected["tunnel_id"]
        or type(projected["config_version"]) is not int
        or projected["config_version"] < 0
        or not _HASH_PATTERN.fullmatch(str(projected["config_sha256"] or ""))
        or projected["config_src"] != "cloudflare"
        or any(
            not isinstance(projected[key], str) or not projected[key]
            for key in ("hostname", "service", "catch_all")
        )
    ):
        raise CutoverError("Enrollment checkpoint ingress identity is invalid")
    return projected


def source_identity(payload: Mapping[str, Any]) -> dict[str, str]:
    """Validate exact Local and Cloud commit identities."""

    if set(payload) != {"local_commit", "cloud_commit"}:
        raise CutoverError("Enrollment checkpoint source identity schema is invalid")
    result = {
        "local_commit": str(payload.get("local_commit") or ""),
        "cloud_commit": str(payload.get("cloud_commit") or ""),
    }
    if any(not _COMMIT_PATTERN.fullmatch(value) for value in result.values()):
        raise CutoverError("Enrollment checkpoint source commit is invalid")
    return result


def write_checkpoint(
    directory: Path,
    *,
    target_workspace_id: str,
    inheritance_workspace_id: str,
    runtime: Mapping[str, Any],
    install: Mapping[str, Any],
    ingress: Mapping[str, Any],
    source: Mapping[str, Any],
    backup_dir: Path,
) -> dict[str, Any]:
    """Atomically persist only non-secret resume identities as one 0600 file."""

    resolved_backup = backup_dir.resolve()
    if not resolved_backup.is_absolute():
        raise CutoverError("Enrollment checkpoint backup path is invalid")
    payload = {
        "schema_version": 1,
        "target_workspace_id": target_workspace_id,
        "inheritance_workspace_id": inheritance_workspace_id,
        "runtime": runtime_identity(runtime),
        "install": install_identity(install),
        "ingress": ingress_identity(ingress),
        "source": source_identity(source),
        "backup_dir": str(resolved_backup),
    }
    write_private_json(checkpoint_path(directory), payload)
    return payload


def load_checkpoint(directory: Path) -> dict[str, Any] | None:
    """Load the one exact checkpoint, returning None only when it is absent."""

    path = checkpoint_path(directory)
    if not path.exists() and not path.is_symlink():
        return None
    assert_private_file(path, max_bytes=65_536)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CutoverError("Enrollment checkpoint is malformed") from error
    expected_keys = {
        "schema_version",
        "target_workspace_id",
        "inheritance_workspace_id",
        "runtime",
        "install",
        "ingress",
        "source",
        "backup_dir",
    }
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise CutoverError("Enrollment checkpoint schema is invalid")
    if payload.get("schema_version") != 1:
        raise CutoverError("Enrollment checkpoint schema version is invalid")
    runtime = payload.get("runtime")
    install = payload.get("install")
    ingress = payload.get("ingress")
    source = payload.get("source")
    if (
        not isinstance(runtime, Mapping)
        or set(runtime) != _RUNTIME_KEYS
        or not isinstance(install, Mapping)
        or set(install) != _INSTALL_KEYS
        or not isinstance(ingress, Mapping)
        or set(ingress) != _INGRESS_KEYS
        or not isinstance(source, Mapping)
    ):
        raise CutoverError("Enrollment checkpoint identity projection is invalid")
    payload["runtime"] = runtime_identity(runtime)
    payload["install"] = install_identity(
        {
            "install_id": install.get("install_id"),
            "source_kind": install.get("source_kind"),
            "result_payload": {
                "capability_code": install.get("capability_code"),
                "version": install.get("version"),
                "activation": {"manifest_hash": install.get("manifest_hash")},
            },
        }
    )
    payload["ingress"] = ingress_identity(ingress)
    payload["source"] = source_identity(source)
    backup_dir = payload.get("backup_dir")
    if not isinstance(backup_dir, str) or not Path(backup_dir).is_absolute():
        raise CutoverError("Enrollment checkpoint backup path is invalid")
    return payload


class EnrollmentContinuation:
    """Resume and enforce from the one durable enrollment checkpoint path."""

    def __init__(
        self,
        *,
        edge: Any,
        ingress: Any,
        release: Any,
        runtime: Any,
        claims: Any,
    ) -> None:
        self.edge = edge
        self.ingress = ingress
        self.release = release
        self.runtime = runtime
        self.claims = claims
        self.claims_paused = False
        self.resource_before: Any | None = None
        self.resource_window: str | None = None

    @staticmethod
    def _load_original_policy(directory: Path) -> dict[str, Any]:
        path = directory / "runtime-policy-before.json"
        assert_private_file(path, max_bytes=32_768)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CutoverError("Saved initial runtime policy is malformed") from error
        if not isinstance(payload, dict) or type(payload.get("revision")) is not int:
            raise CutoverError("Saved initial runtime policy identity is invalid")
        return payload

    @staticmethod
    def _verify_outsider_zero_grant(
        inputs: SecureInputs,
        *effective_policies: dict[str, Any],
    ) -> None:
        outsider = inputs.jwt_claims.get("outsider")
        if outsider is None:
            raise CutoverError("Outsider assertion is required before enforcement")
        outsider_email = str(outsider.get("email") or "").strip().lower()
        outsider_subject = str(outsider.get("sub") or "").strip()
        for payload in effective_policies:
            principals = payload.get("effective_principals")
            admins = payload.get("local_core_super_admins")
            if not isinstance(principals, list) or not isinstance(admins, list):
                raise CutoverError("Effective policy grant projection is malformed")
            for row in [*principals, *admins]:
                if not isinstance(row, dict):
                    raise CutoverError("Effective policy grant principal is malformed")
                if (
                    str(row.get("email") or "").strip().lower() == outsider_email
                    or str(row.get("subject") or "").strip() == outsider_subject
                ):
                    raise CutoverError("Outsider unexpectedly has an effective grant")

    @staticmethod
    def _enforced_body(inputs: SecureInputs, revision: int) -> dict[str, Any]:
        body = dict(inputs.policy)
        body["expected_revision"] = revision
        body["remote_access_state"] = "enforced"
        return body

    def finish(
        self,
        *,
        inputs: SecureInputs,
        target_workspace_id: str,
        inheritance_workspace_id: str,
        current_revision: int,
        original: dict[str, Any],
        install_id: str,
        backup_dir: str,
    ) -> dict[str, Any]:
        """Run the one pre-enforcement resource window and public acceptance path."""

        self.claims_paused = True
        authorization_before = self.claims.pause_and_drain(
            inputs.directory,
            "phase06-authorization",
        )
        self.resource_before = authorization_before
        self.resource_window = "phase06-authorization"
        try:
            self.release.require_no_active_install_jobs()
            self.release.verify_database_pools(
                inputs.directory,
                "pre-enforcement",
            )
            self.release.verify_workspace_rows(
                target_workspace_id,
                inheritance_workspace_id,
            )
            self.runtime.verify_workspace_records(
                target_workspace_id,
                inheritance_workspace_id,
            )
            self.runtime.verify_effective_policies(
                inputs,
                target_workspace_id=target_workspace_id,
                inheritance_workspace_id=inheritance_workspace_id,
                state="enrollment_only",
                revision=current_revision,
            )
            target_effective = self.runtime.get_effective_policy(target_workspace_id)
            inheritance_effective = self.runtime.get_effective_policy(
                inheritance_workspace_id
            )
            self._verify_outsider_zero_grant(
                inputs,
                target_effective,
                inheritance_effective,
            )
            require_access_token_remaining(inputs)
            enforced_body = self._enforced_body(inputs, current_revision)
            record_policy_intent(
                inputs.directory,
                original=original,
                body=enforced_body,
            )
            final_readback = self.runtime.transition(
                enforced_body,
                assertion_path=inputs.jwt_paths["hans"],
                workspace_id=target_workspace_id,
                reopen=True,
            )
            final_revision = final_readback["revision"]
            self.runtime.verify_effective_policies(
                inputs,
                target_workspace_id=target_workspace_id,
                inheritance_workspace_id=inheritance_workspace_id,
                state="enforced",
                revision=final_revision,
            )
            self.release.verify_workspace_rows(
                target_workspace_id,
                inheritance_workspace_id,
            )
            self.runtime.verify_workspace_records(
                target_workspace_id,
                inheritance_workspace_id,
            )
            self.runtime.verify_gateway_latency(inputs, target_workspace_id)
            require_access_token_remaining(inputs)
            self.runtime.verify_public_matrix(inputs, target_workspace_id)
            self.claims.verify_after(
                authorization_before,
                inputs.directory,
                "phase06-authorization",
            )
            self.release.verify_database_pools(inputs.directory, "post-public")
            self.runtime.exit_maintenance()
            self.claims.resume()
            self.claims_paused = False
            self.resource_before = None
            self.resource_window = None
            return {
                "status": "succeeded",
                "runtime_policy_revision": final_revision,
                "install_id": install_id,
                "backup_dir": backup_dir,
                "resource_window": "unchanged",
                "maintenance": False,
            }
        except Exception:
            raise

    def resume(
        self,
        *,
        inputs: SecureInputs,
        checkpoint: dict[str, Any],
        target_workspace_id: str,
        inheritance_workspace_id: str,
    ) -> dict[str, Any]:
        """Validate every durable/live identity and resume without reinstalling."""

        if (
            checkpoint.get("target_workspace_id") != target_workspace_id
            or checkpoint.get("inheritance_workspace_id")
            != inheritance_workspace_id
        ):
            raise CutoverError("Enrollment checkpoint workspace identity changed")
        self.edge.verify()
        self.runtime.close_and_prove(inputs.jwt_paths["hans"], target_workspace_id)
        self.runtime.verify_supervisor()
        self.release.require_no_active_install_jobs()
        self.release.verify_database_pools(inputs.directory, "resume-preflight")
        if source_identity(self.release.source_identity()) != checkpoint["source"]:
            raise CutoverError("Enrollment checkpoint source identity changed")
        self.ingress.verify_exact(inputs, checkpoint["ingress"])
        install_job = self.release.require_install_attempt_terminal(inputs.directory)
        self.release.verify_installed_runtime(install_job)
        if install_identity(install_job) != checkpoint["install"]:
            raise CutoverError("Enrollment checkpoint install identity changed")
        current = self.runtime.get_runtime_policy()
        self.runtime.assert_policy_readback(current, inputs.policy)
        if runtime_identity(current) != checkpoint["runtime"]:
            raise CutoverError("Enrollment checkpoint runtime identity changed")
        current_revision = current["revision"]
        self.release.verify_workspace_rows(
            target_workspace_id,
            inheritance_workspace_id,
        )
        self.runtime.verify_workspace_records(
            target_workspace_id,
            inheritance_workspace_id,
        )
        self.runtime.verify_effective_policies(
            inputs,
            target_workspace_id=target_workspace_id,
            inheritance_workspace_id=inheritance_workspace_id,
            state="enrollment_only",
            revision=current_revision,
        )
        if "outsider" not in inputs.jwt_paths:
            return {
                "status": "pending_outsider",
                "runtime_policy_revision": current_revision,
                "install_id": checkpoint["install"]["install_id"],
                "backup_dir": checkpoint["backup_dir"],
                "maintenance": True,
                "tunnel": "closed",
            }
        require_access_token_remaining(inputs)
        original = self._load_original_policy(inputs.directory)
        return self.finish(
            inputs=inputs,
            target_workspace_id=target_workspace_id,
            inheritance_workspace_id=inheritance_workspace_id,
            current_revision=current_revision,
            original=original,
            install_id=checkpoint["install"]["install_id"],
            backup_dir=checkpoint["backup_dir"],
        )
