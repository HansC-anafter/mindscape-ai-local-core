from __future__ import annotations

import pytest

from backend.app.services.runner_topology.spec_metadata import (
    _extract_runner_metadata_from_spec,
    merge_runner_metadata_into_context,
    resolve_runner_metadata_variant,
)


def _metadata() -> dict:
    return _extract_runner_metadata_from_spec(
        {
            "execution_profile": {
                "resource_class": "browser",
                "queue_shard": "browser_local",
                "runner_metadata_variants": [
                    {
                        "when": {
                            "input": "source_mode",
                            "equals": "captured_posts",
                        },
                        "metadata": {
                            "queue_shard": "default_local_browser",
                            "task_family": "browser_batch",
                            "managed_runner_role": "managed_browser_batch",
                        },
                    }
                ],
            }
        },
        capability_code="ig",
    )


def test_runner_metadata_variant_routes_captured_mode_only() -> None:
    metadata = _metadata()

    browser = resolve_runner_metadata_variant(
        metadata,
        {"inputs": {"source_mode": "browser"}},
    )
    captured = resolve_runner_metadata_variant(
        metadata,
        {"inputs": {"source_mode": "captured_posts"}},
    )

    assert browser["queue_shard"] == "browser_local"
    assert browser.get("task_family") is None
    assert captured["queue_shard"] == "default_local_browser"
    assert captured["task_family"] == "browser_batch"


def test_context_merge_uses_variant_but_preserves_explicit_context() -> None:
    merged = merge_runner_metadata_into_context(
        {
            "inputs": {"source_mode": "captured_posts"},
            "queue_shard": "operator_override",
        },
        _metadata(),
        playbook_code="ig_batch_pin_references",
    )

    assert merged["queue_shard"] == "operator_override"
    assert merged["task_family"] == "browser_batch"
    assert "runner_metadata_variants" not in merged


def test_overlapping_runner_metadata_variants_fail_closed() -> None:
    metadata = _metadata()
    metadata["runner_metadata_variants"].append(
        metadata["runner_metadata_variants"][0]
    )

    with pytest.raises(ValueError, match="multiple runner metadata variants"):
        resolve_runner_metadata_variant(
            metadata,
            {"inputs": {"source_mode": "captured_posts"}},
        )
