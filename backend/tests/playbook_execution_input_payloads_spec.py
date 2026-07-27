from types import SimpleNamespace

import pytest

from backend.app.services.playbook_execution_input_payloads import (
    ExecutionInputPayloadError,
    hydrate_execution_inputs,
    prepare_execution_input_context,
)


def _workspace_loader(storage_root):
    return lambda _workspace_id: SimpleNamespace(
        storage_base_path=str(storage_root)
    )


def test_large_execution_inputs_round_trip_through_workspace_storage(tmp_path):
    inputs = {
        "site_key": "yogacookie-app",
        "execution_unit": {"sections": ["x" * 4096 for _ in range(4)]},
    }

    context = prepare_execution_input_context(
        workspace_id="workspace-1",
        execution_id="execution-1",
        inputs=inputs,
        workspace_loader=_workspace_loader(tmp_path),
    )

    assert "inputs" not in context
    descriptor = context["execution_inputs_ref"]
    assert descriptor["workspace_id"] == "workspace-1"
    assert descriptor["execution_id"] == "execution-1"
    assert descriptor["bytes"] > 8 * 1024
    assert hydrate_execution_inputs(
        context,
        workspace_loader=_workspace_loader(tmp_path),
    ) == inputs


def test_small_execution_inputs_remain_inline(tmp_path):
    inputs = {"site_key": "yogacookie-app"}

    context = prepare_execution_input_context(
        workspace_id="workspace-1",
        execution_id="execution-1",
        inputs=inputs,
        workspace_loader=_workspace_loader(tmp_path),
    )

    assert context == {"inputs": inputs}
    assert not (tmp_path / "execution-inputs").exists()


def test_execution_input_hydration_rejects_checksum_mismatch(tmp_path):
    inputs = {"execution_unit": {"sections": ["x" * 9000]}}
    context = prepare_execution_input_context(
        workspace_id="workspace-1",
        execution_id="execution-1",
        inputs=inputs,
        workspace_loader=_workspace_loader(tmp_path),
    )
    payload_path = tmp_path / "execution-inputs" / "execution-1" / "inputs.json"
    payload_path.write_text("{}", encoding="utf-8")

    with pytest.raises(
        ExecutionInputPayloadError,
        match="execution_input_size_mismatch",
    ):
        hydrate_execution_inputs(
            context,
            workspace_loader=_workspace_loader(tmp_path),
        )


def test_execution_input_identity_cannot_be_overwritten(tmp_path):
    first = {"execution_unit": {"sections": ["x" * 9000]}}
    second = {"execution_unit": {"sections": ["y" * 9000]}}
    prepare_execution_input_context(
        workspace_id="workspace-1",
        execution_id="execution-1",
        inputs=first,
        workspace_loader=_workspace_loader(tmp_path),
    )

    with pytest.raises(
        ExecutionInputPayloadError,
        match="execution_input_identity_conflict",
    ):
        prepare_execution_input_context(
            workspace_id="workspace-1",
            execution_id="execution-1",
            inputs=second,
            workspace_loader=_workspace_loader(tmp_path),
        )
