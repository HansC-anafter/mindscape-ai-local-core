from __future__ import annotations

import pytest

from scripts.maintenance.browser_resource_capacity_preflight_core.cli import (
    build_parser,
)


def test_request_evidence_is_required() -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(
            ["post-resume", "--required-concurrency", "5"]
        )

    assert exc_info.value.code == 2


def test_container_limit_fallback_option_is_removed() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "post-resume",
                "--required-concurrency",
                "5",
                "--request-evidence-json",
                "evidence.json",
                "--container-limit-fallback",
            ]
        )

    assert exc_info.value.code == 2
    assert "container-limit-fallback" not in parser.format_help()
