import asyncio
from typing import Any

from ._asyncio_patch import patch_asyncio as patch_asyncio
from ._cancelscopes import CancelScope as CancelScope
from ._eventloop import get_event_loop_policy as get_event_loop_policy
from ._eventloop import new_event_loop as new_event_loop
from ._eventloop import set_event_loop_policy as set_event_loop_policy
from ._runners import run as run
from ._taskgroups import TaskGroup as TaskGroup
from ._timeouts import Timeout as Timeout
from ._timeouts import timeout as timeout
from ._timeouts import timeout_at as timeout_at


def __getattr__(name: str) -> Any:
    return getattr(asyncio, name)
