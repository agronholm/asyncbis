import asyncbis


async def main() -> None:
    print("main task started")
    await asyncbis.sleep(0)
    try:
        async with asyncbis.timeout(0.5):
            with asyncbis.CancelScope(shield=True):
                print("sleeping")
                await asyncbis.sleep(1)
                print("sleep done")

            await asyncbis.sleep(0)
            print("this should not be reached")
    except TimeoutError:
        print("timeout")

    print("main task finished")


asyncbis.run(main())
