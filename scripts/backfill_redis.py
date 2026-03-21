import asyncio
import os
import sys

from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.models.workspace.enums import TaskStatus

async def backfill():
    store = TasksStore()
    redis = RedisRunnerQueueStore()
    tasks = store.list_tasks(status=TaskStatus.PENDING, limit=1000)
    count = 0
    for t in tasks:
        await redis.enqueue_task(str(t.id))
        count += 1
    print(f"Backfilled {count} tasks to Redis")

if __name__ == "__main__":
    asyncio.run(backfill())
