import pytest

from backend.app.services.orchestration.task_decomposer import TaskDecomposer


class _FakeMeetingAdapter:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def chat_completion(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return self.response


@pytest.mark.asyncio
async def test_task_decomposer_uses_supplied_meeting_adapter_directly() -> None:
    adapter = _FakeMeetingAdapter(
        """
        [
          {
            "id": "phase_0",
            "name": "Generate storyboard",
            "description": "Run the selected storyboard playbook.",
            "preferred_engine": "playbook:pd_storyboard_gen",
            "depends_on": [],
            "tool_name": null,
            "input_params": {},
            "target_workspace_id": null
          }
        ]
        """
    )
    decomposer = TaskDecomposer(llm_adapter=adapter, model_name="codex_cli")

    phases = await decomposer.decompose(
        decision="Create a 90s IG reels storyboard.",
        action_items=[
            {
                "title": "Generate storyboard",
                "description": "Use real IG references.",
                "playbook_code": "pd_storyboard_gen",
            },
            {
                "title": "Judge scenes",
                "description": "Review each scene.",
                "tool_name": "performance_direction.pd_storyboard_quality_judge",
            },
        ],
        available_playbooks="pd_storyboard_gen",
        available_tools="performance_direction.pd_storyboard_quality_judge",
        force=True,
    )

    assert len(adapter.calls) == 1
    assert adapter.calls[0]["kwargs"]["model"] == "codex_cli"
    assert phases[0].preferred_engine == "playbook:pd_storyboard_gen"
