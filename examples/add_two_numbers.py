"""Add two numbers with nothing but NAND gates.

Like doing a sum on paper, column by column, carrying a 1 when a column
overflows, except every column here is a handful of real gates.

Run this with: uv run python examples/add_two_numbers.py
"""

from pycpu.arithmetic import ripple_adder
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

FIRST = 1234
SECOND = 4321


def main() -> None:
    """Build a 16-bit adder, add two numbers and show what it cost."""
    c = Circuit()
    a = c.bus_input("a", 16)
    b = c.bus_input("b", 16)
    total, carry_out = ripple_adder(c, a, b, c.low)
    sim = Simulator(c)
    sim.set_bus(a, FIRST)
    sim.set_bus(b, SECOND)
    work = sim.settle()
    print(f"{FIRST} + {SECOND} = {sim.get_bus(total)} (carry out {sim.get(carry_out)})")
    print(f"the adder is {c.gate_count} NAND gates; this sum took {work} gate evaluations")


if __name__ == "__main__":
    main()
