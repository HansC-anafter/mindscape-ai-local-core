from capabilities.ig.services.auto_analyze import (
    _build_visit_batch_pin_execution_context,
)
from capabilities.ig.tools.ig_batch_pin_tool import (
    _captured_posts_post_detail_fallback_enabled,
)


def test_captured_batch_pin_routes_to_default_local_browser_without_profile_aliases():
    ctx = _build_visit_batch_pin_execution_context(
        execution_id="exec-1",
        workspace_id="workspace-1",
        target_handle="target",
        target_count=12,
        user_data_dir="/app/data/ig-browser-profiles/profile-a",
        parent_execution_id="parent-1",
        source_handle="seed",
    )

    assert ctx["resource_class"] == "browser"
    assert ctx["queue_shard"] == "default_local_browser"
    assert ctx["concurrency"]["lock_scope"] == "playbook"
    assert ctx["concurrency"]["max_parallel"] == 1
    assert ctx["concurrency"]["lock_aliases"] == []


def test_captured_posts_post_detail_fallback_is_opt_in(monkeypatch):
    monkeypatch.delenv("IG_BATCH_PIN_CAPTURED_POST_DETAIL_FALLBACK", raising=False)
    assert _captured_posts_post_detail_fallback_enabled() is False

    monkeypatch.setenv("IG_BATCH_PIN_CAPTURED_POST_DETAIL_FALLBACK", "true")
    assert _captured_posts_post_detail_fallback_enabled() is True
