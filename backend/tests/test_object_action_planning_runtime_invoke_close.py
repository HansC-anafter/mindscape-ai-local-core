import pytest

from backend.app.models.object_runtime import (
    ObjectActionClosureRequest,
    ObjectActionInvokeRequest,
    ObjectInstanceRecord,
)
from backend.tests.object_action_planning_runtime_test_support import (
    CaptureObjectInstanceStore,
    CaptureRelationStore,
    CaptureTasksStore,
    FakeCatalogRegistry,
    build_role_assignments,
    fake_ensure_workspace_exists,
    install_object_runtime_module_alias,
    make_ref,
    make_reels_output_record,
    object_runtime_module,
)


@pytest.mark.asyncio
async def test_object_action_invoke_runs_executor_closes_outputs_and_persists_task(
    monkeypatch,
):
    captured_outputs = []
    captured_relations = []
    captured_tasks = []
    output_record = make_reels_output_record()

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

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        fake_ensure_workspace_exists,
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
        lambda: CaptureObjectInstanceStore(captured_outputs),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: CaptureRelationStore(captured_relations),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_tasks_store",
        lambda: CaptureTasksStore(captured_tasks),
    )
    install_object_runtime_module_alias()

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
                "role_assignments": build_role_assignments(),
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

    monkeypatch.setattr(
        object_runtime_module,
        "_ensure_workspace_exists",
        fake_ensure_workspace_exists,
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_catalog_registry",
        lambda: FakeCatalogRegistry(),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_instance_registry_store",
        lambda: CaptureObjectInstanceStore(captured_outputs),
    )
    monkeypatch.setattr(
        object_runtime_module,
        "_get_object_relation_registry_store",
        lambda: CaptureRelationStore(captured_relations),
    )

    output_ref = make_ref(
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
                {"role": "source", "ref": make_ref("ig", "reference", "ref_001")},
                {
                    "role": "target",
                    "ref": make_ref(
                        "performance_direction",
                        "storyboard_scene",
                        "pd_session_1:latest:sc02",
                    ),
                },
                {
                    "role": "character",
                    "ref": make_ref("character_training", "character_card", "card_chacto"),
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
