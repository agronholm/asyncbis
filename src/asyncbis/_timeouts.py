from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import TracebackType
from typing import final

from ._cancelscopes import CancelScope as CancelScope


@final
class Timeout:
    def __init__(self, when: float | None, *, shield: bool = False) -> None:
        self._cancel_scope = CancelScope(deadline=when, shield=shield)

    async def __aenter__(self) -> Timeout:
        self._cancel_scope.__enter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        return self._cancel_scope.__exit__(exc_type, exc_val, exc_tb)

    def __repr__(self) -> str:
        info = [""]
        if self._state() == "entered":
            deadline = self._cancel_scope.deadline
            when = round(deadline, 3) if deadline is not None else None
            info.append(f"when={when}")

        info_str = " ".join(info)
        return f"<Timeout [{self._state()}]{info_str}>"

    def _state(self) -> str:
        if not self._cancel_scope._entered:
            return "created"
        elif self._cancel_scope._active:
            if self._cancel_scope.deadline_expired:
                return "expiring"
            else:
                return "active"
        elif self._cancel_scope.deadline_expired:
            return "expired"
        else:
            return "active"

    def when(self) -> float | None:
        return self._cancel_scope.deadline

    def expired(self) -> bool:
        return self._cancel_scope.deadline_expired

    def reschedule(self, when: float | None) -> None:
        match self._state():
            case "created":
                raise RuntimeError("Timeout has not been entered")
            case "active":
                pass
            case state:
                raise RuntimeError(
                    f"Cannot change state of {state} Timeout",
                )

        self._cancel_scope.deadline = when


@asynccontextmanager
async def timeout(delay: float, *, shield: bool = False) -> AsyncGenerator[Timeout]:
    when = asyncio.get_running_loop().time() + delay
    async with Timeout(when, shield=shield) as ct:
        yield ct


def timeout_at(when: float, *, shield: bool = False) -> Timeout:
    return Timeout(when, shield=shield)
