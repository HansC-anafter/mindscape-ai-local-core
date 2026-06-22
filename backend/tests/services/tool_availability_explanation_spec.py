from backend.app.services.tools.tool_availability_explanation import (
    attach_tool_availability_explanations,
    build_capability_api_activation_explanation,
)


def test_tool_availability_explanation_marks_workspace_binding():
    results = attach_tool_availability_explanations(
        [{"tool_id": "ig.analyze", "display_name": "Analyze"}],
        workspace_id="ws-1",
        source="tool_rag",
        reason="workspace_binding_allowed",
        workspace_binding_applied=True,
    )

    explanation = results[0]["availability_explanation"]
    assert explanation["available"] is True
    assert explanation["workspace_id"] == "ws-1"
    assert explanation["reason"] == "workspace_binding_allowed"
    assert explanation["workspace_binding_applied"] is True
    assert explanation["rank"] == 1


def test_capability_activation_explanation_lists_routes_and_conflicts():
    explanation = build_capability_api_activation_explanation(
        capability_code="demo",
        status="failed",
        reason="route_conflict",
        expected_routes={("GET", "/demo")},
        conflicts={("GET", "/demo")},
    )

    assert explanation["capability_code"] == "demo"
    assert explanation["status"] == "failed"
    assert explanation["expected_routes"] == [{"method": "GET", "path": "/demo"}]
    assert explanation["conflicts"] == [{"method": "GET", "path": "/demo"}]
