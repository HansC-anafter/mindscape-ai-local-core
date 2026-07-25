from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MAIN_LAUNCHER = REPO_ROOT / "scripts" / "mlx-server" / "start-mlx-server.sh"
MODULE_LAUNCHER = REPO_ROOT / "scripts" / "modules" / "inference" / "mlx.sh"


def test_main_mlx_launcher_self_heals_hf_cache_before_health_probe() -> None:
    text = MAIN_LAUNCHER.read_text(encoding="utf-8")

    assert "HF_HUB_CACHE" in text
    assert 'mkdir -p "$cache_dir"' in text
    assert 'CACHE_DIR="$(_mlx_resolve_hf_cache_dir)"' in text

    loop_index = text.index('while kill -0 "$MLX_PID"')
    ensure_index = text.index('_mlx_ensure_hf_cache_dir "mlx-watchdog"', loop_index)
    probe_index = text.index('"http://localhost:${PORT}/health"', loop_index)

    assert ensure_index < probe_index


def test_main_mlx_launcher_recovers_unresponsive_idle_runtime_by_default() -> None:
    text = MAIN_LAUNCHER.read_text(encoding="utf-8")

    assert (
        'WATCHDOG_IDLE_FAILURE_MODE="${MLX_WATCHDOG_IDLE_FAILURE_MODE:-recover}"'
        in text
    )
    assert 'if [ "$WATCHDOG_IDLE_FAILURE_MODE" = "ignore" ]' in text
    assert "failures=$((failures + 1))" in text
    assert "${WATCHDOG_MAX_FAILURES} idle failures - killing MLX" in text


def test_main_mlx_launcher_reads_formal_lane_state_without_unlinking_it() -> None:
    text = MAIN_LAUNCHER.read_text(encoding="utf-8")

    assert 'if [ "$PORT" = "8210" ]; then' in text
    assert (
        'WATCHDOG_STATE_FILE_DEFAULT="${WATCHDOG_STATE_ROOT}/vision_local.json"'
        in text
    )
    assert (
        'WATCHDOG_STATE_FILE="${MLX_WATCHDOG_STATE_FILE:-'
        '$WATCHDOG_STATE_FILE_DEFAULT}"'
        in text
    )
    assert 'rm -f "$WATCHDOG_STATE_FILE"' not in text


def test_module_mlx_launcher_creates_hf_cache_before_server_exec() -> None:
    text = MODULE_LAUNCHER.read_text(encoding="utf-8")

    assert "HF_HUB_CACHE" in text
    assert 'mkdir -p "$cache_dir"' in text

    start_index = text.index("start_mlx_server()")
    ensure_index = text.index("_mlx_ensure_hf_cache_dir", start_index)
    exec_index = text.index('exec "$python_bin" -m mlx_vlm.server', start_index)

    assert ensure_index < exec_index
