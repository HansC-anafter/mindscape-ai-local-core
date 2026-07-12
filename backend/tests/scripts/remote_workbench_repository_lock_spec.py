from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from remote_workbench_authorization_cutover.io import CutoverError
from remote_workbench_authorization_cutover import repository


HEAD = "a" * 40


class GitExecutor:
    def __init__(self, paths: dict[str, Path]) -> None:
        self.paths = paths
        self.branch_override: dict[Path, str] = {}
        self.head_override: dict[Path, str] = {}
        self.status_override: dict[Path, str] = {}

    def run(self, args, **_kwargs) -> str:
        assert args[:2] == ["git", "-C"]
        repo = Path(args[2])
        command = args[3:]
        if command == ["rev-parse", "--path-format=absolute", "--git-common-dir"]:
            local_repos = {self.paths["canonical_local"], self.paths["local_task"]}
            canonical = (
                self.paths["canonical_local"]
                if repo in local_repos
                else self.paths["canonical_cloud"]
            )
            return str(canonical / ".git")
        if command == ["rev-parse", "--show-toplevel"]:
            return str(repo)
        if command == ["branch", "--show-current"]:
            default = (
                repository.LOCAL_TASK_BRANCH
                if repo == self.paths["local_task"]
                else repository.CLOUD_TASK_BRANCH
            )
            return self.branch_override.get(repo, default)
        if command[:2] == ["status", "--porcelain=v1"]:
            return self.status_override.get(repo, "")
        if command == ["rev-parse", "HEAD"]:
            return self.head_override.get(repo, HEAD)
        if command[:2] == ["merge-base", "--is-ancestor"]:
            return ""
        raise AssertionError(command)


def _tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    workspace = tmp_path / "workspace"
    canonical_local = workspace / "mindscape-ai-local-core"
    canonical_cloud = workspace / "mindscape-ai-cloud"
    local_task = workspace / ".worktrees" / "local-task"
    cloud_task = workspace / ".worktrees" / "cloud-task"
    for path in (canonical_local, canonical_cloud, local_task, cloud_task):
        path.mkdir(parents=True)
    (canonical_local / ".git").mkdir()
    (canonical_cloud / ".git").mkdir()
    (canonical_local / ".venv").mkdir()
    monkeypatch.setattr(repository, "LOCAL_TASK_DIRECTORY", "local-task")
    monkeypatch.setattr(repository, "CLOUD_TASK_DIRECTORY", "cloud-task")
    return {
        "canonical_local": canonical_local,
        "canonical_cloud": canonical_cloud,
        "local_task": local_task,
        "cloud_task": cloud_task,
    }


def test_repository_lock_uses_task_only_as_evidence_and_returns_canonical_sources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _tree(tmp_path, monkeypatch)
    locked = repository.lock_phase06_repositories(
        script_repo_root=paths["canonical_local"],
        runner_cwd=paths["canonical_local"],
        cloud_worktree=paths["cloud_task"],
        executor=GitExecutor(paths),
        python_prefix=paths["canonical_local"] / ".venv",
    )

    assert locked.canonical_local == paths["canonical_local"]
    assert locked.canonical_cloud == paths["canonical_cloud"]
    assert locked.local_task == paths["local_task"]
    assert locked.cloud_task == paths["cloud_task"]


def test_repository_lock_rejects_wrong_clean_path_branch_head_and_symlink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _tree(tmp_path, monkeypatch)
    executor = GitExecutor(paths)
    wrong = tmp_path / "wrong-clean-cloud"
    wrong.mkdir()
    with pytest.raises(CutoverError, match="locked Phase06 path"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=wrong,
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )

    executor.branch_override[paths["cloud_task"]] = "main"
    with pytest.raises(CutoverError, match="Phase06 branch"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=paths["cloud_task"],
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )
    executor.branch_override.clear()
    executor.head_override[paths["cloud_task"]] = "b" * 40
    with pytest.raises(CutoverError, match="landed canonical commit"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=paths["cloud_task"],
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )

    link = tmp_path / "cloud-link"
    link.symlink_to(paths["cloud_task"], target_is_directory=True)
    with pytest.raises(CutoverError, match="symbolic link"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=link,
            executor=GitExecutor(paths),
            python_prefix=paths["canonical_local"] / ".venv",
        )


def test_repository_lock_allows_unrelated_dirty_state_but_rejects_phase06_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _tree(tmp_path, monkeypatch)
    executor = GitExecutor(paths)
    executor.status_override[paths["canonical_cloud"]] = " M reports/unrelated.md"

    repository.lock_phase06_repositories(
        script_repo_root=paths["canonical_local"],
        runner_cwd=paths["canonical_local"],
        cloud_worktree=paths["cloud_task"],
        executor=executor,
        python_prefix=paths["canonical_local"] / ".venv",
    )
    executor.status_override[paths["canonical_cloud"]] = (
        " M capabilities/mindscape_cloud_integration/manifest.yaml"
    )

    with pytest.raises(CutoverError, match="Phase06 path has unlanded changes"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=paths["cloud_task"],
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )

    executor.status_override[paths["canonical_local"]] = (
        " M web-console/src/app/workspaces/[workspaceId]/page.tsx"
    )
    with pytest.raises(CutoverError, match="Phase06 path has unlanded changes"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=paths["cloud_task"],
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )

    executor.status_override[paths["canonical_local"]] = (
        "R  notes/old.ts -> web-console/src/lib/host-runtime-sessions.ts"
    )
    with pytest.raises(CutoverError, match="Phase06 path has unlanded changes"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=paths["cloud_task"],
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )

    executor.status_override[paths["canonical_cloud"]] = " M reports/unrelated.md"
    executor.status_override[paths["canonical_local"]] = (
        " M web-console/src/lib/capability-ui-runtime-assets.ts"
    )
    with pytest.raises(CutoverError, match="Phase06 path has unlanded changes"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=paths["cloud_task"],
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )


@pytest.mark.parametrize(
    "manifest_path",
    (
        "capabilities/dance_motion_coach/manifest.yaml",
        "capabilities/live_interface_interpreter/manifest.yaml",
    ),
)
def test_repository_lock_rejects_dirty_remote_supported_pack_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest_path: str,
) -> None:
    paths = _tree(tmp_path, monkeypatch)
    executor = GitExecutor(paths)
    executor.status_override[paths["canonical_cloud"]] = f" M {manifest_path}"

    with pytest.raises(CutoverError, match="Phase06 path has unlanded changes"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["canonical_local"],
            cloud_worktree=paths["cloud_task"],
            executor=executor,
            python_prefix=paths["canonical_local"] / ".venv",
        )


def test_repository_lock_rejects_noncanonical_runner_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _tree(tmp_path, monkeypatch)
    with pytest.raises(CutoverError, match="cwd must be the canonical"):
        repository.lock_phase06_repositories(
            script_repo_root=paths["canonical_local"],
            runner_cwd=paths["local_task"],
            cloud_worktree=paths["cloud_task"],
            executor=GitExecutor(paths),
            python_prefix=paths["canonical_local"] / ".venv",
        )
