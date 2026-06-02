"""Backend runtime mode helpers.

Separates stable execution-plane behavior from development control-plane
behavior so pack installation work does not automatically restart a backend
that is currently running long-lived execution workloads.
"""

from __future__ import annotations

import os
from pathlib import Path


def _parse_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def get_backend_runtime_role() -> str:
    """Return the configured backend role.

    Roles:
    - execution: stable workload-serving plane; never auto-reloads implicitly
    - control/dev/auto: development-oriented plane
    """

    raw = (
        os.getenv("MINDSCAPE_BACKEND_ROLE")
        or os.getenv("LOCAL_CORE_BACKEND_ROLE")
        or "auto"
    )
    return str(raw).strip().lower() or "auto"


def is_execution_plane() -> bool:
    return get_backend_runtime_role() in {"execution", "stable"}


def is_control_plane() -> bool:
    return get_backend_runtime_role() in {"control", "backend-control", "control-plane"}


def should_enable_uvicorn_reload(
    *,
    environment: str | None = None,
) -> bool:
    """Decide whether the API process should run with uvicorn --reload."""

    explicit_reload = _parse_bool(os.getenv("MINDSCAPE_BACKEND_RELOAD"))
    if explicit_reload is not None:
        return explicit_reload

    env = str(environment or os.getenv("ENVIRONMENT", "development")).strip().lower()
    if env not in {"development", "dev"}:
        return False
    if is_execution_plane():
        return False
    return True


def should_enable_capability_reload_watch(
    *,
    environment: str | None = None,
) -> bool:
    """Return whether uvicorn reload should watch installed capability files."""

    explicit = _parse_bool(os.getenv("MINDSCAPE_CAPABILITY_RELOAD_WATCH"))
    if explicit is not None:
        return explicit

    disable = _parse_bool(os.getenv("LOCAL_CORE_DISABLE_CAPABILITY_RELOAD_WATCH"))
    if disable is True:
        return False

    if not should_enable_uvicorn_reload(environment=environment):
        return False
    if is_control_plane():
        return False
    return True


def get_uvicorn_reload_excludes(
    *,
    app_root: str | os.PathLike[str] | None = None,
    environment: str | None = None,
) -> list[str]:
    """Return filesystem paths that uvicorn reload must ignore.

    The control plane installs capability packs by replacing files under the
    installed capability tree. Watching that tree makes the installer requeue
    itself before it can commit a terminal job state.
    """

    if should_enable_capability_reload_watch(environment=environment):
        return []

    root = Path(app_root) if app_root is not None else Path(__file__).resolve().parents[1]

    def _relative_reload_pattern(path: Path) -> str:
        try:
            return str(path.resolve().relative_to(Path.cwd().resolve()))
        except ValueError:
            return str(path)

    def _reload_patterns(path: Path) -> list[str]:
        relative = _relative_reload_pattern(path)
        absolute = str(path.resolve())
        patterns: list[str] = []
        for base in (relative, absolute):
            patterns.extend([base, f"{base}/*", f"{base}/**", f"{base}/**/*"])
        return list(dict.fromkeys(patterns))

    return [
        pattern
        for path in (root / "capabilities", root / ".capability-install-staging")
        for pattern in _reload_patterns(path)
    ]


def should_allow_implicit_pack_reload(
    *,
    environment: str | None = None,
) -> bool:
    """Return whether pack installation may trigger implicit backend reloads."""

    explicit = _parse_bool(os.getenv("MINDSCAPE_ALLOW_IMPLICIT_PACK_RELOAD"))
    if explicit is not None:
        return explicit

    env = str(environment or os.getenv("ENVIRONMENT", "development")).strip().lower()
    if env not in {"development", "dev"}:
        return False
    if is_execution_plane():
        return False
    return True


def should_run_post_ready_tool_rag_warmup(
    *,
    environment: str | None = None,
) -> bool:
    explicit = _parse_bool(os.getenv("MINDSCAPE_POST_READY_TOOL_RAG_WARMUP"))
    if explicit is not None:
        return explicit

    env = str(environment or os.getenv("ENVIRONMENT", "development")).strip().lower()
    if env not in {"development", "dev"}:
        return True
    if is_execution_plane():
        return True
    return False


def should_run_post_ready_runtime_migrations(
    *,
    environment: str | None = None,
) -> bool:
    explicit = _parse_bool(os.getenv("MINDSCAPE_POST_READY_RUNTIME_MIGRATIONS"))
    if explicit is not None:
        return explicit

    env = str(environment or os.getenv("ENVIRONMENT", "development")).strip().lower()
    if env not in {"development", "dev"}:
        return True
    if is_execution_plane():
        return True
    return False
