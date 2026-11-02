"""Count with a register that adds one to itself on every clock beat.

Like a mileage counter in a car: each beat of the clock, it remembers its
number plus one, and after its biggest number it rolls back round to zero.

Run this with: uv run python examples/counter.py
"""

from pycpu.arithmetic import ripple_adder
from pycpu.circuit import Circuit
from pycpu.logic import buffer_into
from pycpu.memory import Register, make_clock
from pycpu.simulator import Simulator

WIDTH = 4
BEATS = 20


def main() -> None:
    """Build a 4-bit counter from gates and tick it past its roll-over."""
    c = Circuit()
    clock = make_clock(c)
    next_value = tuple(c.wire_placeholder() for _ in range(WIDTH))
    counter = Register(c, WIDTH, next_value, c.high, clock, "counter")
    one = (c.high, *([c.low] * (WIDTH - 1)))
    total, _ = ripple_adder(c, counter.q, one, c.low)
    for wire, bit in zip(next_value, total, strict=True):
        buffer_into(c, bit, wire)
    sim = Simulator(c)
    print(f"a {WIDTH}-bit counter made of {c.gate_count} NAND gates")
    seen: list[int] = []
    for _ in range(BEATS):
        sim.tick(clock)
        seen.append(counter.peek(sim))
    print("beats:", " ".join(str(n) for n in seen))


if __name__ == "__main__":
    main()
