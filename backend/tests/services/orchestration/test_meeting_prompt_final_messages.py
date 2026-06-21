from meeting_prompt_injection_test_support import (
    FakeBlueprint,
    FakeInstruction,
    StubEngine,
    make_workspace,
)


class TestFinalMessagesInjection:
    """Verify system role in final messages across all paths."""

    def test_streaming_system_part_contains_instruction(self):
        """Simulate generator.py path: parse_prompt_parts, inject, build_prompt."""
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )
        from backend.app.shared.llm_utils import build_prompt

        ws = make_workspace(instruction=FakeInstruction(persona="Streaming AI"))
        system_part = "You are a helpful assistant."
        user_part = "Hello"

        ws_block, _source = build_workspace_instruction_block(ws, caller="streaming")
        if ws_block:
            system_part = ws_block + "\n\n" + system_part

        messages = build_prompt(system_prompt=system_part, user_prompt=user_part)
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "Streaming AI" in system_msg["content"]
        assert "helpful assistant" in system_msg["content"]

    def test_background_context_str_contains_instruction(self):
        """Simulate chat_orchestrator_service.py path: context_str to messages."""
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = make_workspace(instruction=FakeInstruction(persona="Background AI"))
        context_str = "Some context data"

        ws_block, _source = build_workspace_instruction_block(ws, caller="background")
        if ws_block:
            context_str = ws_block + "\n\n" + context_str

        messages = []
        if context_str:
            messages.append({"role": "system", "content": context_str})
        messages.append({"role": "user", "content": "Test"})

        system_msg = messages[0]
        assert system_msg["role"] == "system"
        assert "Background AI" in system_msg["content"]
        assert "Some context data" in system_msg["content"]

    def test_meeting_workspace_context_not_in_system(self):
        """Meeting path: workspace context is not in system role."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(
                persona="Meeting facilitator",
                goals=["Drive decisions"],
            )
        )
        block = engine._build_workspace_instruction_block()
        assert "Meeting facilitator" not in block
        assert "Drive decisions" in block

        system_content = "You are the meeting facilitator."
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Let's discuss\n{block}"},
        ]
        assert "Drive decisions" not in messages[0]["content"]
        assert "Meeting facilitator" not in messages[0]["content"]
        assert "Drive decisions" in messages[1]["content"]

    def test_intent_steward_system_prompt_contains_instruction(self):
        """Simulate intent_steward.py path: prepend to system_prompt."""
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )
        from backend.app.shared.llm_utils import build_prompt

        ws = make_workspace(instruction=FakeInstruction(persona="Intent classifier"))
        system_prompt = "You are an Intent Steward AI."

        ws_block, _source = build_workspace_instruction_block(ws, caller="intent_steward")
        if ws_block:
            system_prompt = ws_block + "\n\n" + system_prompt

        messages = build_prompt(
            system_prompt=system_prompt, user_prompt="Analyze signals"
        )
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "Intent classifier" in system_msg["content"]
        assert "Intent Steward AI" in system_msg["content"]
