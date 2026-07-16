"""Machine-readable physical contract for the hot tasks control table."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from backend.app.database.task_index_manifest import task_index_ownership


TASK_JSON_PAYLOAD_COLUMNS = (
    "params",
    "result",
    "execution_context",
    "storyline_tags",
    "blocked_payload",
)

TASK_JSON_WRITE_LIMIT_BYTES = 15 * 1024

CORE_TASK_INDEX_ALLOWLIST = frozenset(
    {
        "tasks_pkey",
        "idx_tasks_execution_id",
        "idx_tasks_workspace_id",
        "idx_tasks_status",
        "idx_tasks_created_at",
        "idx_tasks_queue_shard_status",
    }
)

FORBIDDEN_PACK_INDEX_PATTERNS = (
    re.compile(r"\bpack_id\s*=\s*['\"](?!core\b)[^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"(?:params|result|execution_context|storyline_tags|blocked_payload)\s*(?:::jsonb)?\s*(?:->|#>)", re.IGNORECASE),
)


@dataclass(frozen=True)
class TaskIndexContractViolation:
    """One index definition that violates task control ownership."""

    index_name: str
    reason: str


def validate_task_index_definitions(
    definitions: Iterable[tuple[str, str]],
) -> list[TaskIndexContractViolation]:
    """Reject pack literals and JSON query paths on the generic tasks table."""

    violations: list[TaskIndexContractViolation] = []
    for raw_name, raw_definition in definitions:
        name = str(raw_name)
        definition = str(raw_definition)
        if task_index_ownership("tasks", name) is None:
            violations.append(
                TaskIndexContractViolation(
                    index_name=name,
                    reason="unregistered_tasks_index_owner_or_budget",
                )
            )
            continue
        for pattern in FORBIDDEN_PACK_INDEX_PATTERNS:
            if pattern.search(definition):
                violations.append(
                    TaskIndexContractViolation(
                        index_name=name,
                        reason="pack_specific_or_json_path_index_on_tasks",
                    )
                )
                break
    return violations
