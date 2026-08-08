"""Platform-neutral operator instructions for secret-aware Compose commands."""

from __future__ import annotations


def build_compose_restart_instruction(targets: list[str]) -> str:
    """Return both supported host commands without invoking either runtime."""
    services = " ".join(targets)
    return (
        f"./scripts/compose.sh restart {services} (macOS/Linux) or "
        f".\\scripts\\compose.ps1 restart {services} (Windows)"
    )
