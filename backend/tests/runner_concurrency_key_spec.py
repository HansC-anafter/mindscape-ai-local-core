from backend.app.runner.concurrency import _resolve_lock_keys


def test_resolve_lock_keys_uses_persisted_concurrency_key_without_context_policy():
    keys = _resolve_lock_keys(
        {"inputs": {"reference_id": "ref_1"}},
        "ig_analyze_pinned_reference",
        persisted_concurrency_key="concurrency:playbook:ig_analyze_pinned_reference",
    )

    assert keys == ["concurrency:playbook:ig_analyze_pinned_reference"]


def test_resolve_lock_keys_dedupes_persisted_concurrency_key_with_context_policy():
    keys = _resolve_lock_keys(
        {
            "playbook_code": "ig_analyze_pinned_reference",
            "concurrency": {"lock_scope": "playbook"},
            "inputs": {"reference_id": "ref_1"},
        },
        "ig_analyze_pinned_reference",
        persisted_concurrency_key="concurrency:playbook:ig_analyze_pinned_reference",
    )

    assert keys == ["concurrency:playbook:ig_analyze_pinned_reference"]
