from pathlib import Path

from backend.app.services.install_integrity import (
    DirtyCheckResult,
    build_dirty_review_payload,
)


def test_dirty_review_marks_candidate_that_preserves_local_content(tmp_path: Path):
    installed = tmp_path / "installed"
    candidate = tmp_path / "candidate"
    installed.mkdir()
    candidate.mkdir()
    (installed / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    (candidate / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    payload = build_dirty_review_payload(
        installed,
        candidate,
        DirtyCheckResult(is_dirty=True, modified=["module.py"]),
    )

    assert payload["all_local_changes_preserved"] is True
    assert payload["files"][0]["candidate_state"] == "matches_local"
    assert payload["files"][0]["text_diff"] == []


def test_dirty_review_exposes_candidate_difference_without_truncating_file_scope(
    tmp_path: Path,
):
    installed = tmp_path / "installed"
    candidate = tmp_path / "candidate"
    installed.mkdir()
    candidate.mkdir()
    (installed / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    (candidate / "module.py").write_text("VALUE = 3\n", encoding="utf-8")

    payload = build_dirty_review_payload(
        installed,
        candidate,
        DirtyCheckResult(is_dirty=True, modified=["module.py"]),
    )

    assert payload["file_count"] == 1
    assert payload["all_local_changes_preserved"] is False
    assert payload["files"][0]["candidate_state"] == "differs_from_local"
    assert "-VALUE = 2" in payload["files"][0]["text_diff"]
    assert "+VALUE = 3" in payload["files"][0]["text_diff"]


def test_dirty_review_marks_locally_added_file_omitted_by_candidate(tmp_path: Path):
    installed = tmp_path / "installed"
    candidate = tmp_path / "candidate"
    installed.mkdir()
    candidate.mkdir()
    (installed / "local_fix.py").write_text("FIX = True\n", encoding="utf-8")

    payload = build_dirty_review_payload(
        installed,
        candidate,
        DirtyCheckResult(is_dirty=True, added=["local_fix.py"]),
    )

    assert payload["all_local_changes_preserved"] is False
    assert payload["files"][0]["candidate_state"] == "absent"
    assert payload["files"][0]["local_change_preserved"] is False
