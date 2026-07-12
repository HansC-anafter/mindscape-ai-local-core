"""Single failure-closed recovery seam for cutover and explicit backout."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .io import CutoverError
from .policy_receipt import current_policy_requires_rollback
from .resources import ResourceSnapshot
from .secure_inputs import SecureInputs, require_access_token_remaining


class BackoutClosure:
    """Recover origin, policy, pack, pools, and resources before claim resume."""

    def __init__(self, *, release: Any, runtime: Any, claims: Any) -> None:
        self.release = release
        self.runtime = runtime
        self.claims = claims

    def _rollback_policy(
        self,
        *,
        inputs: SecureInputs,
        target_workspace_id: str,
        original: dict[str, Any],
    ) -> None:
        current = self.runtime.get_runtime_policy()
        revision = current.get("revision")
        if type(revision) is not int:
            raise CutoverError("Cannot back out without the current runtime revision")
        if not current_policy_requires_rollback(
            inputs.directory,
            original=original,
            current=current,
        ):
            return
        snapshot = dict(original)
        snapshot["remote_access_state"] = "enrollment_only"
        body = self.runtime.policy_body(snapshot, revision)
        self.runtime.transition(
            body,
            assertion_path=inputs.jwt_paths["hans"],
            workspace_id=target_workspace_id,
            reopen=False,
        )

    def _restore_pack(self, directory: Path) -> None:
        self.release.require_install_attempt_terminal(directory)
        receipt = directory / "restore-attempt.json"
        prior_job = (
            self.release.require_restore_attempt_terminal(directory)
            if receipt.exists()
            else None
        )
        self.release.require_no_active_install_jobs()
        if prior_job is not None and prior_job.get("state") == "succeeded":
            self.release.verify_restore_job(directory, prior_job)
            return
        self.release.restore_known_good(directory)

    def close(
        self,
        *,
        inputs: SecureInputs,
        target_workspace_id: str,
        original: dict[str, Any] | None,
        rollback_policy: bool,
        restore_pack: bool,
        pack_restore_allowed: bool,
        claims_paused: bool,
        resource_before: ResourceSnapshot | None,
        resource_window: str | None,
        evidence_label: str,
        close_reason: str,
    ) -> None:
        """Run the only terminal closure sequence and resume claims last."""

        before = resource_before
        window = resource_window
        if not claims_paused:
            before = self.claims.pause_and_drain(
                inputs.directory,
                "phase06-backout",
            )
            window = "phase06-backout"
        if before is None or window is None:
            raise CutoverError("Backout closure lacks the paused resource baseline")

        self.runtime.safe_close(close_reason)
        self.runtime.recover_origin(inputs.directory)
        if rollback_policy:
            if original is None:
                raise CutoverError("Backout closure lacks the original runtime policy")
            require_access_token_remaining(inputs)
            self._rollback_policy(
                inputs=inputs,
                target_workspace_id=target_workspace_id,
                original=original,
            )
        if restore_pack:
            if not pack_restore_allowed:
                raise CutoverError(
                    "Accepted install is active or indeterminate; restore remains blocked"
                )
            self._restore_pack(inputs.directory)

        self.release.require_no_active_install_jobs()
        self.release.verify_database_pools(inputs.directory, evidence_label)
        self.claims.verify_after(before, inputs.directory, window)
        self.claims.resume()
