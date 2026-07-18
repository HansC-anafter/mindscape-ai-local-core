"""Fail-closed delivery gate for formal container escalation results."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping


FORMAL_DOCKER_OPERATION_CLASSES = frozenset(
    {
        "docker_run_disposable_isolated_postgresql_bootstrap",
        "docker_run_disposable_isolated_pgbouncer_bootstrap",
    }
)
MAX_FORMAL_EXEC_OUTPUT_BYTES = 65_536
_CONTAINER_ID = re.compile(r"^[0-9a-f]{64}$")


def validate_formal_exec_result(
    source: Mapping[str, Any],
    *,
    operation_class: str,
) -> dict[str, Any]:
    """Permit container-id delivery only from a terminal successful result."""

    if operation_class not in FORMAL_DOCKER_OPERATION_CLASSES:
        raise ValueError("formal_escalation_operation_class_invalid")
    if not isinstance(source, Mapping):
        raise ValueError("formal_escalation_exec_result_invalid")
    output = source.get("output")
    output_text = output if isinstance(output, str) else ""
    output_bytes = len(output_text.encode("utf-8"))
    receipt: dict[str, Any] = {
        "operation_class": operation_class,
        "terminal": False,
        "poll_required": False,
        "delivery_allowed": False,
        "first_failure": None,
        "output_bytes": output_bytes,
        "output_sha256": hashlib.sha256(output_text.encode("utf-8")).hexdigest(),
        "secret_or_output_value_disclosed": False,
    }
    if "session_id" in source or "exit_code" not in source:
        receipt.update(
            {
                "poll_required": True,
                "first_failure": "formal_escalation_cli_nonterminal_result",
            }
        )
        return receipt
    if output_bytes > MAX_FORMAL_EXEC_OUTPUT_BYTES:
        receipt.update(
            {
                "terminal": True,
                "first_failure": "formal_escalation_exec_output_budget_exceeded",
            }
        )
        return receipt
    exit_code = source.get("exit_code")
    if type(exit_code) is not int:
        receipt.update(
            {
                "terminal": True,
                "first_failure": "formal_escalation_exec_exit_code_invalid",
            }
        )
        return receipt
    receipt["terminal"] = True
    receipt["exit_code"] = exit_code
    if exit_code != 0:
        receipt["first_failure"] = "formal_escalation_cli_terminal_failure"
        return receipt
    container_id = output_text.strip()
    if not _CONTAINER_ID.fullmatch(container_id):
        receipt["first_failure"] = "formal_escalation_container_id_invalid"
        return receipt
    receipt.update(
        {
            "delivery_allowed": True,
            "container_id": container_id,
        }
    )
    return receipt
