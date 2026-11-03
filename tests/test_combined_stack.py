"""Slow checks that the whole stack works as one circuit: full RAM, an ALU and registers.

Think of a toy town built from every kind of brick at once. Each brick type has
been tested alone; here we check the town still stands, and that a photograph
of it (`storage`) can rebuild an identical town.
"""

import random

import pytest

from pycpu.arithmetic import AluOp, alu
from pycpu.circuit import Bus, Circuit, Clock, Wire
from pycpu.memory import RAM_ADDRESS_BITS, WORD_BITS, Ram, Register, make_clock
from pycpu.simulator import Simulator

REGISTERS = 8
TICKS = 50
SEED = 2026
WORD_MASK = (1 << WORD_BITS) - 1


class Stack:
    """The full-size RAM, an ALU and eight registers in one circuit."""

    def __init__(self) -> None:
        """Build the circuit and its simulator."""
        c = Circuit()
        self.circuit = c
        self.clock: Clock = make_clock(c)
        self.address: Bus = c.bus_input("address", RAM_ADDRESS_BITS)
        self.data: Bus = c.bus_input("data", WORD_BITS)
        self.write: Wire = c.input("write_enable")
        self.load: Wire = c.input("load")
        self.op: Bus = c.bus_input("op", 3)
        self.ram = Ram(c, self.address, self.data, self.write, self.clock)
        out = alu(c, self.data, self.data, self.op)
        self.registers = [
            Register(c, WORD_BITS, out.result, self.load, self.clock, f"r{i}")
            for i in range(REGISTERS)
        ]
        self.sim = Simulator(c)

    def differing_wires(self, other: Simulator) -> int:
        """Count the wires whose value differs between this simulator and `other`."""
        return sum(self.sim.get(w) != other.get(w) for w in range(self.circuit.wire_count))


@pytest.fixture(scope="module")
def stack() -> Stack:
    """Share one full-size build between the tests, because building is the slow part."""
    return Stack()


@pytest.mark.slow
@pytest.mark.timeout(600)
def test_cloning_the_full_stack_through_storage_gives_no_differing_wires(stack: Stack) -> None:
    """A second simulator restored from the first one's storage matches it wire for wire."""
    rng = random.Random(SEED)  # noqa: S311 - fixed seed, not for secrets
    for i in range(0, 1 << RAM_ADDRESS_BITS, 97):
        stack.ram.poke(stack.sim, i, rng.randrange(1 << WORD_BITS))
    for register in stack.registers:
        register.poke(stack.sim, rng.randrange(1 << WORD_BITS))
    stack.sim.settle()
    clone = Simulator(stack.circuit)
    clone.restore_storage(stack.sim.storage())
    for wire in (stack.write, stack.load, *stack.op, *stack.address, *stack.data):
        clone.set(wire, stack.sim.get(wire))
    clone.settle()
    assert stack.differing_wires(clone) == 0


@pytest.mark.slow
@pytest.mark.timeout(600)
def test_rewinding_after_fifty_ticks_gives_no_differing_wires(stack: Stack) -> None:
    """Restoring saved storage (clock low, settled first) brings back every saved wire."""
    sim, rng = stack.sim, random.Random(SEED)  # noqa: S311 - fixed seed
    saved_wires = bytes(sim.get(w) for w in range(stack.circuit.wire_count))
    saved_storage = sim.storage()
    saved_inputs = [
        (w, sim.get(w)) for w in (stack.write, stack.load, *stack.op, *stack.address, *stack.data)
    ]
    for _ in range(TICKS):
        sim.set_bus(stack.data, rng.randrange(1 << WORD_BITS))
        sim.set_bus(stack.address, rng.randrange(1 << RAM_ADDRESS_BITS))
        sim.set_bus(stack.op, rng.choice(list(AluOp)))
        sim.set(stack.write, rng.randrange(2))
        sim.set(stack.load, rng.randrange(2))
        sim.tick(stack.clock)
    assert sim.storage() != saved_storage
    sim.set(stack.clock.clk, 0)
    sim.set(stack.clock.write, 0)
    sim.settle()
    for wire, value in saved_inputs:
        sim.set(wire, value)
    sim.restore_storage(saved_storage)
    wrong = sum(sim.get(w) != saved_wires[w] for w in range(stack.circuit.wire_count))
    assert wrong == 0
