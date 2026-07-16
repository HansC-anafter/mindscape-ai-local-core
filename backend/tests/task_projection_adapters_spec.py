from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.task_projection_adapters import (
    TaskProjectionAdapterDefinition,
    build_task_display_inputs,
    load_task_display_input_overlays,
    project_task_identity,
    register_definition,
    reset_registry_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    reset_registry_for_tests()
    yield
    reset_registry_for_tests()


def _definition(writer, *, indexes: tuple[str, ...] = ("idx_ig_identity",)):
    return TaskProjectionAdapterDefinition(
        capability_code="ig",
        pack_id_patterns=("ig_*",),
        backend_path="",
        table="ig_task_query_identity",
        identity_fields=("task_id", "workspace_id", "reference_id"),
        indexes=indexes,
        callable_override=writer,
    )


def test_adapter_uses_the_callers_transaction_for_created_and_identity_changed() -> None:
    calls = []
    connection = object()

    def writer(*, conn, task, reason):
        calls.append((conn, task.id, reason))

    register_definition(_definition(writer))
    task = SimpleNamespace(id="task-1", pack_id="ig_analyze_pinned_reference")

    assert project_task_identity(conn=connection, task=task, reason="created") is True
    assert (
        project_task_identity(
            conn=connection,
            task=task,
            reason="identity_changed",
        )
        is True
    )
    assert calls == [
        (connection, "task-1", "created"),
        (connection, "task-1", "identity_changed"),
    ]


def test_non_owned_pack_is_not_forced_into_a_generic_projection() -> None:
    assert (
        project_task_identity(
            conn=object(),
            task=SimpleNamespace(id="task-1", pack_id="planning"),
            reason="created",
        )
        is False
    )


def test_adapter_contract_rejects_generic_tables_and_more_than_four_indexes() -> None:
    with pytest.raises(ValueError, match="pack_owned"):
        register_definition(
            TaskProjectionAdapterDefinition(
                capability_code="ig",
                pack_id_patterns=("ig_*",),
                backend_path="capabilities.ig.services.writer:write",
                table="task_query_dimensions",
                identity_fields=("task_id",),
                indexes=(),
            )
        )

    with pytest.raises(ValueError, match="index_budget"):
        register_definition(
            _definition(
                lambda **_: None,
                indexes=("one", "two", "three", "four", "five"),
            )
        )


def test_lifecycle_changes_cannot_invoke_pack_identity_projection() -> None:
    register_definition(_definition(lambda **_: None))

    with pytest.raises(ValueError, match="invalid_reason"):
        project_task_identity(
            conn=object(),
            task=SimpleNamespace(id="task-1", pack_id="ig_reference"),
            reason="lifecycle_changed",
        )


def test_display_inputs_are_pack_owned_and_bounded() -> None:
    definition = _definition(lambda **_: True)
    register_definition(
        TaskProjectionAdapterDefinition(
            capability_code=definition.capability_code,
            pack_id_patterns=definition.pack_id_patterns,
            backend_path=definition.backend_path,
            table=definition.table,
            identity_fields=definition.identity_fields,
            indexes=definition.indexes,
            callable_override=definition.callable_override,
            display_callable_override=lambda *, task: {
                "reference_id": task.execution_context["inputs"]["reference_id"]
            },
        )
    )

    assert build_task_display_inputs(
        task=SimpleNamespace(
            pack_id="ig_reference",
            execution_context={"inputs": {"reference_id": "ref-1"}},
        )
    ) == {"reference_id": "ref-1"}


def test_display_inputs_fail_closed_over_four_kib() -> None:
    definition = _definition(lambda **_: True)
    register_definition(
        TaskProjectionAdapterDefinition(
            capability_code=definition.capability_code,
            pack_id_patterns=definition.pack_id_patterns,
            backend_path=definition.backend_path,
            table=definition.table,
            identity_fields=definition.identity_fields,
            indexes=definition.indexes,
            callable_override=definition.callable_override,
            display_callable_override=lambda **_: {"value": "x" * 4097},
        )
    )

    with pytest.raises(RuntimeError, match="display_payload_over_budget"):
        build_task_display_inputs(
            task=SimpleNamespace(pack_id="ig_reference")
        )


def test_bulk_display_reader_receives_only_rows_owned_by_its_pack() -> None:
    definition = _definition(lambda **_: True)
    calls = []

    def bulk_reader(*, conn, rows):
        calls.append((conn, list(rows)))
        return {"task-1": {"reference_id": "ref-1"}}

    register_definition(
        TaskProjectionAdapterDefinition(
            capability_code=definition.capability_code,
            pack_id_patterns=definition.pack_id_patterns,
            backend_path=definition.backend_path,
            table=definition.table,
            identity_fields=definition.identity_fields,
            indexes=definition.indexes,
            callable_override=definition.callable_override,
            display_bulk_callable_override=bulk_reader,
        )
    )
    connection = object()

    overlays = load_task_display_input_overlays(
        conn=connection,
        rows=[
            {"task_id": "task-1", "pack_id": "ig_reference"},
            {"task_id": "task-2", "pack_id": "planning"},
        ],
    )

    assert overlays == {"task-1": {"reference_id": "ref-1"}}
    assert calls == [
        (connection, [{"task_id": "task-1", "pack_id": "ig_reference"}])
    ]


def test_generic_projection_builder_contains_no_pack_input_key_knowledge() -> None:
    source = (
        Path(__file__).parents[1]
        / "app"
        / "services"
        / "task_projection_builder.py"
    ).read_text(encoding="utf-8")
    for forbidden in (
        "reference_id",
        "target_handle",
        "user_data_dir",
        "shortcode",
        "visit_account_pages",
    ):
        assert forbidden not in source
