import sys
from _contextvars import copy_context
from asyncio import (
    AbstractEventLoop,
    CancelledError,
    InvalidStateError,
    _enter_task,
    _leave_task,
    futures,
)
from asyncio.tasks import _PyTask
from collections.abc import Coroutine
from contextvars import Context
from inspect import isgenerator
from typing import Any, TypeVar

from ._cancelscopes import CancelScope

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override

_T_co = TypeVar("_T_co", covariant=True)


class AsyncbisTask(_PyTask[_T_co]):
    def __init__(
        self,
        coro: Coroutine[Any, Any, _T_co],
        *,
        name: object = None,
        context: Context | None = None,
        loop: AbstractEventLoop,
        parent_cancel_scope: CancelScope | None = None,
    ):
        if sys.version_info >= (3, 11):
            super().__init__(coro, loop=loop, name=name, context=context)
        else:
            super().__init__(coro, loop=loop, name=name)
            self._context = context or copy_context()

        self._cancel_scope = CancelScope(parent=parent_cancel_scope)
        self._cancel_scope._host_task = self
        self._cancel_scope.__enter__()

    @override
    def cancel(self, msg: Any = None) -> None:
        self._cancel_scope.cancel(msg)

    def _Task__step(self, exc: BaseException | None = None) -> None:
        if self.done():
            raise InvalidStateError(f"_step(): already done: {self!r}, {exc!r}")

        coro = self._coro
        self._fut_waiter = None

        _enter_task(self._loop, self)
        try:
            if exc is None:
                result = coro.send(None)
            else:
                result = coro.throw(exc)
        except StopIteration as exc:
            super(_PyTask, self).set_result(exc.value)
            if self._cancel_scope is not None:
                self._cancel_scope.__exit__(None, None, None)
        except CancelledError as exc:
            self._cancelled_exc = exc
            super(_PyTask, self).cancel()
            if self._cancel_scope is not None:
                self._cancel_scope.__exit__(None, None, None)
        except (KeyboardInterrupt, SystemExit) as exc:
            super(_PyTask, self).set_exception(exc)
            if self._cancel_scope is not None:
                self._cancel_scope.__exit__(None, None, None)

            raise
        except BaseException as exc:
            super(_PyTask, self).set_exception(exc)
            if self._cancel_scope is not None:
                self._cancel_scope.__exit__(None, None, None)
        else:
            blocking = getattr(result, "_asyncio_future_blocking", None)
            if blocking is not None:
                # Yielded Future must come from Future.__iter__().
                if futures._get_loop(result) is not self._loop:
                    new_exc = RuntimeError(
                        f"Task {self!r} got Future {result!r} attached to a different loop"
                    )
                    self._loop.call_soon(self._Task__step, new_exc, context=self._context)
                elif blocking:
                    if result is self:
                        new_exc = RuntimeError(f"Task cannot await on itself: {self!r}")
                        self._loop.call_soon(self._Task__step, new_exc, context=self._context)
                    else:
                        result._asyncio_future_blocking = False
                        result.add_done_callback(self._Task__wakeup, context=self._context)
                        self._fut_waiter = result
                        if self._cancel_scope.effectively_cancelled:
                            self._fut_waiter.cancel(msg=self._cancel_scope._cancel_message)
                else:
                    new_exc = RuntimeError(
                        f"yield was used instead of yield from in task {self!r} with {result!r}"
                    )
                    self._loop.call_soon(self._Task__step, new_exc, context=self._context)
            elif result is None:
                # Bare yield relinquishes control for one event loop iteration.
                if self._cancel_scope.effectively_cancelled:
                    self._loop.call_soon(
                        self._Task__step,
                        CancelledError(self._cancel_scope._cancel_message),
                        context=self._context,
                    )
                else:
                    self._loop.call_soon(self._Task__step, context=self._context)
            elif isgenerator(result):
                # Yielding a generator is just wrong.
                new_exc = RuntimeError(
                    f"yield was used instead of yield from for "
                    f"generator in task {self!r} with {result!r}"
                )
                self._loop.call_soon(self._Task__step, new_exc, context=self._context)
            else:
                # Yielding something else is an error.
                new_exc = RuntimeError(f"Task got bad yield: {result!r}")
                self._loop.call_soon(self._Task__step, new_exc, context=self._context)
        finally:
            _leave_task(self._loop, self)
            self = None  # Needed to break cycles when an exception occurs.
