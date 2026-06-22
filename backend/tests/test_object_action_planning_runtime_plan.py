import pytest

from backend.app.models.object_runtime import ObjectActionPlanRequest
from backend.tests.object_action_planning_runtime_test_support import (
    FakeCatalogRegistry,
    fake_ensure_workspace_exists,
    make_ref,
    object_runtime_module,
)


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
        fake_ensure_workspace_exists,
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
                {"role": "source", "ref": make_ref("ig", "reference", "ref_001")},
                {
                    "role": "target",
                    "ref": make_ref(
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
        fake_ensure_workspace_exists,
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
                {"role": "source", "ref": make_ref("ig", "reference", "ref_001")},
            ],
        ),
    )

    assert response.status == "unsupported"
    assert response.errors[0].code == "affordance_unavailable"
