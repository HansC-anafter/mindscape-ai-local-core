from backend.app.routes.core.capability_packs_core import installed_routes


def test_workspace_tools_route_delegates_after_single_lookup(monkeypatch):
    calls = {"meta": 0, "installed": 0, "builder": 0}
    expected_pack_meta = {
        "id": "demo_pack",
        "code": "demo_pack",
        "ui_components": [],
        "workspace_tools": [],
    }
    expected = [{"tool_key": "demo_pack:demo_tool"}]

    def fake_get_pack_meta_by_code(capability_code):
        calls["meta"] += 1
        assert capability_code == "demo_pack"
        return expected_pack_meta

    def fake_get_installed_pack_ids():
        calls["installed"] += 1
        return {"demo_pack"}

    def fake_build_capability_workspace_tools(
        *,
        capability_code,
        pack_meta: dict,
        format_ui_component,
    ):
        calls["builder"] += 1
        assert capability_code == "demo_pack"
        assert pack_meta == expected_pack_meta
        assert format_ui_component is installed_routes._format_ui_component_for_response
        return expected

    monkeypatch.setattr(
        installed_routes,
        "_get_pack_meta_by_code",
        fake_get_pack_meta_by_code,
    )
    monkeypatch.setattr(
        installed_routes,
        "_get_installed_pack_ids",
        fake_get_installed_pack_ids,
    )
    monkeypatch.setattr(
        installed_routes,
        "build_capability_workspace_tools",
        fake_build_capability_workspace_tools,
    )

    assert installed_routes.get_capability_workspace_tools("demo_pack") == expected
    assert calls == {"meta": 1, "installed": 1, "builder": 1}
