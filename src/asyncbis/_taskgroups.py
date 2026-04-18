from __future__ import annotations

import sys
from asyncio import Event
from typing import TYPE_CHECKING, Any, TypeVar, final

from ._cancelscopes import CancelScope

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from contextvars import Context
    from types import TracebackType

    from ._tasks import AsyncbisTask

_T_co = TypeVar("_T_co", covariant=True)


@final
class TaskGroup:
    def __init__(self) -> None:
        self._cancel_scope = CancelScope()
        self._tasks: set[AsyncbisTask[Any]] = set()
        self._exceptions: list[BaseException] = []
        self._exit_event: Event | None = None

    @property
    def cancel_scope(self) -> CancelScope:
        return self._cancel_scope

    @property
    def all_tasks(self) -> frozenset[AsyncbisTask[Any]]:
        return frozenset(self._tasks)

    async def __aenter__(self) -> TaskGroup:
        self._cancel_scope.__enter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if exc_val is not None:
            self._cancel_scope.cancel()

        # Wait for all tasks to exit before returning
        if self._tasks:
            self._exit_event = Event()
            with CancelScope(parent=self._cancel_scope, shield=True):
                await self._exit_event.wait()

        try:
            if self._exceptions:
                raise BaseExceptionGroup("", self._exceptions)
        except BaseExceptionGroup as excgrp:
            if self._cancel_scope.__exit__(type(excgrp), excgrp, excgrp.__traceback__):
                return True

            raise

        return self._cancel_scope.__exit__(exc_type, exc_val, exc_tb)

    def create_task(
        self,
        coro: Coroutine[Any, Any, _T_co],
        *,
        name: object = None,
        context: Context | None = None,
        eager_start: bool | None = None,
    ) -> AsyncbisTask[_T_co]:
        task = self._cancel_scope._host_task.get_loop()._create_task_internal(
            coro, name=name, context=context, parent_cancel_scope=self._cancel_scope
        )
        self._tasks.add(task)
        task.add_done_callback(self.__task_done)
        return task

    def cancel(self, msg: Any = None) -> None:
        if msg is None:
            msg = f"Cancelled via task group {id(self):x}"

        self._cancel_scope.cancel(str(msg))

    def __task_done(self, task: AsyncbisTask[Any]) -> None:
        self._tasks.remove(task)
        if not task.cancelled() and (exc := task.exception()):
            self._exceptions.append(exc)
            self.cancel()

        if self._exit_event is not None and not self._tasks:
            self._exit_event.set()
