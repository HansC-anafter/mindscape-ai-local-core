"""Coordinator for retained candidate filesystem and migration state."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from .filesystem_saga import PreparedCapabilityTree
from .migration_equivalence import equivalent_migration_contracts
from .state_machine import InstallCommitState, require_transition


class InstallCommitCoordinator:
    """Own the one allowed install state path for a durable install id."""

    def __init__(
        self,
        *,
        install_id: str,
        capability_code: str,
        runtime_installer: Any,
    ):
        self.install_id = str(install_id)
        self.capability_code = str(capability_code)
        self.runtime_installer = runtime_installer
        self.state = InstallCommitState.ACCEPTED
        self.prepared: Optional[PreparedCapabilityTree] = None
        self.truth_committed = False
        self.cleanup_error: Optional[str] = None

    def prepare(
        self,
        *,
        cap_dir: Path,
        manifest: dict[str, Any],
        result: Any,
        temp_dir: Optional[Path],
    ) -> PreparedCapabilityTree:
        self.prepared = self.runtime_installer.prepare_staged_tree(
            cap_dir,
            self.capability_code,
            manifest,
            result,
            temp_dir,
            install_id=self.install_id,
        )
        self.state = require_transition(self.state, InstallCommitState.PREPARED)
        return self.prepared

    def execute_candidate_migrations(self, result: Any) -> None:
        prepared = self._require_prepared()
        if self.state is not InstallCommitState.PREPARED:
            raise RuntimeError("candidate_migration_requires_prepared_state")
        equivalent, candidate_digest, installed_digest = (
            equivalent_migration_contracts(
                prepared.staging_cap_dir,
                prepared.target_cap_dir,
            )
        )
        if equivalent:
            if getattr(result, "migration_status", None) is None:
                result.migration_status = {}
            result.migration_status[self.capability_code] = "skipped"
            if getattr(result, "migration_receipts", None) is None:
                result.migration_receipts = {}
            result.migration_receipts[self.capability_code] = {
                "mode": "identical_installed_migration_contract",
                "candidate_digest": candidate_digest.sha256,
                "installed_digest": installed_digest.sha256,
                "file_count": candidate_digest.file_count,
                "schema_mutation_required": False,
                "database_operations": 0,
            }
            result.add_warning(
                "Skipped database migration execution because the candidate and "
                "installed migration source contracts are byte-identical."
            )
            self.state = require_transition(
                self.state,
                InstallCommitState.MIGRATION_APPLIED,
            )
            return
        original_capabilities_dir = self.runtime_installer.capabilities_dir
        self.runtime_installer.capabilities_dir = prepared.staging_cap_dir.parent
        try:
            self.runtime_installer.execute_migrations(self.capability_code, result)
        finally:
            self.runtime_installer.capabilities_dir = original_capabilities_dir
        migration_state = (getattr(result, "migration_status", None) or {}).get(
            self.capability_code
        )
        if migration_state not in {None, "applied", "skipped"}:
            raise RuntimeError(
                f"candidate_migration_not_applied:{migration_state or 'unknown'}"
            )
        self.state = require_transition(
            self.state,
            InstallCommitState.MIGRATION_APPLIED,
        )

    def publish(self) -> PreparedCapabilityTree:
        if self.state is not InstallCommitState.MIGRATION_APPLIED:
            raise RuntimeError("candidate_publish_requires_migration_applied")
        prepared = self.runtime_installer.publish_candidate_retaining_previous(
            self._require_prepared()
        )
        self.state = require_transition(
            self.state,
            InstallCommitState.CANDIDATE_PUBLISHED,
        )
        return prepared

    def mark_activated(self) -> None:
        self.state = require_transition(
            self.state,
            InstallCommitState.CANDIDATE_ACTIVATED,
        )

    def mark_committed(self) -> None:
        # Set the irreversible boundary first. Once the DB transaction returns,
        # no later in-process failure may restore the previous runtime tree.
        self.truth_committed = True
        self.state = require_transition(self.state, InstallCommitState.COMMITTED)

    def mark_cleanup_pending(self, error: Exception) -> None:
        self.cleanup_error = f"{type(error).__name__}:{str(error)[:160]}"
        if self.state is InstallCommitState.COMMITTED:
            self.state = require_transition(
                self.state,
                InstallCommitState.COMMITTED_CLEANUP_PENDING,
            )

    def finalize(self) -> None:
        if self.state is not InstallCommitState.COMMITTED:
            raise RuntimeError("candidate_finalize_requires_committed_state")
        self.runtime_installer.finalize_publish(self._require_prepared())
        self.state = require_transition(self.state, InstallCommitState.SUCCEEDED)

    def restore_previous(self) -> None:
        if self.truth_committed or self.state in {
            InstallCommitState.COMMITTED,
            InstallCommitState.COMMITTED_CLEANUP_PENDING,
            InstallCommitState.SUCCEEDED,
        }:
            raise RuntimeError("previous_restore_forbidden_after_truth_commit")
        if self.prepared is not None:
            self.runtime_installer.restore_previous(self.prepared)
        if self.state not in {
            InstallCommitState.SUCCEEDED,
            InstallCommitState.RESTORED_PREVIOUS,
        }:
            self.state = require_transition(
                self.state,
                InstallCommitState.RESTORED_PREVIOUS,
            )

    def receipt(self) -> dict[str, Any]:
        return {
            "install_id": self.install_id,
            "capability_code": self.capability_code,
            "state": self.state.value,
            "truth_committed": self.truth_committed,
            "cleanup_error": self.cleanup_error,
            "filesystem": self.prepared.to_receipt() if self.prepared else None,
        }

    def _require_prepared(self) -> PreparedCapabilityTree:
        if self.prepared is None:
            raise RuntimeError("capability_candidate_not_prepared")
        return self.prepared
