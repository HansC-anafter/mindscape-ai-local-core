from __future__ import annotations

import json

from scripts.maintenance.browser_resource_capacity_preflight_core.collectors import _run_json
from scripts.maintenance.browser_resource_capacity_preflight_core.commands import (
    CommandResult,
)
from scripts.maintenance.browser_resource_capacity_preflight_core.runtime_sources import (
    collect_backend_mounts,
    load_deployed_playbook_metadata,
    parse_container_mounts,
    resolve_claim_gate,
)


def test_backend_mount_inspect_keeps_five_second_default() -> None:
    calls: list[tuple[tuple[str, ...], int]] = []

    class RecordingRunner:
        def run(
            self,
            argv: list[str],
            *,
            timeout_seconds: int = 5,
        ) -> CommandResult:
            calls.append((tuple(argv), timeout_seconds))
            mounts = [
                {"Source": "/host/backend", "Destination": "/app/backend"},
                {"Source": "/host/data", "Destination": "/app/data"},
            ]
            return CommandResult(tuple(argv), 0, json.dumps(mounts), "")

    mounts = collect_backend_mounts(  # type: ignore[arg-type]
        RecordingRunner(),
        "backend",
    )
    assert mounts["/app/backend"].as_posix() == "/host/backend"
    assert mounts["/app/data"].as_posix() == "/host/data"
    assert calls == [
        (
            (
                "docker",
                "inspect",
                "--format",
                "{{json .Mounts}}",
                "backend",
            ),
            5,
        )
    ]


def test_mount_parser_ignores_non_absolute_sources() -> None:
    mounts = parse_container_mounts(
        json.dumps(
            [
                {"Source": "relative", "Destination": "/app/backend"},
                {"Source": "/host/data", "Destination": "/app/data"},
            ]
        )
    )

    assert mounts == {"/app/data": mounts["/app/data"]}


def test_claim_gate_matches_redis_bootstrap_default_precedence(tmp_path) -> None:
    bootstrap = tmp_path / "runner-claim-gate.paused"
    bootstrap.write_text('{"reason":"maintenance"}', encoding="utf-8")

    redis_gate = resolve_claim_gate(
        {"state": "paused", "reason": "redis"},
        bootstrap,
    )
    assert redis_gate["source"] == "redis"
    assert redis_gate["reason"] == "redis"

    file_gate = resolve_claim_gate(None, bootstrap)
    assert file_gate["state"] == "paused"
    assert file_gate["source"] == "bootstrap_file"
    bootstrap.unlink()
    assert resolve_claim_gate(None, bootstrap) == {
        "state": "open",
        "reason": None,
        "source": "default",
        "persisted": False,
    }


def test_deployed_specs_preserve_resource_variants_and_concurrency(
    tmp_path,
) -> None:
    specs = tmp_path / "app/capabilities/ig/playbooks/specs"
    specs.mkdir(parents=True)
    codes = (
        "ig_analyze_following",
        "ig_batch_pin_references",
        "ig_pin_post_detail",
    )
    for code in codes:
        payload = {
            "playbook_code": code,
            "execution_profile": {
                "resource_class": "browser",
                "resource_requirements": {"browser_contexts": 1},
                "resource_requirement_variants": [
                    {
                        "when": {"input": "source_mode", "equals": "captured_posts"},
                        "resource_requirements": {"ig_profile_lock": False},
                    }
                ],
            },
            "concurrency": {"lock_key_input": "user_data_dir"},
        }
        (specs / f"{code}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    catalog = load_deployed_playbook_metadata(tmp_path)
    assert set(catalog) == set(codes)
    assert catalog["ig_batch_pin_references"]["resource_requirement_variants"]
    assert catalog["ig_pin_post_detail"]["concurrency"] == {
        "lock_key_input": "user_data_dir"
    }


def test_generic_json_collector_keeps_five_second_default() -> None:
    timeouts: list[int] = []

    class RecordingRunner:
        def run(
            self,
            argv: list[str],
            *,
            timeout_seconds: int = 5,
        ) -> CommandResult:
            timeouts.append(timeout_seconds)
            return CommandResult(tuple(argv), 0, "{}", "")

    assert _run_json(  # type: ignore[arg-type]
        RecordingRunner(),
        ["docker", "info"],
    ) == {}
    assert timeouts == [5]
