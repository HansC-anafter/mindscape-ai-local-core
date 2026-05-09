import asyncio
import functools
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, TypeVar

_T = TypeVar("_T")

_UI_READ_WORKERS = max(2, int(os.getenv("MINDSCAPE_UI_READ_WORKERS", "6")))
_UI_READ_EXECUTOR = ThreadPoolExecutor(
    max_workers=_UI_READ_WORKERS,
    thread_name_prefix="ui-read",
)


async def run_ui_read(func: Callable[..., _T], *args: Any, **kwargs: Any) -> _T:
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(_UI_READ_EXECUTOR, call)
