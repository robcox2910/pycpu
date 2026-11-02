"""Turn the ALU's dial through every setting.

The ALU is like a calculator with a dial: the same two numbers go in, and the
dial picks whether they are added, subtracted, compared bit by bit or shifted.

Run this with: uv run python examples/alu_tour.py
"""

from pycpu.arithmetic import AluOp, alu
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

FIRST = 12
SECOND = 5


def main() -> None:
    """Build one ALU and print every operation's result and flags."""
    c = Circuit()
    a = c.bus_input("a", 16)
    b = c.bus_input("b", 16)
    op = c.bus_input("op", 3)
    out = alu(c, a, b, op)
    sim = Simulator(c)
    sim.set_bus(a, FIRST)
    sim.set_bus(b, SECOND)
    print(f"a = {FIRST}, b = {SECOND}, using {c.gate_count} NAND gates")
    for setting in AluOp:
        sim.set_bus(op, setting)
        sim.settle()
        flags = {
            "zero": sim.get(out.zero),
            "negative": sim.get(out.negative),
            "carry": sim.get(out.carry),
            "overflow": sim.get(out.overflow),
        }
        lit = [name for name, value in flags.items() if value] or ["none"]
        print(f"{setting.name:<6} -> {sim.get_bus(out.result):>5}   flags: {', '.join(lit)}")


if __name__ == "__main__":
    main()
