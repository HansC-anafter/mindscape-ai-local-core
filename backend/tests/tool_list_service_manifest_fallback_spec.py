from backend.app.services.tool_list_service import ToolInfo, ToolListService


class _FakeRegistry:
    def list_tools(self) -> list[str]:
        return ["motion_runtime.mrt_analysis_score_course_motion"]

    def get_tool(self, tool_name: str):
        if tool_name == "motion_runtime.mrt_analysis_score_course_motion":
            return {
                "capability": "motion_runtime",
                "tool_name": "mrt_analysis_score_course_motion",
                "tool_info": {
                    "name": "mrt_analysis_score_course_motion",
                    "description": "Score compact learner motion trajectories.",
                    "category": "capability",
                },
                "backend": "capabilities.motion_runtime.analysis.tools.mrt_analysis_score_course_motion:mrt_analysis_score_course_motion",
            }
        return None


def test_capability_tool_list_merges_manifest_fallback_for_missing_tools(monkeypatch):
    from backend.app.services import capability_registry

    monkeypatch.setattr(capability_registry, "get_registry", lambda: _FakeRegistry())
    monkeypatch.setattr(capability_registry, "load_capabilities", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        ToolListService,
        "_load_manifest_capability_tools",
        lambda self: [
            ToolInfo(
                tool_id="motion_runtime.mrt_analysis_score_course_motion",
                name="mrt_analysis_score_course_motion",
                description="Score compact learner motion trajectories.",
                category="capability",
                source="capability",
                enabled=True,
                metadata={"tool_info": {"tool_name": "mrt_analysis_score_course_motion"}},
            ),
            ToolInfo(
                tool_id="motion_runtime.mrt_analysis_evaluate_motion_attempts",
                name="mrt_analysis_evaluate_motion_attempts",
                description="Evaluate localized motion attempts.",
                category="capability",
                source="capability",
                enabled=True,
                metadata={"tool_info": {"tool_name": "mrt_analysis_evaluate_motion_attempts"}},
            ),
        ],
    )

    tools = ToolListService()._get_capability_tools()
    tool_ids = sorted(tool.tool_id for tool in tools)

    assert tool_ids == [
        "motion_runtime.mrt_analysis_evaluate_motion_attempts",
        "motion_runtime.mrt_analysis_score_course_motion",
    ]
