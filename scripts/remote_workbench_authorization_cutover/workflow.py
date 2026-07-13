"""Single cutover and backout workflows for Remote Workbench authorization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .backout_closure import BackoutClosure
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
from .install_state import AcceptedInstallError
from .policy_receipt import record_policy_intent
from .release import ReleaseGate
from .remote_ingress import RemoteIngressGate
from .resources import RedisResourceSampler, ResourceSnapshot
from .runtime import RuntimeGate
from .secure_inputs import (
    EXPECTED_INHERITANCE_WORKSPACE_ID,
    EXPECTED_TARGET_WORKSPACE_ID,
    SecureInputs,
    load_secure_inputs,
    require_access_token_remaining,
)
from .transition_recovery import (
    load_original_policy,
    recover_uncheckpointed_transition,
    transition_artifacts_present,
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
        self.backout_closure = BackoutClosure(
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
        resource_before: ResourceSnapshot | None,
        resource_window: str | None,
    ) -> None:
        if not any(
            (
                public_mutation_started,
                policy_intent_recorded,
                pack_mutation_started,
                claims_paused,
            )
        ):
            return
        try:
            self.backout_closure.close(
                inputs=inputs,
                target_workspace_id=target_workspace_id,
                original=original,
                rollback_policy=policy_intent_recorded,
                restore_pack=pack_mutation_started,
                pack_restore_allowed=pack_restore_allowed,
                claims_paused=claims_paused,
                resource_before=resource_before,
                resource_window=resource_window,
                evidence_label="mandatory-backout",
                close_reason="authorization_cutover_failed",
            )
        except Exception as error:
            raise CutoverError(
                "Mandatory cutover backout did not close every mutation"
            ) from error

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
        interrupted_transition = transition_artifacts_present(secure_input_dir)
        if interrupted_transition:
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
                if self.continuation.claims_paused:
                    try:
                        original = load_original_policy(inputs.directory)
                        self.backout_closure.close(
                            inputs=inputs,
                            target_workspace_id=target_workspace_id,
                            original=original,
                            rollback_policy=True,
                            restore_pack=True,
                            pack_restore_allowed=True,
                            claims_paused=True,
                            resource_before=self.continuation.resource_before,
                            resource_window=self.continuation.resource_window,
                            evidence_label="mandatory-backout",
                            close_reason="authorization_resume_failed",
                        )
                    except Exception as closure_error:
                        raise CutoverError(
                            "Mandatory checkpoint backout did not close every mutation"
                        ) from closure_error
                else:
                    self.runtime.safe_close("authorization_resume_failed")
                raise
        original = (
            recover_uncheckpointed_transition(
                inputs=inputs,
                runtime=self.runtime,
                target_workspace_id=target_workspace_id,
            )
            if interrupted_transition and not checkpoint_present
            else None
        )
        policy_intent_recorded = False
        pack_mutation_started = False
        pack_restore_allowed = False
        public_mutation_started = False
        claims_paused = False
        resource_before: ResourceSnapshot | None = None
        resource_window: str | None = None
        try:
            self.edge.verify()
            self.ingress.capture_prechange(inputs)
            self.release.require_no_active_install_jobs()
            self.release.verify_workspace_rows(target_workspace_id, inheritance_workspace_id)
            self.runtime.verify_workspace_records(target_workspace_id, inheritance_workspace_id)
            self.release.verify_database_pools(inputs.directory, "preflight")

            claims_paused = True
            infra_before = self.claims.pause_and_drain(inputs.directory, "06a-infra")
            resource_before = infra_before
            resource_window = "06a-infra"
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
            resource_before = None
            resource_window = None

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

            seed = self.runtime.get_runtime_policy()
            self.runtime.assert_initial_seed(
                seed,
                seed["revision"]
                if original is not None
                else inputs.policy["expected_revision"],
            )
            if original is None:
                original = seed
            write_private_json(inputs.directory / "runtime-policy-before.json", original)
            write_private_json(
                inputs.directory / "workspace-policy-post-migration.json",
                self.runtime.get_effective_policy(target_workspace_id),
            )
            revision = seed["revision"]

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
            if "outsider" not in inputs.jwt_paths:
                self.runtime.close_and_prove(
                    inputs.jwt_paths["hans"],
                    target_workspace_id,
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
            if self.continuation.claims_paused:
                claims_paused = True
                resource_before = self.continuation.resource_before
                resource_window = self.continuation.resource_window
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
                    resource_before=resource_before,
                    resource_window=resource_window,
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
        self.backout_closure.close(
            inputs=inputs,
            target_workspace_id=target_workspace_id,
            original=original,
            rollback_policy=True,
            restore_pack=True,
            pack_restore_allowed=True,
            claims_paused=False,
            resource_before=None,
            resource_window=None,
            evidence_label="explicit-backout",
            close_reason="authorization_backout",
        )
        return {
            "status": "succeeded",
            "remote_access_state": "enrollment_only",
            "maintenance": True,
            "tunnel": "closed",
            "pack": "known_good_restored",
        }
