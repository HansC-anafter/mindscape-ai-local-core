"""Owned baseline and retirement metadata for generic task-table indexes."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass(frozen=True)
class TaskIndexOwnership:
    relation: str
    index_name: str
    owner: str
    query_owner: str
    writer_cost: str
    replacement: str
    retirement_condition: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


_TASK_QUEUE_INDEXES = (
    "idx_tasks_admission_deferred_due",
    "idx_tasks_admission_deferred_due_shard",
    "idx_tasks_admission_deferred_payload_release_order",
    "idx_tasks_cold_blocked_due_default",
    "idx_tasks_cold_blocked_due_global",
    "idx_tasks_cold_blocked_due_shard",
    "idx_tasks_cold_blocked_pack_due_shard",
    "idx_tasks_cold_resource_wait_due_global",
    "idx_tasks_cold_resource_wait_due_shard",
    "idx_tasks_cold_unblocked_due_default",
    "idx_tasks_cold_unblocked_due_shard",
    "idx_tasks_cold_unblocked_pack_due_shard",
    "idx_tasks_cold_workspace_quota_due_shard",
    "idx_tasks_frontier_cold",
    "idx_tasks_frontier_ready",
    "idx_tasks_frontier_running_pending",
    "idx_tasks_pending_active_concurrency_key",
    "idx_tasks_pending_concurrency_key",
    "idx_tasks_pending_queue_position",
    "idx_tasks_pending_runner_ownership_cleanup",
    "idx_tasks_ready_running_ws_pack_selector",
    "idx_tasks_ready_running_ws_playbook_selector",
    "idx_tasks_ready_running_ws_reserved",
    "idx_tasks_resource_console_backlog_summary",
    "idx_tasks_running_concurrency_key_unique",
    "idx_tasks_running_heartbeat_at",
    "idx_tasks_workspace_queue_running_pack",
)

_TASK_CONTROL_LOOKUP_INDEXES = (
    "tasks_pkey",
    "idx_tasks_created_at",
    "idx_tasks_execution_id",
    "idx_tasks_message",
    "idx_tasks_pending_agent_dispatch_workspace_created",
    "idx_tasks_project",
    "idx_tasks_status",
    "idx_tasks_workspace",
    "idx_tasks_workspace_status",
    "idx_tasks_workspace_status_created_desc",
    "idx_tasks_ws_meeting_session_created_at",
    "idx_tasks_ws_pack_created_at",
)

_TASK_LEGACY_BLOCKED_KEEP_INDEXES = (
    "idx_tasks_workspace_execution_created_desc",
    "idx_tasks_ws_execctx_meeting_session_created_at",
    "idx_tasks_ws_execctx_thread_created_at",
    "idx_tasks_ws_pack_ref_created_at",
    "idx_tasks_ws_params_meeting_session_created_at",
    "idx_tasks_ws_params_thread_created_at",
)

IG_TASK_RETIREMENT_REPLACEMENTS = {
    "idx_tasks_ig_active_workbench": "task_summary_projection:pack_agnostic_lifecycle",
    "idx_tasks_ig_batch_pin_dedupe_profile_count": "ig_batch_pin_account_summary",
    "idx_tasks_ig_batch_pin_reconcile_handle": "ig_batch_pin_account_summary",
    "idx_tasks_ig_failed_workbench": "task_summary_projection:pack_agnostic_lifecycle",
    "idx_tasks_ig_following_profile_repair_hash": "ig_task_query_identity",
    "idx_tasks_ig_following_resume_child_lookup": "ig_task_query_identity",
    "idx_tasks_ig_ref_effective_params_latest": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_effective_params_latest_v2": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_latest_by_ref": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_latest_state_by_ref": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_live_ctx_fallback_latest": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_live_params_latest": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_running_params_refid": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_running_refid": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_terminal_failed_context": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ig_ref_terminal_failed_params": "ig_task_query_identity+task_summary_projection",
    "idx_tasks_ws_pack_batch_pin_handle_created_desc": "ig_batch_pin_account_summary",
    "idx_tasks_ws_pack_seed_key_created_desc": "ig_seed_execution_state_counts",
}

_SUMMARY_CORE_INDEXES = (
    "task_summary_projection_pkey",
    "idx_task_summary_projection_active_status_pack_updated",
    "idx_task_summary_projection_exec_created",
    "idx_task_summary_projection_include_order",
    "idx_task_summary_projection_pack_created",
    "idx_task_summary_projection_parent_created",
    "idx_task_summary_projection_ready_order",
    "idx_task_summary_projection_workspace_status",
    "idx_task_summary_projection_workspace_status_pack_updated",
    "idx_task_summary_projection_workspace_updated",
    "idx_tsp_queue_ready_eligible_v1",
)

IG_SUMMARY_RETIREMENT_REPLACEMENTS = {
    "idx_tsp_ig_post_detail_active_created": "task_summary_projection:pack_agnostic_lifecycle",
    "idx_tsp_ig_post_detail_active_shortcode_keys_v1": "ig_task_query_identity:shortcode_keys",
    "idx_tsp_ig_ref_task_status_compact_latest": "ig_task_query_identity+task_summary_projection",
    "idx_tsp_ig_workbench_active_rank_updated_v4": "task_summary_projection:pack_agnostic_lifecycle",
}


def _entry(
    relation: str,
    index_name: str,
    *,
    owner: str,
    query_owner: str,
    replacement: str,
    retirement_condition: str,
    status: str,
) -> TaskIndexOwnership:
    return TaskIndexOwnership(
        relation=relation,
        index_name=index_name,
        owner=owner,
        query_owner=query_owner,
        writer_cost="measure_live_index_bytes_wal_hot_and_dirtied_blocks",
        replacement=replacement,
        retirement_condition=retirement_condition,
        status=status,
    )


def _build_manifest() -> dict[tuple[str, str], TaskIndexOwnership]:
    entries: list[TaskIndexOwnership] = []
    for name in _TASK_QUEUE_INDEXES:
        entries.append(
            _entry(
                "tasks",
                name,
                owner="local-core.queue-scheduler",
                query_owner="runner-dispatch-and-resource-console",
                replacement="none-approved",
                retirement_condition="separate_queue-contract-change-with-parity",
                status="keep_core",
            )
        )
    for name in _TASK_CONTROL_LOOKUP_INDEXES:
        entries.append(
            _entry(
                "tasks",
                name,
                owner="local-core.task-control",
                query_owner="task-control-and-detail-reads",
                replacement="none-approved",
                retirement_condition="separate-control-query-change-with-parity",
                status="keep_core",
            )
        )
    for name in _TASK_LEGACY_BLOCKED_KEEP_INDEXES:
        entries.append(
            _entry(
                "tasks",
                name,
                owner="unresolved-legacy",
                query_owner="unresolved",
                replacement="unresolved",
                retirement_condition="owner-caller-plan-and-representative-observation-required",
                status="blocked_keep",
            )
        )
    for name, replacement in IG_TASK_RETIREMENT_REPLACEMENTS.items():
        entries.append(
            _entry(
                "tasks",
                name,
                owner="cloud.ig",
                query_owner="ig-runtime",
                replacement=replacement,
                retirement_condition="caller-negative-scan-plan-workflow-and-24h-observation",
                status="retirement_candidate_blocked",
            )
        )
    for name in _SUMMARY_CORE_INDEXES:
        entries.append(
            _entry(
                "task_summary_projection",
                name,
                owner="local-core.task-lifecycle-projection",
                query_owner="workspace-task-list-and-runner-release-gate",
                replacement="none-approved",
                retirement_condition="separate-lifecycle-query-change-with-parity",
                status="keep_core",
            )
        )
    for name, replacement in IG_SUMMARY_RETIREMENT_REPLACEMENTS.items():
        entries.append(
            _entry(
                "task_summary_projection",
                name,
                owner="cloud.ig",
                query_owner="ig-runtime",
                replacement=replacement,
                retirement_condition="caller-negative-scan-plan-workflow-and-24h-observation",
                status="retirement_candidate_blocked",
            )
        )
    manifest = {(item.relation, item.index_name): item for item in entries}
    if len(manifest) != len(entries):
        raise RuntimeError("duplicate_task_index_manifest_entry")
    return manifest


TASK_INDEX_OWNERSHIP_MANIFEST = _build_manifest()


def task_index_ownership(
    relation: str,
    index_name: str,
) -> Optional[TaskIndexOwnership]:
    return TASK_INDEX_OWNERSHIP_MANIFEST.get((str(relation), str(index_name)))


def retirement_target(index_name: str) -> Optional[TaskIndexOwnership]:
    for relation in ("tasks", "task_summary_projection"):
        item = task_index_ownership(relation, index_name)
        if item is not None and item.status == "retirement_candidate_blocked":
            return item
    return None


__all__ = [
    "IG_SUMMARY_RETIREMENT_REPLACEMENTS",
    "IG_TASK_RETIREMENT_REPLACEMENTS",
    "TASK_INDEX_OWNERSHIP_MANIFEST",
    "TaskIndexOwnership",
    "retirement_target",
    "task_index_ownership",
]
