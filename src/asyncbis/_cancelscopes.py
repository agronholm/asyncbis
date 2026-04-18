from __future__ import annotations

import sys
from asyncio import CancelledError, TimerHandle, current_task
from collections.abc import Awaitable
from types import TracebackType
from typing import TYPE_CHECKING, Any, TypeVar, cast, final

if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup

if TYPE_CHECKING:
    from ._tasks import AsyncbisTask


T = TypeVar("T")


@final
class CancelScope:
    _host_task: AsyncbisTask[Any] | None = None
    _entered = False
    _active = False
    _cancel_called = False
    _cancel_message: str | None = None
    _effectively_cancelled = False
    _deadline_expired = False
    _timeout_handle: TimerHandle | None = None

    def __init__(
        self,
        *,
        parent: CancelScope | None = None,
        deadline: float | None = None,
        shield: bool = False,
    ) -> None:
        self._deadline = deadline
        self._shield = shield
        self._parent = parent
        self._children: list[CancelScope] = []

    @property
    def deadline(self) -> float | None:
        return self._deadline

    @deadline.setter
    def deadline(self, value: float | None) -> None:
        self._deadline = value
        self._cancel_timeout()

    @property
    def deadline_expired(self) -> bool:
        return self._deadline_expired

    @property
    def cancel_called(self) -> bool:
        return self._cancel_called

    @property
    def cancel_message(self) -> str | None:
        return self._cancel_message

    @property
    def effectively_cancelled(self) -> bool:
        return self._effectively_cancelled

    @property
    def shield(self) -> bool:
        return self._shield

    @shield.setter
    def shield(self, value: bool) -> None:
        # If the scope is unshielded, propagate cancellation from the parent
        if (
            not self._effectively_cancelled
            and value
            and not self._shield
            and self._parent is not None
            and self._parent._effectively_cancelled
        ):
            self._effectively_cancelled = True
            self._propagate_cancellation(self._parent._cancel_message)

        self._shield = value

    def __enter__(self) -> CancelScope:
        if self._entered:
            raise RuntimeError("This CancelScope has already been entered")

        if self._host_task is None:
            if (host_task := current_task()) is None:
                raise RuntimeError("No task is currently running")

            self._host_task = cast("AsyncbisTask[Any]", host_task)
            self._parent = self._host_task._cancel_scope
            self._host_task._cancel_scope = self

        # Attach to the parent scope if any
        if self._parent is not None:
            self._parent._children.append(self)

        self._set_timeout()

        self._entered = True
        self._active = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        if not self._active:
            raise RuntimeError("This cancel scope is not active")

        self._active = False
        if self._children:
            raise RuntimeError(
                f"Cancel scope stack violation: this scope still has "
                f"{len(self._children)} active child scope(s)"
            )

        assert self._host_task is not None
        self._host_task._cancel_scope = self._parent
        del self._host_task

        if self._parent is not None:
            self._parent._children.remove(self)

        self._cancel_timeout()
        if isinstance(exc_val, CancelledError):
            if self._deadline_expired:
                raise TimeoutError from exc_val.__cause__

            # Swallow the CancelledError if this is the root scope or
            # the parent scope is not cancelled
            if self._parent is None or not self._parent._effectively_cancelled:
                return True
        elif isinstance(exc_val, BaseExceptionGroup):
            cancelleds, remaining = exc_val.split(CancelledError)
            if remaining:
                raise remaining.with_traceback(exc_tb) from None
            elif cancelleds:
                if self._deadline_expired:
                    raise TimeoutError from exc_val.__cause__
                elif self._cancel_called:
                    return True

        return False

    def cancel(self, msg: object = None) -> None:
        if not self._effectively_cancelled:
            self._cancel_called = True
            self._propagate_cancellation(str(msg) if msg is not None else None)

    def _set_timeout(self) -> None:
        def timeout_callback() -> None:
            self._deadline_expired = True
            self.timeout_handle = None
            self.cancel()

        if self._deadline is not None and self._host_task is not None:
            self._timeout_handle = self._host_task.get_loop().call_at(
                self._deadline, timeout_callback
            )

    def _cancel_timeout(self) -> None:
        if self._timeout_handle is not None:
            self._timeout_handle.cancel()
            self._timeout_handle = None

    def _propagate_cancellation(self, msg: str | None) -> None:
        self._effectively_cancelled = True
        self._cancel_message = msg

        # Cancel any pending operation if this is the effective cancel scope of the host task
        if (host_task := self._host_task) is not None and host_task._cancel_scope is self:
            if (fut_waiter := host_task._fut_waiter) is not None and not fut_waiter.cancelled():
                fut_waiter.cancel(self._cancel_message)

        self._cancel_timeout()

        # Propagate cancellation to unshielded children that aren't shielded or already cancelled
        for child in self._children:
            if not child._shield and not child._effectively_cancelled:
                child._propagate_cancellation(msg)


async def shield(coro: Awaitable[T]) -> T:
    with CancelScope(shield=True):
        return await coro

    assert False, "unreachable"
