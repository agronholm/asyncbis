import signal
import sys
from asyncio import _get_running_loop, set_event_loop
from collections.abc import Callable, Coroutine
from contextlib import ExitStack
from functools import partial
from inspect import iscoroutine
from threading import current_thread, main_thread
from types import FrameType
from typing import Any, TypeVar

from ._eventloop import AsyncbisEventLoop

try:
    import sniffio
except ImportError:
    sniffio = None

T = TypeVar("T")


def sigint_handler(
    sig: int,
    frame: FrameType | None,
    *,
    loop: AsyncbisEventLoop,
    old_handler: Callable[[int, FrameType | None], Any] | int | None,
) -> Any:
    if loop._root_task_group is not None and not loop._root_task_group.cancel_scope.cancel_called:
        signame = f"signal({signal.strsignal(sig) or sig})"
        print(f"Received {signame}, shutting down event loop", file=sys.stderr)
        loop._root_task_group.cancel(f"Cancelled by {signame}")
    elif callable(old_handler):
        old_handler(sig, frame)


def run(main: Coroutine[Any, Any, T], *, debug: bool | None = None) -> T:
    if _get_running_loop() is not None:
        raise RuntimeError("asyncbis.run() cannot be called from a running event loop")

    if not iscoroutine(main):
        raise ValueError(f"a coroutine was expected, got {main!r}")

    loop = AsyncbisEventLoop()
    with ExitStack() as stack:
        set_event_loop(loop)
        stack.callback(loop.close)
        stack.callback(set_event_loop, None)

        if debug is not None:
            loop.set_debug(debug)

        if sniffio is not None:
            token = sniffio.current_async_library_cvar.set("asyncbis")
            stack.callback(sniffio.current_async_library_cvar.reset, token)

        # Handle SIGINT by cancelling the root task group
        if current_thread() is main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                old_handler = signal.getsignal(signum)
                try:
                    signal.signal(
                        signum, partial(sigint_handler, loop=loop, old_handler=old_handler)
                    )
                except ValueError:
                    pass  # gh-91880
                else:
                    stack.callback(signal.signal, signum, old_handler)

        return loop.run_until_complete(loop._root_task(main))
