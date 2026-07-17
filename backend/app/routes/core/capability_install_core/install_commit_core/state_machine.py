"""Single capability install commit state machine."""

from __future__ import annotations

from enum import Enum


class InstallCommitState(str, Enum):
    ACCEPTED = "accepted"
    PREPARED = "prepared"
    MIGRATION_APPLIED = "migration_applied"
    CANDIDATE_PUBLISHED = "candidate_published"
    CANDIDATE_ACTIVATED = "candidate_activated"
    COMMITTED = "committed"
    COMMITTED_CLEANUP_PENDING = "committed_cleanup_pending"
    SUCCEEDED = "succeeded"
    RESTORED_PREVIOUS = "restored_previous"


_ALLOWED_TRANSITIONS = {
    InstallCommitState.ACCEPTED: {
        InstallCommitState.PREPARED,
        InstallCommitState.RESTORED_PREVIOUS,
    },
    InstallCommitState.PREPARED: {
        InstallCommitState.MIGRATION_APPLIED,
        InstallCommitState.RESTORED_PREVIOUS,
    },
    InstallCommitState.MIGRATION_APPLIED: {
        InstallCommitState.CANDIDATE_PUBLISHED,
        InstallCommitState.RESTORED_PREVIOUS,
    },
    InstallCommitState.CANDIDATE_PUBLISHED: {
        InstallCommitState.CANDIDATE_ACTIVATED,
        InstallCommitState.RESTORED_PREVIOUS,
    },
    InstallCommitState.CANDIDATE_ACTIVATED: {
        InstallCommitState.COMMITTED,
        InstallCommitState.RESTORED_PREVIOUS,
    },
    InstallCommitState.COMMITTED: {
        InstallCommitState.SUCCEEDED,
        InstallCommitState.COMMITTED_CLEANUP_PENDING,
    },
    InstallCommitState.COMMITTED_CLEANUP_PENDING: set(),
    InstallCommitState.SUCCEEDED: set(),
    InstallCommitState.RESTORED_PREVIOUS: set(),
}


def require_transition(
    current: InstallCommitState,
    target: InstallCommitState,
) -> InstallCommitState:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise RuntimeError(
            f"invalid_install_commit_transition:{current.value}:{target.value}"
        )
    return target
