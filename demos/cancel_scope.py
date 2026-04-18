import asyncbis


async def failing_task():
    await asyncbis.sleep(0.5)
    raise Exception("failing task")


async def main():
    print("main task started")
    asyncbis.create_task(failing_task())
    try:
        print(await asyncbis.sleep(1))
    finally:
        print("finalizing")
        await asyncbis.shield(asyncbis.sleep(0.5))
        print("finalization done")

    print("this should not be reached")


asyncbis.run(main())
