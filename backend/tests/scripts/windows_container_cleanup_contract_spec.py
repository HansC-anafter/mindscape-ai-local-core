from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
START_SCRIPT = REPO_ROOT / "scripts" / "start.ps1"
CLEANUP_MODULE = (
    REPO_ROOT / "scripts" / "container_cleanup" / "ContainerCleanup.psm1"
)
SHELL_START_SCRIPT = REPO_ROOT / "scripts" / "start.sh"
SHELL_CLEANUP_MODULE = (
    REPO_ROOT / "scripts" / "container_cleanup" / "container_cleanup.sh"
)


def test_windows_start_uses_the_container_cleanup_module() -> None:
    source = START_SCRIPT.read_text(encoding="utf-8")

    assert 'container_cleanup\\ContainerCleanup.psm1' in source
    assert "$containerList = @(Get-MindscapeConflictingContainers)" in source
    assert "Remove-MindscapeResidualContainers" in source
    assert "docker rm -f $container" not in source


def test_cleanup_requeries_after_compose_down_and_accepts_disappearance() -> None:
    source = CLEANUP_MODULE.read_text(encoding="utf-8")

    residual_query = source.index(
        "$residualContainers = @(Get-MindscapeConflictingContainers)"
    )
    removal = source.index("docker rm -f $container", residual_query)
    verification = source.index(
        "$verification = Invoke-MindscapeContainerNameQuery", removal
    )

    assert residual_query < removal < verification
    assert (
        "$verification.ExitCode -ne 0 -or "
        "$verification.Names -contains $container"
    ) in source
    assert '2>$null | Out-Null' in source


def test_shell_start_uses_the_same_idempotent_cleanup_contract() -> None:
    start_source = SHELL_START_SCRIPT.read_text(encoding="utf-8")
    module_source = SHELL_CLEANUP_MODULE.read_text(encoding="utf-8")

    assert 'container_cleanup/container_cleanup.sh' in start_source
    assert 'EXISTING_CONTAINERS="$(mindscape_list_conflicting_containers)"' in start_source
    assert "mindscape_remove_residual_containers" in start_source
    assert 'docker rm -f "$container"' not in start_source
    assert 'residual_containers="$(mindscape_list_conflicting_containers)"' in module_source
    assert 'current_containers="$(mindscape_list_conflicting_containers)"' in module_source
