from __future__ import annotations

import sys

from ._cancelscopes import shield
from ._eventloop import get_event_loop, get_event_loop_policy, set_event_loop_policy
from ._taskgroups import TaskGroup
from ._tasks import AsyncbisTask


def patch_asyncio() -> None:
    """Patch asyncio to use asyncbis's versions of SC-compatible classes and functions."""
    import asyncio.tasks

    if sys.version_info >= (3, 11):
        import asyncio.taskgroups
        import asyncio.tasks

        from ._timeouts import Timeout, timeout, timeout_at

        asyncio.taskgroups.TaskGroup = asyncio.TaskGroup = TaskGroup
        asyncio.Timeout = Timeout
        asyncio.timeout = timeout
        asyncio.timeout_at = timeout_at

    asyncio.Task = asyncio.tasks.Task = AsyncbisTask
    asyncio.get_event_loop = get_event_loop
    asyncio.get_event_loop_policy = get_event_loop_policy
    asyncio.set_event_loop_policy = set_event_loop_policy
    asyncio.shield = shield
