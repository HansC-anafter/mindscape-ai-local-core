"""Async Redis Queue and Lock Store for the Task Runner.

Implements reliable ZSET-based queues with visibility timeouts, 
Delayed backoff queues, Deadletter handling, and Lua-secured Lock Leases.
"""

import asyncio
import logging
from typing import Optional, List, Tuple
from datetime import datetime, timezone

from backend.app.services.cache.async_redis import get_async_redis_client
from backend.app.services.cache.redis_cache import get_cache_service

logger = logging.getLogger(__name__)

# --- Reusable Lua Scripts ---

LUA_COMPARE_AND_DELETE = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

LUA_RENEW_LEASE = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""

class RedisRunnerQueueStore:
    def __init__(self, pack_id: str = "default"):
        self.pack_id = pack_id
        # Queue names
        self.q_pending = f"mindscape:queue:pending:{pack_id}"
        self.q_processing = f"mindscape:queue:processing:{pack_id}"
        self.q_delayed = f"mindscape:queue:delayed:{pack_id}"
        self.q_deadletter = f"mindscape:queue:deadletter:{pack_id}"

    async def _get_client(self):
        return await get_async_redis_client()

    def _utc_now_timestamp(self) -> float:
        return datetime.now(timezone.utc).timestamp()

    # --- Queue Methods ---

    async def enqueue_task(self, task_id: str) -> bool:
        """Push a task to the pending queue."""
        client = await self._get_client()
        if not client:
            return False
        
        try:
            await client.lpush(self.q_pending, task_id)
            return True
        except Exception as e:
            logger.error(f"[Redis Queue] Failed to enqueue {task_id}: {e}")
            return False

    def enqueue_task_sync(self, task_id: str) -> bool:
        """Synchronous enqueue for use inside SQLAlchemy commits."""
        cache = get_cache_service()
        if not cache._ensure_connected() or not cache._client:
            return False
        
        try:
            cache._client.lpush(self.q_pending, task_id)
            return True
        except Exception as e:
            logger.error(f"[Redis Queue] Failed sync enqueue {task_id}: {e}")
            return False

    async def dequeue_task_blocking(self, timeout: int = 2, visibility_timeout_sec: int = 180) -> Optional[str]:
        """Safely fetch a task via blocking pop and move to processing ZSET."""
        client = await self._get_client()
        if not client:
            await asyncio.sleep(timeout)
            return None

        temp_list = f"mindscape:queue:temp:{self.pack_id}"
        try:
            # Step 1: BLMOVE from pending to a temp list atomically.
            # Using BLMOVE (Redis 6+) if available, else fallback down.
            item = await client.blmove(
                self.q_pending,
                temp_list,
                timeout,
                "RIGHT",
                "LEFT"
            )
            
            if not item:
                return None
                
            task_id = item
            
            # Step 2: ZADD to processing with visibility timeout
            deadline = self._utc_now_timestamp() + visibility_timeout_sec
            
            # Transaction block to move from temp to Processing ZSET
            pipe = client.pipeline()
            pipe.zadd(self.q_processing, {task_id: deadline})
            pipe.lrem(temp_list, 1, task_id)
            await pipe.execute()
            
            return task_id

        except Exception as e:
            logger.error(f"[Redis Queue] Failed dequeue: {e}")
            await asyncio.sleep(timeout)
            return None

    async def ack_task(self, task_id: str) -> bool:
        """Acknowledge task completion by removing from processing."""
        client = await self._get_client()
        if not client:
            return False
            
        try:
            res = await client.zrem(self.q_processing, task_id)
            return bool(res)
        except Exception as e:
            logger.error(f"[Redis Queue] Failed ack {task_id}: {e}")
            return False

    async def nack_task_to_delayed(self, task_id: str, delay_sec: int = 15) -> bool:
        """Negative acknowledge: move task from processing to delayed ZSET for backoff."""
        client = await self._get_client()
        if not client:
            return False
            
        try:
            unlock_time = self._utc_now_timestamp() + delay_sec
            pipe = client.pipeline()
            pipe.zadd(self.q_delayed, {task_id: unlock_time})
            pipe.zrem(self.q_processing, task_id)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"[Redis Queue] Failed NACK {task_id}: {e}")
            return False

    async def move_to_deadletter(self, task_id: str) -> bool:
        """Move a poison task to the deadletter list."""
        client = await self._get_client()
        if not client:
            return False
            
        try:
            pipe = client.pipeline()
            pipe.lpush(self.q_deadletter, task_id)
            pipe.zrem(self.q_processing, task_id)
            await pipe.execute()
            return True
        except Exception as e:
            logger.error(f"[Redis Queue] Failed deadletter {task_id}: {e}")
            return False

    async def touch_visibility_timeout(self, task_id: str, added_time_sec: int = 180) -> bool:
        """Renew the visibility timeout (called during task heartbeat)."""
        client = await self._get_client()
        if not client:
            return False
        
        try:
            # Only update if it actually exists in processing
            score = await client.zscore(self.q_processing, task_id)
            if score is not None:
                new_deadline = self._utc_now_timestamp() + added_time_sec
                await client.zadd(self.q_processing, {task_id: new_deadline})
                return True
            return False
        except Exception:
            return False

    # --- Lock Methods ---

    async def acquire_lock(self, lock_key: str, owner_id: str, ttl_seconds: int) -> bool:
        """Try to acquire a lock. Returns True if successful."""
        client = await self._get_client()
        if not client:
            return False
        try:
            res = await client.set(lock_key, owner_id, nx=True, ex=ttl_seconds)
            return bool(res)
        except Exception as e:
            logger.error(f"[Redis Lock] Failed acquire {lock_key}: {e}")
            return False

    async def renew_lock(self, lock_key: str, owner_id: str, ttl_seconds: int) -> bool:
        """Renew lock using Lua comparison to prevent renewing someone else's lock."""
        client = await self._get_client()
        if not client:
            return False
        try:
            res = await client.eval(LUA_RENEW_LEASE, 1, lock_key, owner_id, ttl_seconds)
            return bool(res)
        except Exception as e:
            logger.error(f"[Redis Lock] Failed renew {lock_key}: {e}")
            return False

    async def release_lock(self, lock_key: str, owner_id: str) -> bool:
        """Release lock safely using Lua script."""
        client = await self._get_client()
        if not client:
            return False
        try:
            res = await client.eval(LUA_COMPARE_AND_DELETE, 1, lock_key, owner_id)
            return bool(res)
        except Exception as e:
            logger.error(f"[Redis Lock] Failed release {lock_key}: {e}")
            return False

    async def get_lock_owner(self, lock_key: str) -> Optional[str]:
        client = await self._get_client()
        if not client:
            return None
        try:
            owner = await client.get(lock_key)
            return owner if owner else None
        except Exception:
            return None

    @classmethod
    async def get_all_queue_metrics(cls) -> dict:
        """Aggregates all queue lengths across all pack_ids."""
        from backend.app.services.cache.async_redis import get_async_redis_client
        client = await get_async_redis_client()
        if not client:
            return {"status": "unavailable"}
            
        metrics = {
            "status": "active",
            "global": {
                "pending": 0,
                "processing": 0,
                "delayed": 0,
                "deadletter": 0,
            },
            "packs": {}
        }
        
        async def _scan_and_aggregate(queue_type: str, measure_func: str):
            cursor = b'0'
            while cursor:
                cursor, keys = await client.scan(cursor=cursor, match=f"mindscape:queue:{queue_type}:*", count=100)
                for k in keys:
                    pack = k.decode().split(":")[-1]
                    if pack not in metrics["packs"]:
                        metrics["packs"][pack] = {"pending": 0, "processing": 0, "delayed": 0, "deadletter": 0}
                    
                    if measure_func == "llen":
                        length = await client.llen(k)
                    else:
                        length = await client.zcard(k)
                        
                    metrics["global"][queue_type] += length
                    metrics["packs"][pack][queue_type] += length
                if cursor == b'0':
                    break
                    
        try:
            await _scan_and_aggregate("pending", "llen")
            await _scan_and_aggregate("processing", "zcard")
            await _scan_and_aggregate("delayed", "zcard")
            await _scan_and_aggregate("deadletter", "llen")
        except Exception as e:
            logger.error(f"[Redis Metrics] Failed to aggregate Redis metrics: {e}")
            metrics["status"] = "error"
            
        return metrics
