#!/usr/bin/env python3
"""Reconcile stale capability install jobs blocked on execution activation.

Default mode is dry-run. Use --apply to mark stale, superseded pending
activation jobs as failed through CapabilityInstallJobStore.mark_failed().
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import bindparam, text


LOCAL_CORE_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
for _path in (LOCAL_CORE_ROOT, BACKEND_ROOT, APP_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


from backend.app.services.stores.capability_install_job_store import (  # noqa: E402
    CapabilityInstallJobStore,
)
from backend.app.services.stores.pack_activation_state_store import (  # noqa: E402
    PackActivationStateStore,
)


PENDING_STATE = "pending_execution_activation"
STALE_REASON = "stale_pending_activation_superseded_by_active_manifest"
STALE_ERROR = "superseded_by_active_manifest"
SCRIPT_SOURCE = "reconcile_capability_install_activation_jobs"


@dataclass(frozen=True)
class PendingActivationJob:
    install_id: str
    capability_code: str | None
    state: str
    result_payload: dict[str, Any]
    pending_manifest_hash: str | None
    version: str | None
    created_at: str | None
    updated_at: str | None
    error: str | None


@dataclass(frozen=True)
class ActivationSnapshot:
    pack_id: str
    install_state: str | None
    activation_state: str | None
    manifest_hash: str | None
    updated_at: str | None
    version: str | None = None


@dataclass(frozen=True)
class CleanupDecision:
    install_id: str
    capability_code: str | None
    action: str
    apply_eligible: bool
    reason: str
    pending_manifest_hash: str | None
    active_manifest_hash: str | None
    job_updated_at: str | None
    activation_updated_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "install_id": self.install_id,
            "capability_code": self.capability_code,
            "action": self.action,
            "apply_eligible": self.apply_eligible,
            "reason": self.reason,
            "pending_manifest_hash": self.pending_manifest_hash,
            "active_manifest_hash": self.active_manifest_hash,
            "job_updated_at": self.job_updated_at,
            "activation_updated_at": self.activation_updated_at,
        }


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _json_loads(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        decoded = json.loads(value)
        return dict(decoded) if isinstance(decoded, dict) else {}
    return {}


def _extract_pending_manifest_hash(payload: Mapping[str, Any]) -> str | None:
    activation = payload.get("activation")
    if isinstance(activation, Mapping):
        value = activation.get("manifest_hash")
        if value:
            return str(value)
    value = payload.get("manifest_hash")
    return str(value) if value else None


def _extract_capability_code(payload: Mapping[str, Any]) -> str | None:
    for key in ("capability_code", "pack_id", "code"):
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _active_is_installed(snapshot: ActivationSnapshot) -> bool:
    return (
        snapshot.install_state == "installed"
        and snapshot.activation_state == "active"
        and bool(snapshot.manifest_hash)
    )


def classify_pending_job(
    job: PendingActivationJob,
    activation: ActivationSnapshot | None,
) -> CleanupDecision:
    if job.state != PENDING_STATE:
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=job.capability_code,
            action="skip_non_pending_state",
            apply_eligible=False,
            reason=f"state_is_{job.state}",
            pending_manifest_hash=job.pending_manifest_hash,
            active_manifest_hash=None,
            job_updated_at=job.updated_at,
            activation_updated_at=None,
        )
    if not job.capability_code:
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=None,
            action="blocked_missing_capability_code",
            apply_eligible=False,
            reason="missing_capability_code",
            pending_manifest_hash=job.pending_manifest_hash,
            active_manifest_hash=None,
            job_updated_at=job.updated_at,
            activation_updated_at=None,
        )
    if activation is None:
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=job.capability_code,
            action="blocked_missing_active_state",
            apply_eligible=False,
            reason="missing_pack_activation_state",
            pending_manifest_hash=job.pending_manifest_hash,
            active_manifest_hash=None,
            job_updated_at=job.updated_at,
            activation_updated_at=None,
        )
    if not _active_is_installed(activation):
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=job.capability_code,
            action="blocked_activation_not_active",
            apply_eligible=False,
            reason=(
                f"install_state={activation.install_state};"
                f"activation_state={activation.activation_state}"
            ),
            pending_manifest_hash=job.pending_manifest_hash,
            active_manifest_hash=activation.manifest_hash,
            job_updated_at=job.updated_at,
            activation_updated_at=activation.updated_at,
        )
    if not job.pending_manifest_hash:
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=job.capability_code,
            action="blocked_missing_pending_manifest_hash",
            apply_eligible=False,
            reason="missing_pending_manifest_hash",
            pending_manifest_hash=None,
            active_manifest_hash=activation.manifest_hash,
            job_updated_at=job.updated_at,
            activation_updated_at=activation.updated_at,
        )
    if job.pending_manifest_hash == activation.manifest_hash:
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=job.capability_code,
            action="reconcile_via_status_api",
            apply_eligible=False,
            reason="pending_hash_matches_active_hash",
            pending_manifest_hash=job.pending_manifest_hash,
            active_manifest_hash=activation.manifest_hash,
            job_updated_at=job.updated_at,
            activation_updated_at=activation.updated_at,
        )

    job_updated_at = _parse_dt(job.updated_at)
    activation_updated_at = _parse_dt(activation.updated_at)
    if job_updated_at is None or activation_updated_at is None:
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=job.capability_code,
            action="blocked_unparseable_timestamp",
            apply_eligible=False,
            reason="job_or_activation_updated_at_unparseable",
            pending_manifest_hash=job.pending_manifest_hash,
            active_manifest_hash=activation.manifest_hash,
            job_updated_at=job.updated_at,
            activation_updated_at=activation.updated_at,
        )
    if activation_updated_at < job_updated_at:
        return CleanupDecision(
            install_id=job.install_id,
            capability_code=job.capability_code,
            action="blocked_active_state_older_than_job",
            apply_eligible=False,
            reason="active_state_updated_before_pending_job",
            pending_manifest_hash=job.pending_manifest_hash,
            active_manifest_hash=activation.manifest_hash,
            job_updated_at=job.updated_at,
            activation_updated_at=activation.updated_at,
        )

    return CleanupDecision(
        install_id=job.install_id,
        capability_code=job.capability_code,
        action="stale_superseded_by_active_manifest",
        apply_eligible=True,
        reason=STALE_REASON,
        pending_manifest_hash=job.pending_manifest_hash,
        active_manifest_hash=activation.manifest_hash,
        job_updated_at=job.updated_at,
        activation_updated_at=activation.updated_at,
    )


def build_superseded_result_payload(
    job: PendingActivationJob,
    activation: ActivationSnapshot,
    *,
    reconciled_at: str | None = None,
) -> dict[str, Any]:
    payload = dict(job.result_payload)
    reconciled_at = reconciled_at or _utc_now_iso()
    previous_execution_activation = payload.get("execution_activation")
    payload["execution_activation"] = {
        "state": "failed",
        "source": SCRIPT_SOURCE,
        "reason": STALE_REASON,
        "previous": previous_execution_activation,
        "reconciled_at": reconciled_at,
    }
    payload["maintenance_reconciliation"] = {
        "source": SCRIPT_SOURCE,
        "reason": STALE_REASON,
        "job_state_before": job.state,
        "job_updated_at": job.updated_at,
        "reconciled_at": reconciled_at,
    }
    payload["superseded_by"] = {
        "pack_id": activation.pack_id,
        "version": activation.version,
        "manifest_hash": activation.manifest_hash,
        "activation_updated_at": activation.updated_at,
    }
    payload["restart_required"] = False
    payload["backend_process_restart_required"] = False
    payload["runner_restart_required"] = False
    payload["execution_activation_state"] = "failed"
    return payload


def fetch_pending_jobs(store: CapabilityInstallJobStore) -> list[PendingActivationJob]:
    with store.get_connection() as conn:
        rows = (
            conn.execute(
                text(
                    """
                    SELECT install_id, state, result_payload, error, created_at, updated_at
                    FROM capability_install_jobs
                    WHERE state = :state
                    ORDER BY updated_at ASC, install_id ASC
                    """
                ),
                {"state": PENDING_STATE},
            )
            .mappings()
            .all()
        )
    jobs: list[PendingActivationJob] = []
    for row in rows:
        payload = store.deserialize_json(row.get("result_payload"), {})
        jobs.append(
            PendingActivationJob(
                install_id=str(row["install_id"]),
                capability_code=_extract_capability_code(payload),
                state=str(row["state"]),
                result_payload=payload if isinstance(payload, dict) else {},
                pending_manifest_hash=_extract_pending_manifest_hash(payload),
                version=str(payload.get("version")) if payload.get("version") else None,
                created_at=_iso(row.get("created_at")),
                updated_at=_iso(row.get("updated_at")),
                error=str(row["error"]) if row.get("error") else None,
            )
        )
    return jobs


def _fetch_installed_pack_versions(
    store: CapabilityInstallJobStore,
    pack_ids: Sequence[str],
) -> dict[str, str | None]:
    if not pack_ids:
        return {}
    with store.get_connection() as conn:
        stmt = text(
            """
            SELECT pack_id, metadata
            FROM installed_packs
            WHERE pack_id IN :pack_ids
            """
        ).bindparams(bindparam("pack_ids", expanding=True))
        rows = (
            conn.execute(stmt, {"pack_ids": list(pack_ids)})
            .mappings()
            .all()
        )
    versions: dict[str, str | None] = {}
    for row in rows:
        metadata = _json_loads(row.get("metadata"))
        version = metadata.get("version")
        versions[str(row["pack_id"])] = str(version) if version else None
    return versions


def fetch_activation_snapshots(
    activation_store: PackActivationStateStore,
    job_store: CapabilityInstallJobStore,
    capability_codes: Iterable[str],
) -> dict[str, ActivationSnapshot]:
    states = activation_store.list_states_by_pack_id()
    wanted = sorted({code for code in capability_codes if code})
    versions = _fetch_installed_pack_versions(job_store, wanted)
    snapshots: dict[str, ActivationSnapshot] = {}
    for pack_id in wanted:
        state = states.get(pack_id)
        if not state:
            continue
        snapshots[pack_id] = ActivationSnapshot(
            pack_id=pack_id,
            install_state=state.get("install_state"),
            activation_state=state.get("activation_state"),
            manifest_hash=state.get("manifest_hash"),
            updated_at=state.get("updated_at"),
            version=versions.get(pack_id),
        )
    return snapshots


def run_reconciliation(*, apply: bool) -> dict[str, Any]:
    job_store = CapabilityInstallJobStore()
    activation_store = PackActivationStateStore()
    jobs = fetch_pending_jobs(job_store)
    activations = fetch_activation_snapshots(
        activation_store,
        job_store,
        [job.capability_code for job in jobs if job.capability_code],
    )

    decisions = [
        classify_pending_job(job, activations.get(job.capability_code or ""))
        for job in jobs
    ]
    stale_jobs = [
        (job, decision)
        for job, decision in zip(jobs, decisions)
        if decision.apply_eligible
    ]

    updated: list[dict[str, Any]] = []
    if apply:
        for job, decision in stale_jobs:
            activation = activations.get(job.capability_code or "")
            if activation is None:
                continue
            payload = build_superseded_result_payload(job, activation)
            marked = job_store.mark_failed(
                job.install_id,
                error=STALE_ERROR,
                result_payload=payload,
            )
            updated.append(
                {
                    "install_id": job.install_id,
                    "capability_code": job.capability_code,
                    "state": (marked or {}).get("state"),
                    "error": (marked or {}).get("error"),
                    "action": decision.action,
                }
            )

    return {
        "mode": "apply" if apply else "dry_run",
        "pending_count": len(jobs),
        "decision_counts": _count_decisions(decisions),
        "stale_candidate_count": len(stale_jobs),
        "updated_count": len(updated),
        "decisions": [decision.to_dict() for decision in decisions],
        "updated": updated,
    }


def _count_decisions(decisions: Sequence[CleanupDecision]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.action] = counts.get(decision.action, 0) + 1
    return dict(sorted(counts.items()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile stale capability install activation jobs."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist stale pending activation rows as failed. Default is dry-run.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_reconciliation(apply=bool(args.apply))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
