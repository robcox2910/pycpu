"""Start the Cockpit with `python -m pycpu`.

Like switching on the lights in the workshop: this builds the Cockpit app, with a
whole computer made of NAND gates on it, and serves it on this computer only
(127.0.0.1) with the tour, the example Pebble program that uses everything PyCPU can
run, already loaded. Then it prints the address to visit. Building the full-size
computer takes a few seconds, so it says so first.
"""

import sys

from pynet.loop import run
from pyweb.aserver import AsyncServer

from pycpu.cockpit.app import create_cockpit
from pycpu.memory import RAM_ADDRESS_BITS

HOST = "127.0.0.1"
PORT = 8765
ADDRESS_BITS = RAM_ADDRESS_BITS  # the full 4K words of memory
START_EXAMPLE = "tour"  # the example program loaded when the Cockpit opens


async def open_cockpit(
    port: int = PORT, address_bits: int = ADDRESS_BITS, start_example: str | None = START_EXAMPLE
) -> AsyncServer:
    """Switch the Cockpit on at 127.0.0.1 and return the running server.

    Args:
        port: The port to listen on. Use 0 to let the computer pick a free one.
        address_bits: How many address wires the Cockpit computer's RAM has.
        start_example: The example program to load at the start (the tour unless told
            otherwise), or None for the little assembly demo.

    """
    server = AsyncServer(create_cockpit(address_bits, start_example))
    await server.start(HOST, port)
    return server


def banner(server: AsyncServer) -> str:
    """Return the two lines that tell the user where the Cockpit is."""
    return f"The Cockpit is open at http://{HOST}:{server.port}\nPress Ctrl+C to close it.\n"


async def serve() -> None:
    """Serve the Cockpit until the user presses Ctrl+C."""
    sys.stdout.write("Building the computer from NAND gates...\n")
    sys.stdout.flush()
    server = await open_cockpit(PORT, ADDRESS_BITS, START_EXAMPLE)
    sys.stdout.write(banner(server))
    sys.stdout.flush()
    try:
        await server.serve_forever()
    finally:
        await server.close()


def main() -> None:
    """Run the Cockpit server, quietly stopping on Ctrl+C."""
    try:
        run(serve())
    except KeyboardInterrupt:
        sys.stdout.write("\nThe Cockpit is closed.\n")


if __name__ == "__main__":
    main()
