from unittest.mock import MagicMock

from meeting_prompt_injection_test_support import (
    FakeEffectiveLens,
    FakeLensNode,
    FakeState,
    StubEngine,
    make_native_spatial_storyboard_engine,
)


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
        assert "Total active dimensions: 2" in result

    def test_off_nodes_excluded_from_count(self):
        nodes = [
            FakeLensNode("n1", "A", FakeState("off")),
            FakeLensNode("n2", "B", FakeState("off")),
        ]
        engine = StubEngine()
        engine._effective_lens = FakeEffectiveLens(nodes=nodes)
        result = engine._build_lens_context()
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

    def test_native_spatial_prompt_injects_storyboard_benchmark_block(self):
        engine = make_native_spatial_storyboard_engine()

        prompt = engine._build_turn_prompt(
            role_id="planner",
            round_num=1,
            user_message=(
                "Design a native spatial tray handoff scene for downstream replay"
            ),
            decision=None,
            planner_proposals=[],
            critic_notes=[],
        )

        assert "=== Handoff Instructions ===" in prompt
        assert "=== Storyboard Acceptance Benchmark ===" in prompt
        assert "actor.attendant" in prompt
        assert "beat.entry_with_tray" in prompt
        assert "Entry with tray" in prompt
