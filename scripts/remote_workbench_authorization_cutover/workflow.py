"""Single cutover and backout workflows for Remote Workbench authorization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .claim_gate import RunnerClaimGate
from .edge import AccessEdgeGate
from .enrollment_checkpoint import (
    EnrollmentContinuation,
    checkpoint_path,
    load_checkpoint,
    write_checkpoint,
)
from .io import (
    CutoverError,
    assert_private_directory,
    assert_private_file,
    write_private_json,
)
from .install_state import AcceptedInstallError, ActiveInstallAttemptError
from .policy_receipt import current_policy_requires_rollback, record_policy_intent
from .release import ReleaseGate
from .remote_ingress import RemoteIngressGate
from .resources import RedisResourceSampler
from .runtime import RuntimeGate
from .secure_inputs import (
    EXPECTED_INHERITANCE_WORKSPACE_ID,
    EXPECTED_TARGET_WORKSPACE_ID,
    SecureInputs,
    load_secure_inputs,
    require_access_token_remaining,
)


class CutoverWorkflow:
    """Orchestrate the only approved maintenance-bound authorization transition."""

    def __init__(
        self,
        *,
        edge: AccessEdgeGate,
        ingress: RemoteIngressGate,
        release: ReleaseGate,
        runtime: RuntimeGate,
        resources: RedisResourceSampler,
        claims: RunnerClaimGate,
    ) -> None:
        self.edge = edge
        self.ingress = ingress
        self.release = release
        self.runtime = runtime
        self.resources = resources
        self.claims = claims
        self.continuation = EnrollmentContinuation(
            edge=edge,
            ingress=ingress,
            release=release,
            runtime=runtime,
            claims=claims,
        )

    @staticmethod
    def _validate_workspace_ids(target: str, inheritance: str) -> None:
        if target != EXPECTED_TARGET_WORKSPACE_ID:
            raise CutoverError("Target workspace does not match the locked rollout")
        if inheritance != EXPECTED_INHERITANCE_WORKSPACE_ID:
            raise CutoverError("Inheritance workspace does not match the locked rollout")

    @staticmethod
    def _pending_enrollment_body(inputs: SecureInputs, revision: int) -> dict[str, Any]:
        body = dict(inputs.policy)
        body["expected_revision"] = revision
        body["remote_access_state"] = "enrollment_only"
        body["local_core_super_admins"] = [
            {
                "email": email,
                "subject": "pending_identity_resolution",
                "status": "pending",
            }
            for email in ("hans@anafter.co", "pproo.reader@gmail.com")
        ]
        return body

    @staticmethod
    def _active_enrollment_body(inputs: SecureInputs, revision: int) -> dict[str, Any]:
        body = dict(inputs.policy)
        body["expected_revision"] = revision
        body["remote_access_state"] = "enrollment_only"
        return body

    @staticmethod
    def _enforced_body(inputs: SecureInputs, revision: int) -> dict[str, Any]:
        body = dict(inputs.policy)
        body["expected_revision"] = revision
        body["remote_access_state"] = "enforced"
        return body

    def _rollback_policy(
        self,
        *,
        original: dict[str, Any],
        assertion_path: Path,
        target_workspace_id: str,
        directory: Path,
    ) -> None:
        current = self.runtime.get_runtime_policy()
        revision = current.get("revision")
        if type(revision) is not int:
            raise CutoverError("Cannot back out without the current runtime revision")
        if not current_policy_requires_rollback(
            directory,
            original=original,
            current=current,
        ):
            return
        snapshot = dict(original)
        snapshot["remote_access_state"] = "enrollment_only"
        body = self.runtime.policy_body(snapshot, revision)
        self.runtime.transition(
            body,
            assertion_path=assertion_path,
            workspace_id=target_workspace_id,
            reopen=False,
        )

    def _restore_preflight(self, directory: Path) -> dict[str, Any] | None:
        receipt = directory / "restore-attempt.json"
        job = (
            self.release.require_restore_attempt_terminal(directory)
            if receipt.exists()
            else None
        )
        self.release.require_no_active_install_jobs()
        self.release.verify_database_pools()
        return job

    def _finish_restore(
        self,
        directory: Path,
        prior_job: dict[str, Any] | None,
    ) -> None:
        if prior_job is not None and prior_job.get("state") == "succeeded":
            self.release.verify_restore_job(directory, prior_job)
            return
        self.release.restore_known_good(directory)

    def _mandatory_backout(
        self,
        *,
        inputs: SecureInputs,
        target_workspace_id: str,
        original: dict[str, Any] | None,
        policy_intent_recorded: bool,
        pack_mutation_started: bool,
        pack_restore_allowed: bool,
        public_mutation_started: bool,
        claims_paused: bool,
    ) -> None:
        errors: list[Exception] = []
        preserve_claim_pause = False
        if public_mutation_started:
            try:
                self.runtime.safe_close("authorization_cutover_failed")
            except Exception as error:  # noqa: BLE001 - every recovery step must run
                errors.append(error)
        if policy_intent_recorded and original is not None:
            try:
                require_access_token_remaining(inputs)
                self._rollback_policy(
                    original=original,
                    assertion_path=inputs.jwt_paths["hans"],
                    target_workspace_id=target_workspace_id,
                    directory=inputs.directory,
                )
            except Exception as error:  # noqa: BLE001
                errors.append(error)
        if pack_mutation_started:
            if not pack_restore_allowed:
                errors.append(
                    CutoverError(
                        "Accepted install is active or indeterminate; restore remains blocked"
                    )
                )
            else:
                try:
                    restore_before = self.claims.pause_and_drain(
                        inputs.directory,
                        "phase06-backout",
                    )
                    claims_paused = True
                    self.release.require_install_attempt_terminal(inputs.directory)
                    prior_restore = self._restore_preflight(inputs.directory)
                    self._finish_restore(inputs.directory, prior_restore)
                    self.claims.verify_after(
                        restore_before,
                        inputs.directory,
                        "phase06-backout",
                    )
                except ActiveInstallAttemptError as error:
                    preserve_claim_pause = True
                    errors.append(error)
                except AcceptedInstallError as error:
                    preserve_claim_pause = not error.terminal
                    errors.append(error)
                except Exception as error:  # noqa: BLE001
                    errors.append(error)
        if claims_paused and not preserve_claim_pause:
            try:
                self.claims.resume()
            except Exception as error:  # noqa: BLE001
                errors.append(error)
        if errors:
            raise CutoverError("Mandatory cutover backout did not close every mutation") from errors[0]

    def cutover(
        self,
        *,
        secure_input_dir: Path,
        target_workspace_id: str,
        inheritance_workspace_id: str,
    ) -> dict[str, Any]:
        """Run the one backup/install/enrollment/enforcement transition path."""

        self._validate_workspace_ids(target_workspace_id, inheritance_workspace_id)
        checkpoint_present = (
            checkpoint_path(secure_input_dir).exists()
            or checkpoint_path(secure_input_dir).is_symlink()
        )
        if checkpoint_present:
            self.runtime.safe_close("authorization_resume_preflight")
        inputs = load_secure_inputs(secure_input_dir)
        checkpoint = load_checkpoint(inputs.directory)
        if checkpoint is not None:
            try:
                return self.continuation.resume(
                    inputs=inputs,
                    checkpoint=checkpoint,
                    target_workspace_id=target_workspace_id,
                    inheritance_workspace_id=inheritance_workspace_id,
                )
            except Exception:
                self.runtime.safe_close("authorization_resume_failed")
                raise
        original: dict[str, Any] | None = None
        policy_intent_recorded = False
        pack_mutation_started = False
        pack_restore_allowed = False
        public_mutation_started = False
        claims_paused = False
        try:
            self.edge.verify()
            self.ingress.capture_prechange(inputs)
            self.release.require_no_active_install_jobs()
            self.release.verify_workspace_rows(target_workspace_id, inheritance_workspace_id)
            self.runtime.verify_workspace_records(target_workspace_id, inheritance_workspace_id)
            self.release.verify_database_pools(inputs.directory, "preflight")

            claims_paused = True
            infra_before = self.claims.pause_and_drain(inputs.directory, "06a-infra")
            backup_dir = self.release.verify_or_create_backup()

            public_mutation_started = True
            self.runtime.activate_supervisor()
            self.runtime.verify_supervisor()
            origin = self.runtime.inspect_origin(inputs.directory, target_workspace_id)
            require_access_token_remaining(inputs)
            self.runtime.close_and_prove(
                inputs.jwt_paths["hans"],
                target_workspace_id,
            )
            if origin.get("drift"):
                self.runtime.reconcile_origin(
                    origin["drift"],
                    secure_dir=inputs.directory,
                    workspace_id=target_workspace_id,
                )
            self.release.verify_database_pools(inputs.directory, "post-origin")
            self.release.require_no_active_install_jobs()
            self.release.capture_known_good(inputs.directory)
            workspace_before = self.runtime.get_effective_policy(target_workspace_id)
            write_private_json(
                inputs.directory / "workspace-policy-before.json",
                workspace_before,
            )
            self.claims.verify_after(infra_before, inputs.directory, "06a-infra")
            self.claims.resume()
            claims_paused = False

            archive = self.release.package_current()
            try:
                install_job = self.release.install_current(archive, inputs.directory)
            except AcceptedInstallError as error:
                pack_mutation_started = True
                pack_restore_allowed = error.terminal
                raise
            pack_mutation_started = True
            pack_restore_allowed = True
            self.release.require_no_active_install_jobs()
            self.release.verify_database_pools(inputs.directory, "post-install")
            self.release.verify_effective_policy_query_plan(target_workspace_id)

            original = self.runtime.get_runtime_policy()
            self.runtime.assert_initial_seed(
                original,
                inputs.policy["expected_revision"],
            )
            write_private_json(inputs.directory / "runtime-policy-before.json", original)
            write_private_json(
                inputs.directory / "workspace-policy-post-migration.json",
                self.runtime.get_effective_policy(target_workspace_id),
            )
            revision = original["revision"]

            require_access_token_remaining(inputs)
            pending_body = self._pending_enrollment_body(inputs, revision)
            record_policy_intent(inputs.directory, original=original, body=pending_body)
            policy_intent_recorded = True
            pending_readback = self.runtime.transition(
                pending_body,
                assertion_path=inputs.jwt_paths["hans"],
                workspace_id=target_workspace_id,
                reopen=False,
            )
            self.runtime.verify_pending_coherence(pending_readback, target_workspace_id)
            ingress_lock = self.ingress.apply_exact(inputs)
            self.runtime.reopen_transport()
            require_access_token_remaining(inputs)
            self.runtime.verify_enrollment_assertions(inputs, target_workspace_id)

            pending_revision = pending_readback["revision"]
            require_access_token_remaining(inputs)
            enrollment_body = self._active_enrollment_body(inputs, pending_revision)
            record_policy_intent(inputs.directory, original=original, body=enrollment_body)
            enrollment_readback = self.runtime.transition(
                enrollment_body,
                assertion_path=inputs.jwt_paths["hans"],
                workspace_id=target_workspace_id,
                reopen=True,
            )
            current_revision = enrollment_readback["revision"]
            self.runtime.verify_effective_policies(
                inputs,
                target_workspace_id=target_workspace_id,
                inheritance_workspace_id=inheritance_workspace_id,
                state="enrollment_only",
                revision=current_revision,
            )
            if "outsider" not in inputs.jwt_paths:
                self.runtime.close_and_prove(
                    inputs.jwt_paths["hans"],
                    target_workspace_id,
                )
                checkpoint = write_checkpoint(
                    inputs.directory,
                    target_workspace_id=target_workspace_id,
                    inheritance_workspace_id=inheritance_workspace_id,
                    runtime=enrollment_readback,
                    install=install_job,
                    ingress=ingress_lock,
                    source=self.release.source_identity(),
                    backup_dir=backup_dir,
                )
                return {
                    "status": "pending_outsider",
                    "runtime_policy_revision": current_revision,
                    "install_id": checkpoint["install"]["install_id"],
                    "backup_dir": checkpoint["backup_dir"],
                    "maintenance": True,
                    "tunnel": "closed",
                }
            return self.continuation.finish(
                inputs=inputs,
                target_workspace_id=target_workspace_id,
                inheritance_workspace_id=inheritance_workspace_id,
                current_revision=current_revision,
                original=original,
                install_id=install_job["install_id"],
                backup_dir=str(backup_dir),
            )
        except Exception as failure:
            try:
                self._mandatory_backout(
                    inputs=inputs,
                    target_workspace_id=target_workspace_id,
                    original=original,
                    policy_intent_recorded=policy_intent_recorded,
                    pack_mutation_started=pack_mutation_started,
                    pack_restore_allowed=pack_restore_allowed,
                    public_mutation_started=public_mutation_started,
                    claims_paused=claims_paused,
                )
            except Exception as backout_error:
                raise backout_error from failure
            raise

    def backout(
        self,
        *,
        secure_input_dir: Path,
        target_workspace_id: str,
        inheritance_workspace_id: str,
    ) -> dict[str, Any]:
        """Restore saved policy and pack while public access remains closed."""

        self._validate_workspace_ids(target_workspace_id, inheritance_workspace_id)
        inputs = load_secure_inputs(secure_input_dir)
        directory = inputs.directory
        assert_private_directory(directory)
        snapshot_path = directory / "runtime-policy-before.json"
        assert_private_file(snapshot_path, max_bytes=32_768)
        try:
            original = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise CutoverError("Saved runtime policy snapshot is malformed") from error
        if not isinstance(original, dict):
            raise CutoverError("Saved runtime policy snapshot must be an object")
        try:
            before = self.claims.pause_and_drain(directory, "phase06-backout")
            self.runtime.safe_close("authorization_backout")
            self.release.require_install_attempt_terminal(directory)
            prior_restore = self._restore_preflight(directory)
            self.runtime.recover_origin(directory)
            require_access_token_remaining(inputs)
            self._rollback_policy(
                original=original,
                assertion_path=inputs.jwt_paths["hans"],
                target_workspace_id=target_workspace_id,
                directory=directory,
            )
            self._finish_restore(directory, prior_restore)
            self.claims.verify_after(before, directory, "phase06-backout")
        finally:
            active_restore = directory.joinpath("restore-attempt.json").exists()
            keep_paused = False
            if active_restore:
                try:
                    self.release.require_restore_attempt_terminal(directory)
                except ActiveInstallAttemptError:
                    keep_paused = True
            if not keep_paused:
                self.claims.resume()
        return {
            "status": "succeeded",
            "remote_access_state": "enrollment_only",
            "maintenance": True,
            "tunnel": "closed",
            "pack": "known_good_restored",
        }
