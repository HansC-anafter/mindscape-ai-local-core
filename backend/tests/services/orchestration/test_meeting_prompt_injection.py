"""
Unit tests for A1 prompt injection: lens context, active intents,
and previous decisions injected into agent turn prompts.
"""

import pytest
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from pathlib import Path

from backend.app.services.orchestration.meeting._prompts import MeetingPromptsMixin


@dataclass
class FakeLensNode:
    node_id: str
    node_label: str
    state: object
    effective_scope: str = "global"


class FakeState:
    def __init__(self, value: str):
        self.value = value


class FakeEffectiveLens:
    def __init__(self, nodes=None, preset_name="Default", lens_hash="abc123"):
        self.nodes = nodes or []
        self.global_preset_name = preset_name
        self.hash = lens_hash


class StubEngine(MeetingPromptsMixin):
    """Minimal stub mimicking MeetingEngine attributes used by prompts mixin."""

    def __init__(self):
        self.session = MagicMock()
        self.session.id = "sess-001"
        self.session.workspace_id = "ws-001"
        self.session.agenda = ["Review design"]
        self.session.success_criteria = []
        self.session.lens_id = "lens-001"
        self.session.max_rounds = 5
        self.workspace = MagicMock()
        self.workspace.id = "ws-001"
        self.project_id = "proj-001"
        self.profile_id = "user-001"
        self.store = MagicMock()
        self.session_store = MagicMock()
        self._effective_lens = None
        self._active_intent_ids = []
        self._lens_hash = None
        self._events = []
        self._turn_history = []
        self._project_context = None
        # Locale attribute used by _build_turn_prompt
        self._locale = "en"


class TestBuildLensContext:
    def test_returns_empty_when_no_lens(self):
        engine = StubEngine()
        assert engine._build_lens_context() == ""

    def test_includes_preset_name_and_hash(self):
        engine = StubEngine()
        engine._effective_lens = FakeEffectiveLens(
            preset_name="Creative", lens_hash="deadbeef"
        )
        result = engine._build_lens_context()
        assert "Creative" in result
        assert "deadbeef" in result

    def test_emphasize_nodes_listed(self):
        nodes = [
            FakeLensNode("n1", "Creativity", FakeState("emphasize"), "global"),
            FakeLensNode("n2", "Precision", FakeState("keep"), "workspace"),
            FakeLensNode("n3", "Humor", FakeState("off"), "global"),
        ]
        engine = StubEngine()
        engine._effective_lens = FakeEffectiveLens(nodes=nodes)
        result = engine._build_lens_context()
        assert "Creativity" in result
        assert "Emphasized" in result
        # OFF nodes are excluded from active count
        assert "Total active dimensions: 2" in result

    def test_off_nodes_excluded_from_count(self):
        nodes = [
            FakeLensNode("n1", "A", FakeState("off")),
            FakeLensNode("n2", "B", FakeState("off")),
        ]
        engine = StubEngine()
        engine._effective_lens = FakeEffectiveLens(nodes=nodes)
        result = engine._build_lens_context()
        # No active nodes, but still shows lens name
        assert "Default" in result
        assert "Emphasized" not in result

    def test_uses_node_label_not_node_id(self):
        nodes = [
            FakeLensNode("uuid-123", "My Label", FakeState("emphasize")),
        ]
        engine = StubEngine()
        engine._effective_lens = FakeEffectiveLens(nodes=nodes)
        result = engine._build_lens_context()
        assert "My Label" in result
        assert "uuid-123" not in result


class TestBuildTurnPromptInjection:
    def test_lens_block_injected_when_lens_exists(self):
        engine = StubEngine()
        engine._effective_lens = FakeEffectiveLens(preset_name="Strategic")
        prompt = engine._build_turn_prompt(
            role_id="facilitator",
            round_num=1,
            user_message="Hello",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Active Lens ===" in prompt
        assert "Strategic" in prompt

    def test_no_lens_block_when_no_lens(self):
        engine = StubEngine()
        prompt = engine._build_turn_prompt(
            role_id="facilitator",
            round_num=1,
            user_message="Hello",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Active Lens ===" not in prompt

    def test_intents_block_injected_when_intents_exist(self):
        engine = StubEngine()
        engine._active_intent_ids = ["intent-a", "intent-b"]

        # Mock intent objects returned by store.list_intents
        intent_a = MagicMock()
        intent_a.id = "intent-a"
        intent_a.title = "Deploy landing page"
        intent_a.status = MagicMock(value="active")
        intent_a.progress_percentage = 50

        intent_b = MagicMock()
        intent_b.id = "intent-b"
        intent_b.title = "Research competitors"
        intent_b.status = MagicMock(value="active")
        intent_b.progress_percentage = 20

        engine.store.list_intents.return_value = [intent_a, intent_b]

        prompt = engine._build_turn_prompt(
            role_id="planner",
            round_num=1,
            user_message="Plan something",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Active Intents ===" in prompt
        assert "Deploy landing page" in prompt
        assert "Research competitors" in prompt

    def test_no_intents_block_when_empty(self):
        engine = StubEngine()
        engine._active_intent_ids = []
        prompt = engine._build_turn_prompt(
            role_id="planner",
            round_num=1,
            user_message="Plan",
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )
        assert "=== Active Intents ===" not in prompt


class FakeInstruction:
    """Fake WorkspaceInstruction for testing."""

    def __init__(self, **kwargs):
        self.persona = kwargs.get("persona")
        self.goals = kwargs.get("goals", [])
        self.anti_goals = kwargs.get("anti_goals", [])
        self.style_rules = kwargs.get("style_rules", [])
        self.domain_context = kwargs.get("domain_context")


class FakeBlueprint:
    """Fake WorkspaceBlueprint for testing."""

    def __init__(self, instruction=None, brief=None):
        self.instruction = instruction
        self.brief = brief


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
        # Meeting-specific filtering: no persona, no anti_goals, raw body
        assert "Persona:" not in result
        assert "Don't post content" not in result
        assert "Anti-goals" not in result
        # Preserved fields
        assert "Track trending topics" in result
        assert "Report in zh-TW" in result
        assert "Focus on Instagram Reels" in result
        # Raw body: no === delimiters (caller wraps its own)
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
        """When only persona + goals set, meeting block shows only goals."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(
                persona="You are a brand strategist",
                goals=["Build brand awareness"],
            )
        )
        result = engine._build_workspace_instruction_block()
        # Persona is excluded for meeting
        assert "Persona:" not in result
        assert "brand strategist" not in result
        # Goals preserved
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
        # Has content from instruction goals (persona excluded)
        assert "Do great things" in result
        assert "This brief should not appear" not in result

    def test_empty_instruction_no_brief_fallback(self):
        """Empty instruction with brief does NOT fallback for meeting."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(),  # All fields empty
            brief="Fallback brief text",
        )
        result = engine._build_workspace_instruction_block()
        # Meeting caller: fallback_to_brief=False, so empty result
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
        # Delimiters from helper are NOT present (raw_body=True)
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


class TestFinalMessagesInjection:
    """Verify system role in final messages across all paths."""

    def _make_workspace(self, instruction=None, brief=None):
        return type(
            "W",
            (),
            {
                "id": "ws-final",
                "workspace_blueprint": FakeBlueprint(
                    instruction=instruction, brief=brief
                ),
            },
        )()

    def test_streaming_system_part_contains_instruction(self):
        """Simulate generator.py path: parse_prompt_parts → inject → build_prompt."""
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )
        from backend.app.shared.llm_utils import build_prompt

        ws = self._make_workspace(instruction=FakeInstruction(persona="Streaming AI"))
        # Simulate parse_prompt_parts output
        system_part = "You are a helpful assistant."
        user_part = "Hello"

        ws_block, src = build_workspace_instruction_block(ws, caller="streaming")
        if ws_block:
            system_part = ws_block + "\n\n" + system_part

        messages = build_prompt(system_prompt=system_part, user_prompt=user_part)
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "Streaming AI" in system_msg["content"]
        assert "helpful assistant" in system_msg["content"]

    def test_background_context_str_contains_instruction(self):
        """Simulate chat_orchestrator_service.py path: context_str → messages."""
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws = self._make_workspace(instruction=FakeInstruction(persona="Background AI"))
        context_str = "Some context data"

        ws_block, src = build_workspace_instruction_block(ws, caller="background")
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
        """Meeting path: workspace context is NOT in system role."""
        engine = StubEngine()
        engine.workspace.workspace_blueprint = FakeBlueprint(
            instruction=FakeInstruction(
                persona="Meeting facilitator",
                goals=["Drive decisions"],
            )
        )
        block = engine._build_workspace_instruction_block()
        # Persona is excluded for meeting
        assert "Meeting facilitator" not in block
        # Goals preserved
        assert "Drive decisions" in block

        # Simulate _role_turn: system_content no longer includes ws_instruction
        system_content = "You are the meeting facilitator."
        # No prepend — workspace context goes in user prompt now

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": f"Let's discuss\n{block}"},
        ]
        # System message should NOT contain workspace instruction
        assert "Drive decisions" not in messages[0]["content"]
        assert "Meeting facilitator" not in messages[0]["content"]
        # User message has the context
        assert "Drive decisions" in messages[1]["content"]

    def test_intent_steward_system_prompt_contains_instruction(self):
        """Simulate intent_steward.py path: prepend to system_prompt."""
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )
        from backend.app.shared.llm_utils import build_prompt

        ws = self._make_workspace(
            instruction=FakeInstruction(persona="Intent classifier")
        )
        system_prompt = "You are an Intent Steward AI."

        ws_block, src = build_workspace_instruction_block(ws, caller="intent_steward")
        if ws_block:
            system_prompt = ws_block + "\n\n" + system_prompt

        messages = build_prompt(
            system_prompt=system_prompt, user_prompt="Analyze signals"
        )
        system_msg = next(m for m in messages if m["role"] == "system")
        assert "Intent classifier" in system_msg["content"]
        assert "Intent Steward AI" in system_msg["content"]


class TestToolInventoryCanonicalIds:
    """Fallback tool inventory should surface canonical pack-prefixed IDs."""

    def test_manifest_fallback_uses_pack_prefixed_tool_id(self, monkeypatch):
        engine = StubEngine()
        repo_root = Path(__file__).resolve().parents[4]
        monkeypatch.setenv("APP_DIR", str(repo_root))

        fake_binding_store = MagicMock()
        fake_binding_store.list_bindings_by_workspace.return_value = []

        fake_packs_store = MagicMock()
        fake_packs_store.list_enabled_pack_ids.return_value = ["ig"]

        with patch(
            "backend.app.services.stores.workspace_resource_binding_store.WorkspaceResourceBindingStore",
            return_value=fake_binding_store,
        ), patch(
            "backend.app.services.stores.installed_packs_store.InstalledPacksStore",
            return_value=fake_packs_store,
        ):
            block = engine._build_tool_inventory_block()

        assert "- ig.ig_capture_account_snapshot:" in block
        assert "- ig.ig_fetch_posts:" in block
        assert "- ig_capture_account_snapshot:" not in block


class TestPersonaInjection:
    """Tests for _assemble_system_message persona block (Change 3)."""

    def test_includes_critical_rules(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="critic",
            agent_name="Critic",
            role="critic",
            system_prompt="You identify risks.",
            critical_rules=["NEVER approve without concerns."],
        )
        result = engine._assemble_system_message(role_def)
        assert "NEVER approve without concerns" in result
        assert "Critical rules" in result

    def test_includes_responsibility_boundary(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="exec",
            agent_name="Executor",
            role="executor",
            system_prompt="You convert decisions.",
            responsibility_boundary="execution_only",
        )
        result = engine._assemble_system_message(role_def)
        assert "execution_only" in result
        assert "Stay strictly within" in result

    def test_minimal_role_no_extras(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="test",
            agent_name="Test",
            system_prompt="Basic prompt.",
        )
        result = engine._assemble_system_message(role_def)
        assert result == "Basic prompt."

    def test_full_persona_block_assembly(self):
        engine = StubEngine()
        from backend.app.models.playbook import AgentDefinition

        role_def = AgentDefinition(
            agent_id="planner",
            agent_name="Planner",
            role="planner",
            system_prompt="You propose plans.",
            responsibility_boundary="proposal_and_planning",
            critical_rules=["Rule 1", "Rule 2"],
            communication_style="Structured planner.",
            success_metrics=["Metric A"],
        )
        result = engine._assemble_system_message(role_def)
        assert "You propose plans." in result
        assert "proposal_and_planning" in result
        assert "Rule 1" in result
        assert "Rule 2" in result
        assert "Structured planner." in result
        assert "Metric A" in result
