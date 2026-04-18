import signal

import asyncbis


async def main() -> None:
    print("main task started")
    with asyncbis.CancelScope(shield=True):
        signal.raise_signal(signal.SIGINT)
        print("sent SIGINT; the sleep should still complete")
        await asyncbis.sleep(1)
        print("sleep done")

    await asyncbis.sleep(1)
    print("this point should not be reached")


asyncbis.run(main())
