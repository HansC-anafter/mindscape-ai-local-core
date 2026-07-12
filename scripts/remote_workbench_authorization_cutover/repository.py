"""Repository, cwd, protected-path, and interpreter locks for Phase06."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .io import CutoverError


LOCAL_TASK_DIRECTORY = "mindscape-ai-local-core-remote-workbench-phase06-20260713"
CLOUD_TASK_DIRECTORY = "mindscape-ai-cloud-remote-workbench-phase06-20260713"
LOCAL_TASK_BRANCH = "codex/remote-workbench-phase06-local-20260713"
CLOUD_TASK_BRANCH = "codex/remote-workbench-phase06-cloud-20260713"
LOCAL_PROTECTED_PREFIXES = (
    "docker-compose.yml",
    "backend/app/routes/core/capability_packs_core/installed_routes.py",
    "backend/app/routes/core/capability_packs_core/mobile_workbench_gateway_support.py",
    "backend/app/services/host_resources/runner_claim_gate_bootstrap.py",
    "backend/app/services/host_resources/runner_claim_gate_facade.py",
    "scripts/config/ai.mindscape.remote-workbench-bridge.plist",
    "scripts/install-remote-workbench-bridge-macos.sh",
    "scripts/remote_workbench_authorization_cutover/",
    "scripts/remote_workbench_bridge/",
    "scripts/remote_workbench_bridge_monitor.py",
    "scripts/remote_workbench_remote_ingress_lock.py",
    "scripts/start_remote_workbench_tunnel.sh",
    "scripts/verify_remote_workbench_identity_workspace_authorization.py",
    "web-console/dev-proxy.gateway.spec.mjs",
    "web-console/dev-proxy.mjs",
    "web-console/dev-proxy/",
    "web-console/src/app/workspaces/[workspaceId]/capabilities/[capabilityCode]/CapabilityLoadedComponents.tsx",
    "web-console/src/app/workspaces/[workspaceId]/page.tsx",
    "web-console/src/app/workspaces/[workspaceId]/RemoteWorkspaceLanding.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityUiHostClientLoader.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityHostRuntimeFrame.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityUiHostRouteClient.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/CapabilityUiHostRouteShell.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspaceRunsPanel.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspaceSurfaceShell.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/WorkspaceToolExtensionSlot.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/useWorkspaceToolDefinitions.ts",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/renderCapabilityUiHostPage.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/[capabilityCode]/[[...surfacePath]]/page.tsx",
    "web-console/src/app/workspaces/[workspaceId]/capability-ui-hosts/capabilityHostRuntimeFrame/workspaceToolContributions.tsx",
    "web-console/src/app/workspaces/[workspaceId]/components/OutcomesPanel.tsx",
    "web-console/src/app/workspaces/[workspaceId]/components/PackPanel.tsx",
    "web-console/src/app/workspaces/components/execution-inspector/StepDetailPanel.tsx",
    "web-console/src/components/capabilities/meeting-workbench/RuntimeCommandSurfaceSlot.tsx",
    "web-console/src/components/capabilities/meeting-workbench/runs/useHostRuntimeRunSession.ts",
    "web-console/src/components/capabilities/workbench/PackScopeToolRailHost.tsx",
    "web-console/src/lib/capability-packs/installed-capabilities-cache.ts",
    "web-console/src/lib/capability-runtime-asset-url.ts",
    "web-console/src/lib/capability-ui-loader.ts",
    "web-console/src/lib/capability-ui-runtime-assets.ts",
    "web-console/src/lib/host-runtime-sessions.ts",
    "web-console/src/lib/keyboard-shortcuts/KeyboardShortcutProvider.tsx",
    "web-console/src/lib/keyboard-shortcuts/shortcut-storage.ts",
    "web-console/src/lib/workspace-tools/workspace-tool-registry.ts",
)
CLOUD_PROTECTED_PREFIXES = (
    "capabilities/mindscape_cloud_integration/",
    "scripts/package_capability.py",
    "scripts/validate_manifest.py",
)


class Executor(Protocol):
    def run(
        self,
        args: Sequence[str],
        *,
        timeout_seconds: float = 60.0,
        input_text: str | None = None,
    ) -> str: ...


@dataclass(frozen=True)
class LockedRepositories:
    canonical_local: Path
    local_task: Path
    canonical_cloud: Path
    cloud_task: Path
    commit: str


def _absolute_without_symlink(path: Path, label: str) -> Path:
    expanded = path.expanduser()
    if expanded.is_symlink():
        raise CutoverError(f"{label} must not be a symbolic link")
    absolute = expanded.absolute()
    resolved = absolute.resolve()
    if absolute != resolved:
        raise CutoverError(f"{label} must not traverse symbolic links")
    return resolved


def _git(executor: Executor, repo: Path, *args: str) -> str:
    return executor.run(
        ["git", "-C", str(repo), *args],
        timeout_seconds=20.0,
    ).strip()


def _git_status(executor: Executor, repo: Path) -> str:
    """Preserve porcelain's leading XY columns while trimming terminal newlines."""

    return executor.run(
        [
            "git",
            "-C",
            str(repo),
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ],
        timeout_seconds=20.0,
    ).rstrip("\r\n")


def _status_paths(raw: str) -> set[str]:
    paths: set[str] = set()
    for line in raw.splitlines():
        if len(line) < 4:
            raise CutoverError("Canonical Git status evidence is malformed")
        value = line[3:].strip()
        for candidate in value.split(" -> "):
            if candidate.startswith('"'):
                try:
                    decoded = json.loads(candidate)
                except json.JSONDecodeError as error:
                    raise CutoverError("Canonical Git quoted path is malformed") from error
                if not isinstance(decoded, str):
                    raise CutoverError("Canonical Git quoted path is not text")
                paths.add(decoded)
            else:
                paths.add(candidate)
    return paths


def _require_no_protected_overlap(
    executor: Executor,
    canonical: Path,
    prefixes: tuple[str, ...],
    label: str,
) -> None:
    raw = _git_status(executor, canonical)
    overlap = sorted(
        path
        for path in _status_paths(raw)
        if any(path == prefix or path.startswith(prefix) for prefix in prefixes)
    )
    if overlap:
        raise CutoverError(f"{label} canonical Phase06 path has unlanded changes")


def _require_repo_identity(
    executor: Executor,
    *,
    task: Path,
    canonical: Path,
    expected_branch: str,
    protected_prefixes: tuple[str, ...],
    label: str,
) -> str:
    task_top = Path(_git(executor, task, "rev-parse", "--show-toplevel")).resolve()
    canonical_top = Path(
        _git(executor, canonical, "rev-parse", "--show-toplevel")
    ).resolve()
    if task_top != task or canonical_top != canonical:
        raise CutoverError(f"{label} Git top-level does not match its declared path")
    if _git(executor, task, "branch", "--show-current") != expected_branch:
        raise CutoverError(f"{label} branch does not match the Phase06 branch")
    task_status = _git_status(executor, task)
    if task_status:
        raise CutoverError(f"{label} worktree must be clean")
    _require_no_protected_overlap(
        executor,
        canonical,
        protected_prefixes,
        label,
    )
    task_head = _git(executor, task, "rev-parse", "HEAD")
    if task_head != _git(executor, canonical, "rev-parse", "HEAD"):
        raise CutoverError(f"{label} HEAD is not the landed canonical commit")
    task_common = Path(
        _git(executor, task, "rev-parse", "--path-format=absolute", "--git-common-dir")
    ).resolve()
    canonical_common = Path(
        _git(
            executor,
            canonical,
            "rev-parse",
            "--path-format=absolute",
            "--git-common-dir",
        )
    ).resolve()
    if task_common != canonical_common:
        raise CutoverError(f"{label} task does not belong to the canonical repository")
    return task_head


def lock_phase06_repositories(
    *,
    script_repo_root: Path,
    runner_cwd: Path,
    cloud_worktree: Path,
    executor: Executor,
    python_prefix: Path,
) -> LockedRepositories:
    """Run from canonical Local while task worktrees remain identity evidence only."""

    canonical_local = _absolute_without_symlink(script_repo_root, "Canonical Local root")
    if _absolute_without_symlink(runner_cwd, "Runner cwd") != canonical_local:
        raise CutoverError("Runner cwd must be the canonical Local repository")
    workspace_root = canonical_local.parent
    if canonical_local != workspace_root / "mindscape-ai-local-core":
        raise CutoverError("Runner root must be the declared canonical Local repository")
    canonical_cloud = workspace_root / "mindscape-ai-cloud"
    local_task = _absolute_without_symlink(
        workspace_root / ".worktrees" / LOCAL_TASK_DIRECTORY,
        "Local task worktree",
    )
    cloud_task = _absolute_without_symlink(cloud_worktree, "Cloud task worktree")
    expected_cloud = workspace_root / ".worktrees" / CLOUD_TASK_DIRECTORY
    if cloud_task != expected_cloud.resolve():
        raise CutoverError("Cloud worktree does not match the locked Phase06 path")
    if not canonical_local.joinpath(".git").is_dir():
        raise CutoverError("Canonical Local repository is unavailable")
    if not canonical_cloud.joinpath(".git").is_dir():
        raise CutoverError("Canonical Cloud repository is unavailable")
    if python_prefix.resolve() != canonical_local.joinpath(".venv").resolve():
        raise CutoverError("Runner must use the canonical Local .venv interpreter")
    local_head = _require_repo_identity(
        executor,
        task=local_task,
        canonical=canonical_local,
        expected_branch=LOCAL_TASK_BRANCH,
        protected_prefixes=LOCAL_PROTECTED_PREFIXES,
        label="Local task",
    )
    cloud_head = _require_repo_identity(
        executor,
        task=cloud_task,
        canonical=canonical_cloud,
        expected_branch=CLOUD_TASK_BRANCH,
        protected_prefixes=CLOUD_PROTECTED_PREFIXES,
        label="Cloud task",
    )
    if local_head != _git(executor, canonical_local, "rev-parse", "HEAD"):
        raise CutoverError("Local canonical commit identity changed during preflight")
    return LockedRepositories(
        canonical_local=canonical_local,
        local_task=local_task,
        canonical_cloud=canonical_cloud,
        cloud_task=cloud_task,
        commit=cloud_head,
    )
