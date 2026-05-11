import pytest

from backend.app.services.runner_resources import (
    InMemoryResourceLeaseStore,
    build_resource_lease_key,
    release_resource_lease_keys,
    renew_resource_lease_keys,
)


@pytest.mark.asyncio
async def test_resource_lease_store_enforces_owner_and_ttl():
    store = InMemoryResourceLeaseStore(now_epoch=100.0)
    lease_key = build_resource_lease_key("ig_profile_lock", "/tmp/profile A")

    assert await store.acquire(lease_key, "runner-a:task-1", 10) is True
    assert await store.acquire(lease_key, "runner-b:task-2", 10) is False
    assert await store.release(lease_key, "runner-b:task-2") is False

    await renew_resource_lease_keys(
        store,
        [lease_key],
        owner_id="runner-a:task-1",
        ttl_seconds=20,
    )
    store.advance(19)
    assert await store.acquire(lease_key, "runner-b:task-2", 10) is False

    store.advance(2)
    assert await store.list_expired() == [lease_key]
    assert await store.acquire(lease_key, "runner-b:task-2", 10) is True

    await release_resource_lease_keys(
        store,
        [lease_key],
        owner_id="runner-b:task-2",
    )
    assert await store.acquire(lease_key, "runner-a:task-1", 10) is True


def test_resource_lease_key_is_stable_and_namespaced():
    key_a = build_resource_lease_key("ig_profile_lock", "/tmp/profile A")
    key_b = build_resource_lease_key("ig_profile_lock", "/tmp/profile A")
    key_c = build_resource_lease_key("ig_profile_lock", "/tmp/profile B")

    assert key_a == key_b
    assert key_a != key_c
    assert key_a.startswith("mindscape:runner_resources:lease:v1:ig_profile_lock:")
    assert "/" not in key_a
    assert " " not in key_a
