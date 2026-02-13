"""
Startup banner for Mindscape AI Local Core backend.

Prints a mushroom ASCII art logo with system info after successful startup.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Version constant — single source of truth
VERSION = "1.0.0"

# ANSI color codes
_CYAN = "\033[36m"
_MAGENTA = "\033[35m"
_WHITE = "\033[97m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def print_startup_banner(
    *, port: int | None = None, extra_lines: list[str] | None = None
):
    """Print the Mindscape AI startup banner to stdout.

    Args:
        port: Override the port number. Defaults to PORT env var or 8000.
        extra_lines: Additional info lines to append (e.g. capability pack count).
    """
    if port is None:
        port = int(os.getenv("PORT", "8000"))

    url = f"http://localhost:{port}"

    mushroom = f"""{_MAGENTA}
        ██████████
      ██{_WHITE}░░{_MAGENTA}██{_WHITE}░░░░{_MAGENTA}██
    ██{_WHITE}░░░░{_MAGENTA}██{_WHITE}░░░░░░{_MAGENTA}██
    ██{_WHITE}░░░░░░░░░░░░{_MAGENTA}██
    ██{_WHITE}░░░░░░░░░░░░{_MAGENTA}██
      ██████████████
        {_CYAN}██{_WHITE}░░░░{_CYAN}██
        ██{_WHITE}░░░░{_CYAN}██
        ██{_WHITE}░░░░{_CYAN}██
        ██████████{_RESET}"""

    # Build info block
    info_lines = [
        "",
        f"  {_BOLD}{_WHITE}Mindscape AI{_RESET}{_DIM}  — Your Personal AI Team Console{_RESET}",
        "",
        f"  {_CYAN}Version :{_RESET}  {VERSION}",
        f"  {_CYAN}URL     :{_RESET}  {url}",
        f"  {_CYAN}API Docs:{_RESET}  {url}/docs",
    ]

    if extra_lines:
        for line in extra_lines:
            info_lines.append(f"  {_CYAN}>{_RESET} {line}")

    info_lines.append("")
    info_lines.append(f"  {_DIM}Ready to serve.{_RESET}")
    info_lines.append("")

    banner = mushroom + "\n" + "\n".join(info_lines)
    print(banner, flush=True)
