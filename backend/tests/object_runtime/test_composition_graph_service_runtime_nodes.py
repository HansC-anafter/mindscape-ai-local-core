"""Executable node runtime tests for CompositionGraphService."""

import asyncio
import sys
import types

import pytest

from backend.tests.object_runtime.composition_graph_service_test_support import (
    CompositionGraphEdge,
    CompositionGraphNode,
    CompositionGraphRunRequest,
    CompositionGraphService,
    MemoryArtifactsStore,
    write_node_manifest,
)


@pytest.mark.asyncio
async def test_executable_graph_nodes_run_and_node_options(monkeypatch, tmp_path):
    write_node_manifest(
        tmp_path,
        "demo_nodes",
        {
            "enabled": True,
            "contract_version": "1.0.0",
            "nodes": [
                {
                    "id": "demo_source",
                    "label": "Demo Source",
                    "input_ports": [],
                    "output_ports": [
                        {
                            "id": "value",
                            "direction": "output",
                            "data_type": "demo_value",
                        }
                    ],
                    "payload_schema": {"type": "object", "additionalProperties": True},
                    "executor": {
                        "backend": "capabilities.demo_nodes.services.graph_nodes.demo:run_source"
                    },
                    "option_sources": {
                        "choice": {
                            "backend": "capabilities.demo_nodes.services.graph_nodes.demo:list_choices"
                        }
                    },
                },
                {
                    "id": "demo_sink",
                    "label": "Demo Sink",
                    "input_ports": [
                        {
                            "id": "value",
                            "direction": "input",
                            "data_type": "demo_value",
                            "required": True,
                        }
                    ],
                    "output_ports": [
                        {
                            "id": "result",
                            "direction": "output",
                            "data_type": "demo_result",
                        }
                    ],
                    "payload_schema": {"type": "object", "additionalProperties": True},
                    "executor": {
                        "backend": "capabilities.demo_nodes.services.graph_nodes.demo:run_sink"
                    },
                },
            ],
        },
    )
    capabilities = types.ModuleType("capabilities")
    demo_nodes = types.ModuleType("capabilities.demo_nodes")
    services = types.ModuleType("capabilities.demo_nodes.services")
    graph_nodes_module = types.ModuleType("capabilities.demo_nodes.services.graph_nodes")
    demo_module = types.ModuleType("capabilities.demo_nodes.services.graph_nodes.demo")

    async def run_source(**_kwargs):
        return {"status": "succeeded", "outputs": {"value": "from-source"}}

    async def run_sink(**kwargs):
        assert kwargs["input_values"]["value"] == "from-source"
        return {"status": "succeeded", "outputs": {"result": "done"}}

    def list_choices(**_kwargs):
        return {"options": [{"value": "a", "label": "Choice A"}]}

    demo_module.run_source = run_source
    demo_module.run_sink = run_sink
    demo_module.list_choices = list_choices
    monkeypatch.setitem(sys.modules, "capabilities", capabilities)
    monkeypatch.setitem(sys.modules, "capabilities.demo_nodes", demo_nodes)
    monkeypatch.setitem(sys.modules, "capabilities.demo_nodes.services", services)
    monkeypatch.setitem(
        sys.modules,
        "capabilities.demo_nodes.services.graph_nodes",
        graph_nodes_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "capabilities.demo_nodes.services.graph_nodes.demo",
        demo_module,
    )

    store = MemoryArtifactsStore()
    service = CompositionGraphService(
        artifacts_store=store,
        local_core_root=tmp_path,
        installed_pack_ids=["demo_nodes"],
    )
    contracts = service.list_contracts("ws")
    serialized_contract = contracts.contracts[0].model_dump(mode="json")
    assert serialized_contract["node_types"][0]["id"] == "demo_source"
    assert "backend" not in str(serialized_contract["node_types"])

    options = await service.resolve_node_options(
        "ws",
        node_type="demo_source",
        field="choice",
    )
    assert options.options[0].value == "a"

    started = await service.start_run(
        "ws",
        CompositionGraphRunRequest(
            meeting_id="mtg",
            thread_id="thread",
            nodes=[
                CompositionGraphNode(id="source", type="demo_source", payload={}),
                CompositionGraphNode(id="sink", type="demo_sink", payload={}),
            ],
            edges=[
                CompositionGraphEdge(
                    id="edge",
                    source="source",
                    source_port="value",
                    target="sink",
                    target_port="value",
                )
            ],
        ),
    )
    await asyncio.sleep(0.05)
    completed = service.get_run("ws", started.run.id).run
    assert completed.status == "succeeded"
    assert completed.node_states["sink"].outputs["result"] == "done"


@pytest.mark.asyncio
async def test_runtime_lock_serializes_parallel_nodes(monkeypatch, tmp_path):
    write_node_manifest(
        tmp_path,
        "locked_nodes",
        {
            "enabled": True,
            "contract_version": "1.0.0",
            "nodes": [
                {
                    "id": "locked_node",
                    "label": "Locked Node",
                    "input_ports": [],
                    "output_ports": [
                        {
                            "id": "value",
                            "direction": "output",
                            "data_type": "demo_value",
                        }
                    ],
                    "payload_schema": {"type": "object", "additionalProperties": True},
                    "executor": {
                        "backend": "capabilities.locked_nodes.services.graph_nodes.locked:run_locked"
                    },
                    "runtime_lock": {
                        "key_template": "profile:{payload.user_data_dir}",
                        "max_parallel": 1,
                    },
                }
            ],
        },
    )
    capabilities = types.ModuleType("capabilities")
    locked_nodes = types.ModuleType("capabilities.locked_nodes")
    services = types.ModuleType("capabilities.locked_nodes.services")
    graph_nodes_module = types.ModuleType("capabilities.locked_nodes.services.graph_nodes")
    locked_module = types.ModuleType(
        "capabilities.locked_nodes.services.graph_nodes.locked"
    )
    active = {"count": 0, "max": 0}

    async def run_locked(**kwargs):
        active["count"] += 1
        active["max"] = max(active["max"], active["count"])
        await asyncio.sleep(0.02)
        active["count"] -= 1
        return {"status": "succeeded", "outputs": {"value": kwargs["node_id"]}}

    locked_module.run_locked = run_locked
    monkeypatch.setitem(sys.modules, "capabilities", capabilities)
    monkeypatch.setitem(sys.modules, "capabilities.locked_nodes", locked_nodes)
    monkeypatch.setitem(sys.modules, "capabilities.locked_nodes.services", services)
    monkeypatch.setitem(
        sys.modules,
        "capabilities.locked_nodes.services.graph_nodes",
        graph_nodes_module,
    )
    monkeypatch.setitem(
        sys.modules,
        "capabilities.locked_nodes.services.graph_nodes.locked",
        locked_module,
    )

    service = CompositionGraphService(
        artifacts_store=MemoryArtifactsStore(),
        local_core_root=tmp_path,
        installed_pack_ids=["locked_nodes"],
    )
    started = await service.start_run(
        "ws",
        CompositionGraphRunRequest(
            nodes=[
                CompositionGraphNode(
                    id="a",
                    type="locked_node",
                    payload={"user_data_dir": "/tmp/profile"},
                ),
                CompositionGraphNode(
                    id="b",
                    type="locked_node",
                    payload={"user_data_dir": "/tmp/profile"},
                ),
            ],
            edges=[],
        ),
    )
    await asyncio.sleep(0.08)
    completed = service.get_run("ws", started.run.id).run
    assert completed.status == "succeeded"
    assert active["max"] == 1
