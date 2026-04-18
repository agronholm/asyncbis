from __future__ import annotations

import sys
import threading
from asyncio import AbstractEventLoop, base_events, events, futures, tasks
from asyncio import new_event_loop as asyncio_new_event_loop
from collections.abc import Awaitable, Coroutine
from contextvars import Context
from itertools import count
from typing import TYPE_CHECKING, Any, NoReturn, TypeVar

from ._cancelscopes import CancelScope
from ._taskgroups import TaskGroup
from ._tasks import AsyncbisTask

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

if TYPE_CHECKING:
    from asyncio.events import _TaskFactory

_T_co = TypeVar("_T_co", covariant=True)


class AsyncbisEventLoop(AbstractEventLoop):
    def __init__(self) -> None:
        super().__init__()
        self._real_loop = asyncio_new_event_loop()
        self._task_name_counter = count(1)
        self._root_task_group: TaskGroup | None = None

    def __getattribute__(self, item: str) -> Any:
        if item in AsyncbisEventLoop.__dict__:
            return super().__getattribute__(item)

        self_dict = super().__getattribute__("__dict__")
        if item in self_dict:
            return self_dict[item]

        real_loop = super().__getattribute__("_real_loop")
        return getattr(real_loop, item)

    def _create_task_internal(
        self,
        coro: Coroutine[Any, Any, _T_co],
        *,
        name: object = None,
        context: Context | None = None,
        parent_cancel_scope: CancelScope | None = None,
    ) -> AsyncbisTask[_T_co]:
        self._check_closed()

        return AsyncbisTask(
            coro, name=name, context=context, loop=self, parent_cancel_scope=parent_cancel_scope
        )

    async def _root_task(self, main: Coroutine[Any, Any, _T_co]) -> _T_co:
        try:
            async with TaskGroup() as tg:
                self._root_task_group = tg
                main_task = tg.create_task(main)
        finally:
            self._root_task_group = None
            with CancelScope(shield=True):
                await self.shutdown_asyncgens()
                await self.shutdown_default_executor()

        return main_task.result()

    @override
    def create_future(self) -> futures.Future[Any]:
        return futures.Future(loop=self)

    @override
    def create_task(
        self,
        coro: Coroutine[Any, Any, _T_co],
        *,
        name: object = None,
        context: Context | None = None,
        eager_start: bool | None = None,
    ) -> AsyncbisTask[_T_co]:
        if self._root_task_group is None:
            return self._create_task_internal(coro, name="Root task", context=context)

        return self._root_task_group.create_task(
            coro, name=name, context=context, eager_start=eager_start
        )

    @override
    def set_task_factory(self, factory: _TaskFactory | None) -> NoReturn:
        raise NotImplementedError(
            f"set_task_factory() is not supported by {self.__class__.__name__}"
        )

    @override
    def run_forever(self) -> None:
        self._check_closed()
        self._check_running()
        self._set_coroutine_origin_tracking(self._debug)

        old_agen_hooks = sys.get_asyncgen_hooks()
        try:
            self._real_loop._thread_id = threading.get_ident()
            sys.set_asyncgen_hooks(
                firstiter=self._asyncgen_firstiter_hook, finalizer=self._asyncgen_finalizer_hook
            )

            events._set_running_loop(self)
            while True:
                self._run_once()
                if self._stopping:
                    break
        finally:
            self._real_loop._stopping = False
            self._real_loop._thread_id = None
            events._set_running_loop(None)
            self._set_coroutine_origin_tracking(False)
            sys.set_asyncgen_hooks(*old_agen_hooks)

    @override
    def run_until_complete(self, future: Awaitable[_T_co]) -> _T_co:
        self._check_closed()
        self._check_running()

        new_task = not futures.isfuture(future)
        future = tasks.ensure_future(future, loop=self)
        if new_task:
            # An exception is raised if the future didn't complete, so there
            # is no need to log the "destroy pending task" message
            future._log_destroy_pending = False

        future.add_done_callback(base_events._run_until_complete_cb)
        try:
            self.run_forever()
        except:
            if new_task and future.done() and not future.cancelled():
                # The coroutine raised a BaseException. Consume the exception
                # to not log a warning, the caller doesn't have access to the
                # local task.
                future.exception()
            raise
        finally:
            future.remove_done_callback(base_events._run_until_complete_cb)

        if not future.done():
            raise RuntimeError("Event loop stopped before Future completed.")

        return future.result()


def new_event_loop() -> AsyncbisEventLoop:
    return AsyncbisEventLoop()


def get_event_loop() -> NoReturn:
    raise NotImplementedError(
        "This function is not supported on asyncbis. Use get_running_loop() instead."
    )


def get_event_loop_policy() -> NoReturn:
    raise NotImplementedError("This function is not supported on asyncbis")


def set_event_loop_policy(policy: Any) -> NoReturn:
    raise NotImplementedError("This function is not supported on asyncbis")
