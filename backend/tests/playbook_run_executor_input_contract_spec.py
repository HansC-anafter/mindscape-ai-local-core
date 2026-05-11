from types import SimpleNamespace

import pytest

from backend.app.services.playbook_run_executor import PlaybookRunExecutor


def _playbook_run(inputs):
    return SimpleNamespace(playbook_json=SimpleNamespace(inputs=inputs))


def test_playbook_input_contract_applies_defaults_for_missing_values():
    normalized = PlaybookRunExecutor._apply_playbook_input_contract(
        "ig_batch_pin_references",
        _playbook_run(
            {
                "workspace_id": SimpleNamespace(required=True, default=None),
                "target_handle": SimpleNamespace(required=True, default=None),
                "target_count": SimpleNamespace(required=False, default=100),
                "source_mode": SimpleNamespace(required=False, default="browser"),
            }
        ),
        {
            "workspace_id": "ws-1",
            "target_handle": "target",
            "target_count": None,
        },
    )

    assert normalized["target_count"] == 100
    assert normalized["source_mode"] == "browser"
    assert normalized["target_handle"] == "target"


def test_playbook_input_contract_rejects_missing_required_values():
    with pytest.raises(
        ValueError,
        match="Missing required playbook inputs for ig_analyze_pinned_reference: reference_id",
    ):
        PlaybookRunExecutor._apply_playbook_input_contract(
            "ig_analyze_pinned_reference",
            _playbook_run(
                {
                    "workspace_id": {"required": True, "default": None},
                    "reference_id": {"required": True, "default": None},
                    "analysis_profile": {"required": False, "default": "visual_anatomy"},
                }
            ),
            {
                "workspace_id": "ws-1",
                "reference_id": "",
            },
        )


def test_playbook_input_contract_copies_mutable_defaults():
    playbook_run = _playbook_run(
        {
            "workspace_id": {"required": True, "default": None},
            "target_handle": {"required": True, "default": None},
            "filters": {"required": False, "default": {"mode": "all"}},
        }
    )

    first = PlaybookRunExecutor._apply_playbook_input_contract(
        "demo",
        playbook_run,
        {"workspace_id": "ws-1", "target_handle": "target"},
    )
    second = PlaybookRunExecutor._apply_playbook_input_contract(
        "demo",
        playbook_run,
        {"workspace_id": "ws-1", "target_handle": "target"},
    )
    first["filters"]["mode"] = "changed"

    assert second["filters"] == {"mode": "all"}
