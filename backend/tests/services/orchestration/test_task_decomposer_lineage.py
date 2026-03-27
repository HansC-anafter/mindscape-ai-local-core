from backend.app.services.orchestration.task_decomposer import TaskDecomposer


def test_passthrough_sets_source_intent_id_from_action_item():
    decomposer = TaskDecomposer()

    phases = decomposer._passthrough(
        [
            {
                "intent_id": "intent-1",
                "title": "Draft brief",
                "description": "Create the first draft",
            }
        ]
    )

    assert len(phases) == 1
    assert phases[0].id == "intent-1"
    assert phases[0].source_intent_id == "intent-1"


def test_parse_phases_preserves_source_intent_id_from_llm_output():
    decomposer = TaskDecomposer()

    phases = decomposer._parse_phases(
        [
            {
                "id": "phase_0",
                "source_intent_id": "intent-2",
                "name": "Finalize delivery",
                "preferred_engine": "tool:review.record_review_completed",
                "tool_name": "review.record_review_completed",
            }
        ],
        action_items=[
            {"intent_id": "intent-1", "title": "Plan"},
            {"intent_id": "intent-2", "title": "Finalize"},
        ],
    )

    assert len(phases) == 1
    assert phases[0].id == "phase_0"
    assert phases[0].source_intent_id == "intent-2"


def test_parse_phases_falls_back_to_phase_id_when_it_matches_intent_id():
    decomposer = TaskDecomposer()

    phases = decomposer._parse_phases(
        [
            {
                "id": "intent-3",
                "name": "Direct passthrough phase",
                "preferred_engine": "playbook:project_breakdown",
            }
        ],
        action_items=[{"intent_id": "intent-3", "title": "Break down project"}],
    )

    assert len(phases) == 1
    assert phases[0].source_intent_id == "intent-3"
