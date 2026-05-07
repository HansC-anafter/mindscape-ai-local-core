import asyncio
import time

from backend.app.services.system_health_checker import run_readiness_coro_in_worker


def test_readiness_worker_keeps_running_event_loop_responsive():
    async def _scenario():
        async def blocking_readiness():
            time.sleep(0.2)
            return "ready"

        readiness_task = asyncio.create_task(
            run_readiness_coro_in_worker(lambda: blocking_readiness())
        )
        await asyncio.wait_for(asyncio.sleep(0.02), timeout=0.1)

        return await readiness_task

    assert asyncio.run(_scenario()) == "ready"
