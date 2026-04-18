About
=====

This is a research project aimed at fixing some `long-standing problems`_ in asyncio_, at the cost of some
backwards compatibility.

.. _long-standing problems: https://anyio.readthedocs.io/en/stable/why.html
.. _asyncio: https://docs.python.org/3/library/asyncio.html

Differences with standard library asyncio
-----------------------------------------

* Task spawning

  * All tasks (except for the root task which runs all other tasks) belong to task groups
    (``create_task()`` creates tasks in the root task group)
  * If a task raises an exception, it propagates to the parent task
  * If the root task group receives an exception, the event loop is shut down and the exception is propagated
    to the caller of ``run()``
* Cancellation and timeouts

  * All cancellation works in a stateful fashion via ``asyncbis.CancelScope``
  * Every task has its associated ``CancelScope``, and ``Task.cancel()`` sets the task's cancel scope
    into the cancelled state
  * Cancel scopes can be used as context managers to shield arbitrary blocks of async code
    (``with CancelScope(shield=True): ...``)
  * Tasks always run their code up to the first yield point, even when cancelled (this gives them a chance
    to respond to the cancellation by cleaning up any resources they were passed)
  * ``asyncio.shield`` was patched to run the target awaitable inside a shielded cancel scope rather than
    spawning a new task
  * ``timeout()`` and ``timeout_at()`` were reimplemented using cancel scopes and deadlines, and were given
    the optional ``shield`` argument to shield the enclosed code from cancellation for the given duration
  * ``TaskGroup`` was given the ``cancel()`` method to cancel all ()current and newly added) tasks in the group
* Event loop shutdown

  * On ``SIGINT``, the root task group, rather than individual tasks, is cancelled, allowing shielding
    to protect arbitrarily complex shielded task structures from cancellation
  * ``SIGTERM`` is now handled the same way
* Disabled features

  * Custom task classes are not supported, as level cancellation depends on tasks working with cancel scopes
  * The following deprecated functions raise ``NotImplementedError``:

    * ``get_event_loop()``
    * ``get_event_loop_policy()``
    * ``set_event_loop_policy()``

Installation
============

To install, just do::

    pip install git+https://github.com/agronholm/asyncbis

Usage
=====

There are two options for using asyncbis:

#. Call ``asyncbis.patch_asyncio()`` before importing any code that uses asyncio, and then use asyncio normally
#. Import everything directly from ``asyncbis`` instead of ``asyncio``. This makes sure you get the upgraded versions
   of everything.

The entry point is ``asyncbis.run()``:

.. code:: python

    import asyncbis

    async def main():
        print("sleeping")
        await asyncbis.sleep(1)
        print("sleep complete")

    asyncbis.run(main())

Note on sniffio
===============

If sniffio_ is installed, ``asyncbis.run()`` registers the current event loop as ``asyncbis`` rather than ``asyncio``.

.. _sniffio: https://github.com/python-trio/sniffio

Note on AnyIO
=============

An AnyIO backend for ``asyncbis`` is in the works, but not available yet.
