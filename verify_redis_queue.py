import os
import sys
import asyncio
from datetime import datetime

# Adjust path so backend modules can be imported
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.cache.async_redis import get_async_redis_client

async def main():
    print("--- Starting Redis Queue Integration Tests ---")
    
    redis_client = await get_async_redis_client()
    if not redis_client:
        print("Redis client unavailable.")
        return

    # Clean up any leftover test keys
    pack_id = "test_queue_pack"
    store = RedisRunnerQueueStore(pack_id=pack_id)
    await redis_client.delete(store.q_pending, store.q_processing, store.q_delayed, store.q_deadletter)
    
    # 1. Enqueue and Dequeue
    task_id_1 = "task_verify_001"
    ok = await store.enqueue_task(task_id_1)
    print(f"[Test 1] Enqueued: {ok}")
    assert ok
    
    popped_task = await store.dequeue_task_blocking(timeout=2, visibility_timeout_sec=5)
    print(f"[Test 1] Popped: {popped_task}")
    assert popped_task == task_id_1
    
    # Verify it is in processing queue
    score = await redis_client.zscore(store.q_processing, task_id_1)
    print(f"[Test 1] ZSET processing score: {score}")
    assert score is not None
    
    # 2. Ack Task
    ok = await store.ack_task(task_id_1)
    print(f"[Test 2] Acked: {ok}")
    assert ok
    score_after = await redis_client.zscore(store.q_processing, task_id_1)
    assert score_after is None
    
    # 3. Nack to Delayed
    task_id_nack = "task_verify_002"
    await store.enqueue_task(task_id_nack)
    await store.dequeue_task_blocking(timeout=1)
    ok = await store.nack_task_to_delayed(task_id_nack, delay_sec=10)
    print(f"[Test 3] Nack to delayed: {ok}")
    assert ok
    score_del = await redis_client.zscore(store.q_delayed, task_id_nack)
    print(f"[Test 3] Delayed ZSET score: {score_del}")
    assert score_del is not None
    
    # 4. Deadletter
    task_id_dead = "task_verify_003"
    await store.enqueue_task(task_id_dead)
    await store.dequeue_task_blocking(timeout=1)
    ok = await store.move_to_deadletter(task_id_dead)
    print(f"[Test 4] Moved to Deadletter: {ok}")
    assert ok
    dead_len = await redis_client.llen(store.q_deadletter)
    assert dead_len == 1
    
    # 5. Lock Lua Scripts
    lock_key = "test_lock_lua"
    owner_id = "runner_x"
    ok = await store.acquire_lock(lock_key, owner_id, 10)
    print(f"[Test 5] Acquired lock: {ok}")
    assert ok
    
    # Try acquire with different owner
    ok2 = await store.acquire_lock(lock_key, "runner_y", 10)
    print(f"[Test 5] Acquiring lock again (expected fail): {ok2}")
    assert not ok2
    
    # Renew lock
    ok_renew = await store.renew_lock(lock_key, owner_id, 20)
    print(f"[Test 5] Renew lock (expected success): {ok_renew}")
    assert ok_renew
    
    # Renew with wrong owner
    ok_renew2 = await store.renew_lock(lock_key, "runner_y", 20)
    print(f"[Test 5] Renew lock wrong owner (expected fail): {ok_renew2}")
    assert not ok_renew2
    
    # Safe Release
    ok_rel_wrong = await store.release_lock(lock_key, "runner_y")
    print(f"[Test 5] Release lock wrong owner (expected fail): {ok_rel_wrong}")
    assert not ok_rel_wrong
    
    ok_rel = await store.release_lock(lock_key, owner_id)
    print(f"[Test 5] Release lock right owner (expected success): {ok_rel}")
    assert ok_rel
    
    print("--- All tests passed! ---")
    
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
