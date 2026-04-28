import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import backend.app as backend_app

sys.modules["app"] = backend_app

from backend.app.models.object_runtime import (
    ObjectActionClosureRequest,
    ObjectActionInvokeRequest,
    ObjectActionPlanRequest,
    ObjectInstanceRecord,
    ObjectRef,
)
from backend.app.services.object_action_closure_wiring import (
    close_object_action_from_execution_result,
)


def _load_object_runtime_module():
    workspace_dir = REPO_ROOT / "backend" / "app" / "routes" / "core" / "workspace"
    package_name = "backend.app.routes.core.workspace"
    if package_name not in sys.modules:
        workspace_package = types.ModuleType(package_name)
        workspace_package.__path__ = [str(workspace_dir)]
        sys.modules[package_name] = workspace_package

    module_path = workspace_dir / "object_runtime.py"
    module_name = "backend.app.routes.core.workspace.object_runtime_action_plan_test_module"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


object_runtime_module = _load_object_runtime_module()


def _ref(owner_pack: str, object_kind: str, object_id: str) -> ObjectRef:
    return ObjectRef(
        uri=f"mindscape://{owner_pack}/{object_kind}/{object_id}",
        owner_pack=owner_pack,
        object_kind=object_kind,
        object_id=object_id,
        workspace_id="ws_demo",
    )


class FakeCatalogRegistry:
    def __init__(self, *, include_affordance: bool = True):
        self.include_affordance = include_affordance

    def get_entry(self, owner_pack: str, object_kind: str):
        payload = {
            "owner_pack": owner_pack,
            "object_kind": object_kind,
            "display_name": object_kind.replace("_", " ").title(),
            "id_field": "id",
            "affordances": [],
        }
        if self.include_affordance and object_kind == "storyboard_scene":
            payload["affordances"] = [
                {
                    "verb": "generate_reels_asset",
                    "label": "Generate reels asset",
                    "description": "Generate an asset into a storyboard scene.",
                    "object_kinds": ["storyboard_scene"],
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "required_roles": ["source", "target", "character"],
                    "write_modes": ["staged"],
                    "planner_backend": "capabilities.performance_direction.services.aol:plan_reels_asset",
                    "executor_backend": "capabilities.performance_direction.services.aol:execute_reels_asset",
                }
            ]
        return payload


async def _fake_ensure_workspace_exists(workspace_id: str) -> None:
    assert workspace_id == "ws_demo"


@pytest.mark.asyncio
async def test_object_action_plan_invokes_pack_planner_with_structured_roles(monkeypatch):
    captured = {}
    captured_relations = []

    async def fake_invoke_backend(backend_path: str, **kwargs):
        captured["backend_path"] = backend_path
        captured["kwargs"] = kwargs
        return {
            "plan": {
                "steps": ["load_source_reference", "patch_storyboard_scene"],
                "target_uri": kwargs["role_assignments"][1]["ref"]["uri"],
                "character_uri": kwargs["role_assignments"][2]["ref"]["uri"],
            }
        }

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        _fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_invoke_backend_callable",
        fake_invoke_backend,
    )

    class FakeRelationStore:
        def upsert_many(self, workspace_id, relations):
            captured_relations.extend(relations)
            return len(relations)

    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: FakeRelationStore(),
    )

    response = await object_runtime_module.plan_workspace_object_action(
        workspace_id="ws_demo",
        request=ObjectActionPlanRequest(
            instruction="Generate a 90s yoga reels asset into this scene.",
            affordance_verb="generate_reels_asset",
            write_mode="staged",
            entries=[
                {"role": "source", "ref": _ref("ig", "reference", "ref_001")},
                {
                    "role": "target",
                    "ref": _ref(
                        "performance_direction",
                        "storyboard_scene",
                        "pd_session_1:latest:sc02",
                    ),
                },
                {
                    "role": "character",
                    "ref": _ref("character_training", "character_card", "card_chacto"),
                },
            ],
        ),
    )

    assert response.status == "planned"
    assert response.selected_affordance.verb == "generate_reels_asset"
    assert response.request_plan["steps"] == [
        "load_source_reference",
        "patch_storyboard_scene",
    ]
    assert captured["backend_path"] == (
        "capabilities.performance_direction.services.aol:plan_reels_asset"
    )
    assert [entry["role"] for entry in captured["kwargs"]["role_assignments"]] == [
        "source",
        "target",
        "character",
    ]
    assert response.request_plan["action_plan_id"].startswith("oap_")
    assert [relation.relation_kind for relation in captured_relations] == [
        "planned_input_for",
        "planned_character_for",
    ]
    assert {relation.provenance_id for relation in captured_relations} == {
        response.request_plan["action_plan_id"],
    }
    assert captured_relations[0].source_ref.object_kind == "reference"
    assert captured_relations[0].target_ref.object_kind == "storyboard_scene"


@pytest.mark.asyncio
async def test_object_action_plan_reports_missing_required_roles(monkeypatch):
    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        _fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(),
    )

    response = await object_runtime_module.plan_workspace_object_action(
        workspace_id="ws_demo",
        request=ObjectActionPlanRequest(
            instruction="Generate a 90s yoga reels asset into this scene.",
            affordance_verb="generate_reels_asset",
            entries=[
                {"role": "source", "ref": _ref("ig", "reference", "ref_001")},
                {
                    "role": "target",
                    "ref": _ref(
                        "performance_direction",
                        "storyboard_scene",
                        "pd_session_1:latest:sc02",
                    ),
                },
            ],
        ),
    )

    assert response.status == "needs_disambiguation"
    assert response.missing_roles == ["character"]
    assert response.errors[0].code == "missing_required_roles"


@pytest.mark.asyncio
async def test_object_action_plan_reports_unsupported_affordance(monkeypatch):
    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        _fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(include_affordance=False),
    )

    response = await object_runtime_module.plan_workspace_object_action(
        workspace_id="ws_demo",
        request=ObjectActionPlanRequest(
            instruction="Generate a 90s yoga reels asset into this scene.",
            entries=[
                {"role": "source", "ref": _ref("ig", "reference", "ref_001")},
            ],
        ),
    )

    assert response.status == "unsupported"
    assert response.errors[0].code == "affordance_unavailable"


@pytest.mark.asyncio
async def test_object_action_invoke_runs_executor_closes_outputs_and_persists_task(monkeypatch):
    captured_outputs = []
    captured_relations = []
    captured_tasks = []

    output_record = ObjectInstanceRecord(
        ref=_ref("performance_direction", "generated_reels_asset", "gra_invoke_001"),
        title="Invoked reels asset",
        summary_text="Generated by invoke endpoint.",
        mention_tokens=["@reels_asset:gra_invoke_001"],
        mention_text="invoked reels asset",
    )

    async def fake_invoke_backend(backend_path: str, **kwargs):
        assert backend_path == "capabilities.performance_direction.services.aol:execute_reels_asset"
        assert kwargs["action_plan_id"] == "oap_invoke_001"
        assert [entry["role"] for entry in kwargs["role_assignments"]] == [
            "source",
            "target",
            "character",
        ]
        return {
            "status": "completed",
            "outputs": {
                "object_action_closure": {
                    "status": "succeeded",
                    "output_records": [output_record.model_dump()],
                }
            },
        }

    class FakeObjectInstanceStore:
        def upsert_many(self, workspace_id, records):
            assert workspace_id == "ws_demo"
            captured_outputs.extend(records)
            return len(records)

    class FakeRelationStore:
        def upsert_many(self, workspace_id, relations):
            assert workspace_id == "ws_demo"
            captured_relations.extend(relations)
            return len(relations)

    class FakeTasksStore:
        def get_task_by_execution_id(self, execution_id):
            return None

        def create_task(self, task):
            captured_tasks.append(task)
            return task

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        _fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_invoke_backend_callable",
        fake_invoke_backend,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_instance_registry_store",
        lambda: FakeObjectInstanceStore(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: FakeRelationStore(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_tasks_store",
        lambda: FakeTasksStore(),
    )
    sys.modules["backend.app.routes.core.workspace.object_runtime"] = object_runtime_module

    role_assignments = [
        {"role": "source", "ref": _ref("ig", "reference", "ref_001").model_dump()},
        {
            "role": "target",
            "ref": _ref(
                "performance_direction",
                "storyboard_scene",
                "pd_session_1:latest:sc02",
            ).model_dump(),
        },
        {
            "role": "character",
            "ref": _ref("character_training", "character_card", "card_chacto").model_dump(),
        },
    ]
    response = await object_runtime_module.invoke_workspace_object_action(
        workspace_id="ws_demo",
        request=ObjectActionInvokeRequest(
            instruction="Generate a 90s reels asset.",
            meeting_id="meeting_demo",
            thread_id="meeting_demo",
            execution_id="exec_invoke_001",
            object_action_plan={
                "selected_affordance": {
                    "verb": "generate_reels_asset",
                    "label": "Generate reels asset",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "required_roles": ["source", "target", "character"],
                    "planner_backend": "capabilities.performance_direction.services.aol:plan_reels_asset",
                    "executor_backend": "capabilities.performance_direction.services.aol:execute_reels_asset",
                },
                "role_assignments": role_assignments,
                "request_plan": {
                    "action_plan_id": "oap_invoke_001",
                    "affordance_verb": "generate_reels_asset",
                    "meeting_id": "meeting_demo",
                },
            },
        ),
    )

    assert response.status == "succeeded"
    assert response.action_plan_id == "oap_invoke_001"
    assert response.execution_id == "exec_invoke_001"
    assert response.closure["indexed_output_count"] == 1
    assert captured_outputs[0].ref.object_id == "gra_invoke_001"
    assert [relation.relation_kind for relation in captured_relations] == [
        "generated_from_source",
        "landed_in",
        "generated_with_character",
    ]
    assert len(captured_tasks) == 1
    task = captured_tasks[0]
    assert task.meeting_session_id == "meeting_demo"
    assert task.execution_context["object_action_closure"]["action_plan_id"] == "oap_invoke_001"
    assert task.execution_context["inputs"]["object_action_plan_id"] == "oap_invoke_001"


@pytest.mark.asyncio
async def test_object_action_close_indexes_outputs_and_execution_provenance(monkeypatch):
    captured_outputs = []
    captured_relations = []

    class FakeObjectInstanceStore:
        def upsert_many(self, workspace_id, records):
            assert workspace_id == "ws_demo"
            captured_outputs.extend(records)
            return len(records)

    class FakeRelationStore:
        def upsert_many(self, workspace_id, relations):
            assert workspace_id == "ws_demo"
            captured_relations.extend(relations)
            return len(relations)

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        _fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_instance_registry_store",
        lambda: FakeObjectInstanceStore(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: FakeRelationStore(),
    )

    output_ref = _ref(
        "performance_direction",
        "generated_reels_asset",
        "gra_plan_001",
    )
    response = await object_runtime_module.close_workspace_object_action(
        workspace_id="ws_demo",
        request=ObjectActionClosureRequest(
            action_plan_id="oap_demo",
            meeting_id="meeting_demo",
            affordance_verb="generate_reels_asset",
            entries=[
                {"role": "source", "ref": _ref("ig", "reference", "ref_001")},
                {
                    "role": "target",
                    "ref": _ref(
                        "performance_direction",
                        "storyboard_scene",
                        "pd_session_1:latest:sc02",
                    ),
                },
                {
                    "role": "character",
                    "ref": _ref("character_training", "character_card", "card_chacto"),
                },
            ],
            output_records=[
                ObjectInstanceRecord(
                    ref=output_ref,
                    title="90s yoga reels asset",
                    summary_text="Generated output for scene sc02.",
                    labels=["reels", "yoga"],
                    mention_tokens=["@reels_asset:gra_plan_001"],
                    mention_text="90s yoga reels asset gra_plan_001",
                    affordance_verbs=["review_generated_reels_asset"],
                )
            ],
            execution_result={"artifact_uri": "s3://demo/gra_plan_001.mp4"},
        ),
    )

    assert response.status == "succeeded"
    assert response.indexed_output_count == 1
    assert response.indexed_relation_count == 3
    assert captured_outputs[0].ref.object_kind == "generated_reels_asset"
    assert [relation.relation_kind for relation in captured_relations] == [
        "generated_from_source",
        "landed_in",
        "generated_with_character",
    ]
    assert captured_relations[0].source_ref.object_kind == "reference"
    assert captured_relations[0].target_ref.object_kind == "generated_reels_asset"
    assert captured_relations[1].source_ref.object_kind == "generated_reels_asset"
    assert captured_relations[1].target_ref.object_kind == "storyboard_scene"
    assert captured_relations[2].source_ref.object_kind == "character_card"
    assert {relation.provenance_type for relation in captured_relations} == {
        "object_action_execution"
    }
    assert {relation.provenance_id for relation in captured_relations} == {"oap_demo"}
    assert captured_relations[0].metadata["execution_result"] == {
        "artifact_uri": "s3://demo/gra_plan_001.mp4"
    }


def test_runtime_closure_wiring_indexes_structured_execution_outputs(monkeypatch):
    captured_outputs = []
    captured_relations = []

    class FakeObjectInstanceStore:
        def upsert_many(self, workspace_id, records):
            assert workspace_id == "ws_demo"
            captured_outputs.extend(records)
            return len(records)

    class FakeRelationStore:
        def upsert_many(self, workspace_id, relations):
            assert workspace_id == "ws_demo"
            captured_relations.extend(relations)
            return len(relations)

    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_instance_registry_store",
        lambda: FakeObjectInstanceStore(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: FakeRelationStore(),
    )
    sys.modules["backend.app.routes.core.workspace.object_runtime"] = object_runtime_module

    output_record = ObjectInstanceRecord(
        ref=_ref("performance_direction", "generated_reels_asset", "gra_exec_001"),
        title="Runtime generated reels asset",
        summary_text="Generated by a completed meeting tool execution.",
        mention_tokens=["@reels_asset:gra_exec_001"],
        mention_text="runtime generated reels asset",
        affordance_verbs=["review_generated_reels_asset"],
    )

    closure = close_object_action_from_execution_result(
        workspace_id="ws_demo",
        execution_id="exec_001",
        inputs={
            "meeting_id": "meeting_demo",
            "object_action_plan": {
                "request_plan": {
                    "action_plan_id": "oap_exec_001",
                    "affordance_verb": "generate_reels_asset",
                },
                "role_assignments": [
                    {"role": "source", "ref": _ref("ig", "reference", "ref_001").model_dump()},
                    {
                        "role": "target",
                        "ref": _ref(
                            "performance_direction",
                            "storyboard_scene",
                            "pd_session_1:latest:sc02",
                        ).model_dump(),
                    },
                    {
                        "role": "character",
                        "ref": _ref(
                            "character_training",
                            "character_card",
                            "card_chacto",
                        ).model_dump(),
                    },
                ],
            },
        },
        execution_result={
            "outputs": {
                "object_action_closure": {
                    "output_records": [output_record.model_dump()],
                }
            }
        },
    )

    assert closure["status"] == "succeeded"
    assert closure["action_plan_id"] == "oap_exec_001"
    assert closure["indexed_output_count"] == 1
    assert closure["indexed_relation_count"] == 3
    assert captured_outputs[0].ref.object_id == "gra_exec_001"
    assert [relation.relation_kind for relation in captured_relations] == [
        "generated_from_source",
        "landed_in",
        "generated_with_character",
    ]


def test_runtime_closure_wiring_marks_planned_execution_without_outputs_as_skipped():
    closure = close_object_action_from_execution_result(
        workspace_id="ws_demo",
        execution_id="exec_002",
        inputs={
            "object_action_plan": {
                "request_plan": {
                    "action_plan_id": "oap_exec_002",
                    "affordance_verb": "generate_reels_asset",
                },
            },
        },
        execution_result={"outputs": {"message": "No addressable output emitted."}},
    )

    assert closure == {
        "status": "skipped",
        "reason": "no_output_records",
        "action_plan_id": "oap_exec_002",
        "execution_id": "exec_002",
    }
