import asyncio
from typing import Any, Awaitable, Callable, Optional, Tuple


TerminateProcess = Callable[..., Awaitable[None]]
ActivityProbe = Callable[[], Tuple[Tuple[str, int, int], ...]]


async def _pump_stream(
    stream: Any,
    queue: asyncio.Queue[tuple[str, Optional[bytes]]],
    stream_name: str,
) -> None:
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            await queue.put((stream_name, None))
            return
        await queue.put((stream_name, chunk))


async def _wait_with_communicate_fallback(
    *,
    proc: Any,
    runtime_name: str,
    execution_id: str,
    stall_timeout: Optional[float],
    activity_probe: ActivityProbe,
    terminate_process: TerminateProcess,
) -> tuple[bytes, bytes]:
    communicate_task = asyncio.create_task(proc.communicate())
    try:
        if not stall_timeout or stall_timeout <= 0:
            return await communicate_task

        poll_interval = min(5.0, max(0.5, stall_timeout / 6.0))
        loop = asyncio.get_running_loop()
        last_activity_at = loop.time()
        last_activity = activity_probe()

        while True:
            done, _ = await asyncio.wait({communicate_task}, timeout=poll_interval)
            if communicate_task in done:
                return await communicate_task

            current_activity = activity_probe()
            if current_activity != last_activity:
                last_activity = current_activity
                last_activity_at = loop.time()
                continue

            if loop.time() - last_activity_at < stall_timeout:
                continue

            await terminate_process(
                proc=proc,
                communicate_task=communicate_task,
                wait_timeout=poll_interval,
            )
            raise asyncio.TimeoutError(
                f"{runtime_name} subprocess stalled after {int(stall_timeout)}s "
                f"without file or message activity ({execution_id})"
            )
    except asyncio.CancelledError:
        await terminate_process(proc=proc, communicate_task=communicate_task)
        raise


async def wait_for_streaming_subprocess_activity(
    *,
    proc: Any,
    runtime_name: str,
    execution_id: str,
    stall_timeout: Optional[float],
    activity_probe: ActivityProbe,
    terminate_process: TerminateProcess,
) -> tuple[bytes, bytes]:
    stdout_stream = getattr(proc, "stdout", None)
    stderr_stream = getattr(proc, "stderr", None)
    if stdout_stream is None and stderr_stream is None:
        return await _wait_with_communicate_fallback(
            proc=proc,
            runtime_name=runtime_name,
            execution_id=execution_id,
            stall_timeout=stall_timeout,
            activity_probe=activity_probe,
            terminate_process=terminate_process,
        )

    if not stall_timeout or stall_timeout <= 0:
        stdout, stderr = await proc.communicate()
        return stdout or b"", stderr or b""

    poll_interval = min(5.0, max(0.5, stall_timeout / 6.0))
    loop = asyncio.get_running_loop()
    last_activity_at = loop.time()
    last_activity = activity_probe()
    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    closed_streams: set[str] = set()
    queue: asyncio.Queue[tuple[str, Optional[bytes]]] = asyncio.Queue()
    pump_tasks: list[asyncio.Task[None]] = []

    if stdout_stream is not None:
        pump_tasks.append(asyncio.create_task(_pump_stream(stdout_stream, queue, "stdout")))
    else:
        closed_streams.add("stdout")
    if stderr_stream is not None:
        pump_tasks.append(asyncio.create_task(_pump_stream(stderr_stream, queue, "stderr")))
    else:
        closed_streams.add("stderr")

    try:
        while True:
            if len(closed_streams) >= 2:
                if getattr(proc, "returncode", None) is None:
                    await proc.wait()
                return b"".join(stdout_chunks), b"".join(stderr_chunks)

            try:
                stream_name, chunk = await asyncio.wait_for(queue.get(), timeout=poll_interval)
            except asyncio.TimeoutError:
                current_activity = activity_probe()
                if current_activity != last_activity:
                    last_activity = current_activity
                    last_activity_at = loop.time()
                    continue
                if loop.time() - last_activity_at < stall_timeout:
                    continue
                await terminate_process(proc=proc, wait_timeout=poll_interval)
                raise asyncio.TimeoutError(
                    f"{runtime_name} subprocess stalled after {int(stall_timeout)}s "
                    f"without file, message, stdout, or stderr activity ({execution_id})"
                )

            if chunk is None:
                closed_streams.add(stream_name)
                continue

            if stream_name == "stdout":
                stdout_chunks.append(chunk)
            else:
                stderr_chunks.append(chunk)
            last_activity_at = loop.time()
    except asyncio.CancelledError:
        await terminate_process(proc=proc)
        raise
    finally:
        for task in pump_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*pump_tasks, return_exceptions=True)
