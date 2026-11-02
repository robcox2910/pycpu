"""Start the Bench with `python -m pycpu`.

Like switching on the lights in the workshop: this builds the Bench app and serves
it on this computer only (127.0.0.1), then prints the address to visit.
"""

import sys

from pynet.loop import run
from pyweb.aserver import AsyncServer

from pycpu.bench.app import create_bench

HOST = "127.0.0.1"
PORT = 8765


async def serve() -> None:
    """Serve the Bench until the user presses Ctrl+C."""
    server = AsyncServer(create_bench())
    await server.start(HOST, PORT)
    sys.stdout.write(f"The Bench is open at http://{HOST}:{server.port}\n")
    sys.stdout.write("Press Ctrl+C to close it.\n")
    sys.stdout.flush()
    try:
        await server.serve_forever()
    finally:
        await server.close()


def main() -> None:
    """Run the Bench server, quietly stopping on Ctrl+C."""
    try:
        run(serve())
    except KeyboardInterrupt:
        sys.stdout.write("\nThe Bench is closed.\n")


if __name__ == "__main__":
    main()
