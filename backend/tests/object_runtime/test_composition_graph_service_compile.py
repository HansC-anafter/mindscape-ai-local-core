"""Compile path tests for CompositionGraphService."""

import sys
import types

import pytest

from backend.tests.object_runtime.composition_graph_service_test_support import (
    CompositionGraphCompileRequest,
    CompositionGraphDraftCreateRequest,
    CompositionGraphService,
    MemoryArtifactsStore,
    ObjectRef,
    ObjectRoleEntry,
    graph_edges,
    graph_nodes,
    valid_contract,
    write_manifest,
)


@pytest.mark.asyncio
async def test_compile_validates_graph_and_returns_command_envelope(
    monkeypatch,
    tmp_path,
):
    write_manifest(tmp_path, "demo", valid_contract())

    capabilities = types.ModuleType("capabilities")
    demo = types.ModuleType("capabilities.demo")
    services = types.ModuleType("capabilities.demo.services")
    compile_module = types.ModuleType("capabilities.demo.services.compile")

    def compile_graph(**kwargs):
        assert kwargs["selected_primary_pack"] == "demo"
        assert kwargs["composition_graph_ref"]["draft_id"]
        return {
            "command_envelope": {
                "meeting_id": kwargs["meeting_id"],
                "thread_id": kwargs["thread_id"],
                "intent_text": kwargs["command"],
                "requested_action": {
                    "verb": "demo_compile",
                    "pack_code": "demo",
                    "parameters": kwargs["action_parameters"],
                },
            }
        }

    def broken_compile_graph(**_kwargs):
        raise RuntimeError("compile backend unavailable")

    compile_module.compile_graph = compile_graph
    compile_module.broken_compile_graph = broken_compile_graph
    monkeypatch.setitem(sys.modules, "capabilities", capabilities)
    monkeypatch.setitem(sys.modules, "capabilities.demo", demo)
    monkeypatch.setitem(sys.modules, "capabilities.demo.services", services)
    monkeypatch.setitem(sys.modules, "capabilities.demo.services.compile", compile_module)

    store = MemoryArtifactsStore()
    service = CompositionGraphService(
        artifacts_store=store,
        local_core_root=tmp_path,
        installed_pack_ids=["demo"],
    )
    draft = service.create_draft(
        "ws",
        CompositionGraphDraftCreateRequest(
            meeting_id="mtg",
            thread_id="thread",
            selected_primary_pack="demo",
            nodes=graph_nodes(),
            edges=graph_edges(),
        ),
    ).draft

    failed = await service.compile_graph(
        "ws",
        CompositionGraphCompileRequest(
            draft_id=draft.id,
            meeting_id="mtg",
            command="Compile graph",
            selected_primary_pack="missing",
        ),
    )
    assert failed.status == "failed"
    assert failed.diagnostics[0].code == "missing_primary_pack"

    succeeded = await service.compile_graph(
        "ws",
        CompositionGraphCompileRequest(
            draft_id=draft.id,
            meeting_id="mtg",
            thread_id="thread",
            command="Compile graph",
            context_objects=[
                ObjectRoleEntry(
                    role="source",
                    ref=ObjectRef(
                        uri="mindscape://demo/reference/ref_1",
                        owner_pack="demo",
                        object_kind="reference",
                        object_id="ref_1",
                        workspace_id="ws",
                    ),
                )
            ],
            action_parameters={"tone": "specific"},
        ),
    )

    assert succeeded.status == "succeeded"
    assert succeeded.command_envelope is not None
    assert succeeded.command_envelope.requested_action["pack_code"] == "demo"
    assert succeeded.command_envelope.context_objects[0].role == "source"

    store_failure = MemoryArtifactsStore()
    write_manifest(
        tmp_path,
        "broken_demo",
        valid_contract("capabilities.demo.services.compile:broken_compile_graph"),
    )
    failure_service = CompositionGraphService(
        artifacts_store=store_failure,
        local_core_root=tmp_path,
        installed_pack_ids=["broken_demo"],
    )
    failure = await failure_service.compile_graph(
        "ws",
        CompositionGraphCompileRequest(
            meeting_id="mtg",
            command="Compile graph",
            selected_primary_pack="broken_demo",
            nodes=graph_nodes(),
            edges=graph_edges(),
        ),
    )
    assert failure.status == "failed"
    assert failure.diagnostics[0].code == "pack_compile_failed"
