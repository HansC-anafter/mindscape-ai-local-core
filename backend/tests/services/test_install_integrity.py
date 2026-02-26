"""Unit tests for install integrity dirty-state detection."""

import json
from pathlib import Path

from backend.app.services.install_integrity import (
    MANIFEST_FILENAME,
    check_dirty_state,
    compute_dir_hashes,
    save_install_manifest,
)


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_compute_dir_hashes_missing_dir_returns_empty(tmp_path: Path):
    hashes = compute_dir_hashes(tmp_path / "missing")
    assert hashes == {}


def test_compute_dir_hashes_empty_dir_returns_empty(tmp_path: Path):
    hashes = compute_dir_hashes(tmp_path)
    assert hashes == {}


def test_compute_dir_hashes_skips_install_manifest_file(tmp_path: Path):
    _write(tmp_path / "a.txt", "one")
    _write(tmp_path / MANIFEST_FILENAME, "{}")
    hashes = compute_dir_hashes(tmp_path)
    assert "a.txt" in hashes
    assert MANIFEST_FILENAME not in hashes


def test_compute_dir_hashes_skips_cache_and_compiled_files(tmp_path: Path):
    _write(tmp_path / "module.py", "print('ok')\n")
    _write(tmp_path / "__pycache__" / "module.cpython-311.pyc", "bin")
    _write(tmp_path / "artifact.pyc", "bin")
    _write(tmp_path / "artifact.pyo", "bin")
    _write(tmp_path / ".DS_Store", "bin")
    hashes = compute_dir_hashes(tmp_path)
    assert list(hashes.keys()) == ["module.py"]


def test_compute_dir_hashes_uses_relative_nested_paths(tmp_path: Path):
    _write(tmp_path / "tools" / "schemas" / "input.json", '{"type":"object"}')
    hashes = compute_dir_hashes(tmp_path)
    assert "tools/schemas/input.json" in hashes


def test_save_install_manifest_persists_expected_fields(tmp_path: Path):
    _write(tmp_path / "file.txt", "v1")
    hashes = compute_dir_hashes(tmp_path)
    manifest_path = save_install_manifest(tmp_path, "1.2.3", hashes)
    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert saved["version"] == "1.2.3"
    assert saved["file_count"] == 1
    assert saved["files"]["file.txt"].startswith("sha256:")
    assert "installed_at" in saved


def test_check_dirty_state_without_manifest_is_clean(tmp_path: Path):
    _write(tmp_path / "file.txt", "v1")
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is False
    assert result.modified == []
    assert result.added == []
    assert result.deleted == []


def test_check_dirty_state_unchanged_files_is_clean(tmp_path: Path):
    _write(tmp_path / "file.txt", "v1")
    save_install_manifest(tmp_path, "1.0.0", compute_dir_hashes(tmp_path))
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is False


def test_check_dirty_state_detects_modified_files(tmp_path: Path):
    file_path = tmp_path / "file.txt"
    _write(file_path, "v1")
    save_install_manifest(tmp_path, "1.0.0", compute_dir_hashes(tmp_path))
    _write(file_path, "v2")
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is True
    assert result.modified == ["file.txt"]


def test_check_dirty_state_detects_added_files(tmp_path: Path):
    _write(tmp_path / "file.txt", "v1")
    save_install_manifest(tmp_path, "1.0.0", compute_dir_hashes(tmp_path))
    _write(tmp_path / "new.txt", "new")
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is True
    assert result.added == ["new.txt"]


def test_check_dirty_state_detects_deleted_files(tmp_path: Path):
    file_path = tmp_path / "file.txt"
    _write(file_path, "v1")
    save_install_manifest(tmp_path, "1.0.0", compute_dir_hashes(tmp_path))
    file_path.unlink()
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is True
    assert result.deleted == ["file.txt"]


def test_check_dirty_state_detects_mixed_changes(tmp_path: Path):
    _write(tmp_path / "a.txt", "a1")
    _write(tmp_path / "b.txt", "b1")
    save_install_manifest(tmp_path, "1.0.0", compute_dir_hashes(tmp_path))
    _write(tmp_path / "a.txt", "a2")
    (tmp_path / "b.txt").unlink()
    _write(tmp_path / "c.txt", "c1")
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is True
    assert result.modified == ["a.txt"]
    assert result.deleted == ["b.txt"]
    assert result.added == ["c.txt"]


def test_check_dirty_state_fail_closed_on_corrupt_manifest(tmp_path: Path):
    _write(tmp_path / "file.txt", "v1")
    save_install_manifest(tmp_path, "1.0.0", compute_dir_hashes(tmp_path))
    _write(tmp_path / MANIFEST_FILENAME, "{invalid json")
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is True
    assert result.modified == ["<manifest unreadable — cannot determine changes>"]
    assert result.installed_version == "<unknown>"


def test_check_dirty_state_fail_closed_when_manifest_path_is_directory(tmp_path: Path):
    _write(tmp_path / "file.txt", "v1")
    (tmp_path / MANIFEST_FILENAME).mkdir(parents=True, exist_ok=True)
    result = check_dirty_state(tmp_path)
    assert result.is_dirty is True
    assert result.modified == ["<manifest unreadable — cannot determine changes>"]
