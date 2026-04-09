from backend.app.system_capabilities.world_memory_core.services.context_export_facade import (
    ContextExportFacade,
)


def test_world_card_projection_text_includes_zone():
    result = ContextExportFacade().export_context(
        workspace_id="ws-demo",
        receipt={
            "scene_id": "scene.demo",
            "current_zone": "window_side",
            "visible_objects": ["window_light"],
        },
    )

    assert "window_side" in result["world_card_text"]
