import pytest

from meeting_prompt_injection_test_support import (
    FakeBlueprint,
    FakeInstruction,
    StubEngine,
)


class TestWorkspaceInstructionInjection:
    """Tests for workspace instruction block building and injection."""

    def test_full_instruction_block(self):
        """Meeting block excludes persona and anti_goals."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(
                persona="You are an IG community analyst",
                goals=["Track trending topics", "Identify engagement patterns"],
                anti_goals=["Don't post content", "Don't make purchases"],
                style_rules=["Report in zh-TW", "Use data-driven language"],
                domain_context="Focus on Instagram Reels and Stories.",
            )
        )
        result = engine._build_workspace_instruction_block()
        assert "Persona:" not in result
        assert "Don't post content" not in result
        assert "Anti-goals" not in result
        assert "Track trending topics" in result
        assert "Report in zh-TW" in result
        assert "Focus on Instagram Reels" in result
        assert "=== Workspace Instruction ===" not in result
        assert "=== End Instruction ===" not in result

    def test_fallback_to_brief_disabled_for_meeting(self):
        """Meeting caller never uses brief fallback."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            brief="This workspace tracks IG topics."
        )
        result = engine._build_workspace_instruction_block()
        assert result == ""

    def test_empty_when_no_blueprint(self):
        engine = StubEngine()
        engine.workspace.workspace_blueprint = None
        result = engine._build_workspace_instruction_block()
        assert result == ""

    def test_empty_when_no_workspace(self):
        engine = StubEngine()
        engine.workspace = None
        result = engine._build_workspace_instruction_block()
        assert result == ""

    def test_partial_fields_only_persona_and_goals(self):
        """When only persona and goals are set, meeting block shows only goals."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(
                persona="You are a brand strategist",
                goals=["Build brand awareness"],
            )
        )
        result = engine._build_workspace_instruction_block()
        assert "Persona:" not in result
        assert "brand strategist" not in result
        assert "Build brand awareness" in result
        assert "Anti-goals" not in result
        assert "Style:" not in result
        assert "Domain context:" not in result

    def test_instruction_has_priority_over_brief(self):
        """Instruction fields used; brief ignored for meeting."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(
                persona="I am the AI",
                goals=["Do great things"],
            ),
            brief="This brief should not appear",
        )
        result = engine._build_workspace_instruction_block()
        assert "Do great things" in result
        assert "This brief should not appear" not in result

    def test_empty_instruction_no_brief_fallback(self):
        """Empty instruction with brief does not fallback for meeting."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(),
            brief="Fallback brief text",
        )
        result = engine._build_workspace_instruction_block()
        assert result == ""

    def test_meeting_workspace_context_in_user_prompt(self):
        """Workspace context appears in _build_turn_prompt output."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(
                domain_context="Yoga studio in Taipei",
                style_rules=["Use formal Chinese"],
            )
        )
        prompt = engine._build_turn_prompt(
            role_id="facilitator",
            round_num=1,
            user_message="Analyze IG account",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Workspace Context (Reference) ===" in prompt
        assert "=== End Context ===" in prompt
        assert "does NOT override your deliberation role" in prompt
        assert "Yoga studio in Taipei" in prompt
        assert "Use formal Chinese" in prompt
        assert "=== Workspace Instruction ===" not in prompt


class TestWorkspaceInstructionModel:
    """Tests for WorkspaceInstruction Pydantic model validation."""

    def test_basic_creation(self):
        from backend.app.models.workspace_blueprint import WorkspaceInstruction

        instr = WorkspaceInstruction(
            persona="You are a test AI",
            goals=["Goal 1", "Goal 2"],
            anti_goals=["Anti 1"],
        )
        assert instr.persona == "You are a test AI"
        assert len(instr.goals) == 2
        assert instr.version == 1

    def test_persona_max_length(self):
        from backend.app.models.workspace_blueprint import WorkspaceInstruction
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WorkspaceInstruction(persona="x" * 501)

    def test_domain_context_max_length(self):
        from backend.app.models.workspace_blueprint import WorkspaceInstruction
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            WorkspaceInstruction(domain_context="x" * 2001)

    def test_empty_instruction_valid(self):
        from backend.app.models.workspace_blueprint import WorkspaceInstruction

        instr = WorkspaceInstruction()
        assert instr.persona is None
        assert instr.goals == []
        assert instr.version == 1

    def test_jsonb_roundtrip(self):
        from backend.app.models.workspace_blueprint import (
            WorkspaceBlueprint,
            WorkspaceInstruction,
        )

        bp = WorkspaceBlueprint(
            instruction=WorkspaceInstruction(
                persona="Test AI",
                goals=["G1"],
                anti_goals=["A1"],
            ),
            brief="Legacy brief",
        )
        dumped = bp.model_dump()
        restored = WorkspaceBlueprint.model_validate(dumped)
        assert restored.instruction is not None
        assert restored.instruction.persona == "Test AI"
        assert restored.brief == "Legacy brief"


class TestUnifiedHelper:
    """Tests for workspace_instruction_helper.build_workspace_instruction_block."""

    def test_full_instruction_returns_block_and_source(self):
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = type(
            "W",
            (),
            {
                "id": "ws-1",
                "workspace_blueprint": FakeBlueprint(
                    instruction=FakeInstruction(
                        persona="IG analyst",
                        goals=["Track topics"],
                        anti_goals=["No posting"],
                        style_rules=["zh-TW"],
                        domain_context="Instagram focus",
                    )
                ),
            },
        )()
        block, source = build_workspace_instruction_block(ws, caller="test")
        assert source == "instruction"
        assert "=== Workspace Instruction ===" in block
        assert "Persona: IG analyst" in block
        assert "Track topics" in block

    def test_fallback_to_brief_returns_brief_source(self):
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = type(
            "W",
            (),
            {
                "id": "ws-2",
                "workspace_blueprint": FakeBlueprint(brief="Legacy brief text"),
            },
        )()
        block, source = build_workspace_instruction_block(ws, caller="test")
        assert source == "brief"
        assert "=== Workspace Brief ===" in block
        assert "Legacy brief text" in block

    def test_empty_instruction_falls_back_to_brief(self):
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = type(
            "W",
            (),
            {
                "id": "ws-3",
                "workspace_blueprint": FakeBlueprint(
                    instruction=FakeInstruction(),
                    brief="Fallback brief",
                ),
            },
        )()
        block, source = build_workspace_instruction_block(ws, caller="test")
        assert source == "brief"
        assert "Fallback brief" in block

    def test_no_blueprint_returns_none_source(self):
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = type("W", (), {"id": "ws-4", "workspace_blueprint": None})()
        block, source = build_workspace_instruction_block(ws, caller="test")
        assert source == "none"
        assert block == ""

    def test_none_workspace_returns_none_source(self):
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        block, source = build_workspace_instruction_block(None, caller="test")
        assert source == "none"
        assert block == ""

    def test_instruction_priority_over_brief(self):
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = type(
            "W",
            (),
            {
                "id": "ws-5",
                "workspace_blueprint": FakeBlueprint(
                    instruction=FakeInstruction(persona="Expert"),
                    brief="Should be ignored",
                ),
            },
        )()
        block, source = build_workspace_instruction_block(ws, caller="test")
        assert source == "instruction"
        assert "Expert" in block
        assert "Should be ignored" not in block

    def test_partial_fields_only_goals(self):
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = type(
            "W",
            (),
            {
                "id": "ws-6",
                "workspace_blueprint": FakeBlueprint(
                    instruction=FakeInstruction(goals=["G1", "G2"]),
                ),
            },
        )()
        block, source = build_workspace_instruction_block(ws, caller="test")
        assert source == "instruction"
        assert "G1" in block
        assert "Persona" not in block
