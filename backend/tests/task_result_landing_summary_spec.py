from backend.app.services.stores.postgres.workspaces_store import (
    PostgresWorkspacesStore,
)
from backend.app.services.task_result_landing import TaskResultLandingService


def test_extract_result_summary_compacts_nested_storyboard_payload():
    summary = TaskResultLandingService._extract_result_summary(
        {
            "steps": {
                "generate": {
                    "outputs": {
                        "payload": {
                            "storyboard": {
                                "storyboard_id": "sb_123",
                                "scenes": [{"scene_id": "s1"}, {"scene_id": "s2"}],
                                "raw": "x" * 5000,
                            },
                            "created_count": 2,
                        }
                    }
                }
            }
        }
    )

    assert "storyboard=storyboard_id=sb_123, scenes=2" in summary
    assert "created_count=2" in summary
    assert len(summary) <= 500
    assert "xxxxx" not in summary


def test_extract_result_summary_bounds_generic_nested_values():
    summary = TaskResultLandingService._extract_result_summary(
        {
            "steps": {
                "analyze": {
                    "outputs": {
                        "payload": {
                            "profile": {
                                "summary": "a" * 1000,
                                "score": 0.91,
                                "tags": ["one", "two"],
                            },
                            "items": list(range(20)),
                        }
                    }
                }
            }
        }
    )

    assert "score=0.91" in summary
    assert "items=list(count=20)" in summary
    assert len(summary) <= 500


def test_workspace_data_source_entry_compacts_last_result_summary():
    entry = PostgresWorkspacesStore._compact_data_source_entry(
        {
            "total_runs": 3,
            "last_result_summary": "x" * 700,
            "produces": [{"type": "artifact"}],
        }
    )

    assert entry["total_runs"] == 3
    assert entry["produces"] == [{"type": "artifact"}]
    assert len(entry["last_result_summary"]) == 500
    assert entry["last_result_summary"].endswith("...")
