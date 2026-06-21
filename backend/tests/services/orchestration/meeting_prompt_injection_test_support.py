from dataclasses import dataclass
from unittest.mock import MagicMock

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
        self._locale = "en"


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


def make_workspace(instruction=None, brief=None):
    return type(
        "W",
        (),
        {
            "id": "ws-final",
            "workspace_blueprint": FakeBlueprint(instruction=instruction, brief=brief),
        },
    )()


def make_native_spatial_storyboard_engine():
    engine = StubEngine()
    engine.executor_runtime = "codex_cli"
    engine._requires_full_deliberation_review = MagicMock(return_value=True)
    engine.session.agenda = ["Single-camera tray delivery"]
    engine.session.metadata = {
        "request_contract": {
            "human_instructions": (
                "Use the storyboard benchmark as a hard acceptance target."
            ),
            "governance_constraints": {
                "spatial_schedule": {
                    "storyboard_acceptance": {
                        "storyboard_id": "story_counter_tray_single_cam_delivery_v1",
                        "intent_summary": (
                            "Single-camera indoor countertop tray delivery"
                        ),
                        "acceptance_checks": {
                            "required_actor_ids": ["actor.attendant"],
                            "required_performance_beats": [
                                "beat.entry_with_tray",
                                "beat.align_to_counter",
                            ],
                            "required_segment_titles": [
                                "Entry with tray",
                                "Align to counter",
                            ],
                        },
                        "storyboard_cards": [
                            {
                                "card_id": "card.entry_with_tray",
                                "title": "Entry with tray",
                                "required_segment_title": "Entry with tray",
                                "required_beat_ids": ["beat.entry_with_tray"],
                            }
                        ],
                    }
                }
            },
        }
    }
    return engine
