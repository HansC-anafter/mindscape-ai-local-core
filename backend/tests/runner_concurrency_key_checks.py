import os
import sys
import types

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

runner_queue_store_stub = types.ModuleType(
    "backend.app.services.stores.redis.runner_queue_store"
)
runner_queue_store_stub.RedisRunnerQueueStore = object
sys.modules.setdefault(
    "backend.app.services.stores.redis.runner_queue_store",
    runner_queue_store_stub,
)

from backend.app.runner.concurrency import _resolve_lock_keys


def test_shared_profile_lock_keys_cover_cross_playbook_ig_browser_aliases():
    ctx = {
        "inputs": {"user_data_dir": "/tmp/ig-profile"},
        "concurrency": {
            "lock_key_input": "user_data_dir",
            "lock_scope": "input",
        },
    }

    keys = _resolve_lock_keys(ctx, "ig_analyze_following")

    assert keys[0] == "concurrency:user_data_dir:/tmp/ig-profile"
    assert "ig_profile:/tmp/ig-profile" in keys
    assert (
        "concurrency:playbook_input:ig_analyze_following:/tmp/ig-profile"
        in keys
    )
    assert (
        "concurrency:playbook_input:ig_batch_pin_references:/tmp/ig-profile"
        in keys
    )


def test_legacy_playbook_input_lock_still_projects_shared_profile_aliases():
    ctx = {
        "inputs": {"user_data_dir": "/tmp/ig-profile"},
        "concurrency": {
            "lock_key_input": "user_data_dir",
            "lock_scope": "playbook_input",
        },
    }

    keys = _resolve_lock_keys(ctx, "ig_batch_pin_references")

    assert keys[0] == (
        "concurrency:playbook_input:ig_batch_pin_references:/tmp/ig-profile"
    )
    assert "concurrency:user_data_dir:/tmp/ig-profile" in keys
    assert "ig_profile:/tmp/ig-profile" in keys
    assert (
        "concurrency:playbook_input:ig_analyze_following:/tmp/ig-profile"
        in keys
    )
