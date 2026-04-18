import asyncbis


async def taskfunc() -> None:
    print("this point should be reached")
    await asyncbis.sleep(0)
    print("this point should NOT be reached")


async def main() -> None:
    print("main task started")
    try:
        async with asyncbis.TaskGroup() as tg:
            task = tg.create_task(taskfunc())
            task.cancel()
    finally:
        print("main task ending")


asyncbis.run(main())
