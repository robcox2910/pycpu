"""Tests for the latch, flip-flop, clock and register.

Expected values are plain Python numbers; the circuits do the remembering.
"""

import pytest

from pycpu.arithmetic import ripple_adder
from pycpu.circuit import Circuit
from pycpu.logic import buffer_into
from pycpu.memory import Register, d_flip_flop, d_latch, make_clock
from pycpu.simulator import Simulator

WORD = 16
LOW_BYTE = 8
FIRST_VALUE = 0x1234
SECOND_VALUE = 0xBEEF
SURVIVOR = 0xCAFE
MANY_TICKS = 10
COUNT_BEATS = 300
BYTE_RANGE = 256
LATCH_GATES = 4
SHIFT_VALUE = 0x5A
TWO_BITS_OF_CELLS = 4
FLIP_FLOP_GATES = 9


def test_latch_follows_while_enabled_then_holds() -> None:
    """A latch copies its data while enabled and keeps the last value after."""
    c = Circuit()
    data, enable = c.input("data"), c.input("enable")
    q, q_n = d_latch(c, data, enable)
    sim = Simulator(c)
    assert c.gate_count == LATCH_GATES
    for wire, value in [(enable, 1), (data, 1)]:
        sim.set(wire, value)
    sim.settle()
    assert (sim.get(q), sim.get(q_n)) == (1, 0)
    sim.set(enable, 0)
    sim.set(data, 0)
    sim.settle()
    assert sim.get(q) == 1  # held
    sim.set(enable, 1)
    sim.settle()
    assert (sim.get(q), sim.get(q_n)) == (0, 1)  # follows again
    sim.set(enable, 0)
    sim.set(data, 1)
    sim.settle()
    assert sim.get(q) == 0


def test_flip_flop_changes_only_on_rising_edge() -> None:
    """A flip-flop ignores data while clk is steady, and copies it as clk rises."""
    c = Circuit()
    data, clk = c.input("data"), c.input("clk")
    q = d_flip_flop(c, data, clk)
    sim = Simulator(c)
    assert c.gate_count == FLIP_FLOP_GATES
    sim.set(data, 1)
    sim.settle()
    assert sim.get(q) == 0  # clk low: not yet
    sim.set(clk, 1)
    sim.settle()
    assert sim.get(q) == 1  # the rising edge
    sim.set(data, 0)
    sim.settle()
    assert sim.get(q) == 1  # clk high: ignored
    sim.set(clk, 0)
    sim.settle()
    assert sim.get(q) == 1  # the falling edge does nothing
    sim.set(clk, 1)
    sim.settle()
    assert sim.get(q) == 0  # next rising edge picks up the 0


def test_tick_pulses_write_before_clk_and_returns_both_low() -> None:
    """A latch on `write` photographs a register's old value before `clk` changes it."""
    c = Circuit()
    clock = make_clock(c)
    data = c.input("data")
    r = d_flip_flop(c, data, clock.clk)
    snap, _ = d_latch(c, r, clock.write)
    sim = Simulator(c)
    sim.set(data, 1)
    sim.tick(clock)
    assert (sim.get(r), sim.get(snap)) == (1, 0)
    sim.tick(clock)
    assert (sim.get(r), sim.get(snap)) == (1, 1)
    assert (sim.get(clock.clk), sim.get(clock.write)) == (0, 0)


def test_register_holds_without_load_and_loads_with_it() -> None:
    """With load 0 a tick keeps the value; with load 1 it takes the data."""
    c = Circuit()
    clock = make_clock(c)
    data = c.bus_input("d", WORD)
    load = c.input("load")
    reg = Register(c, WORD, data, load, clock, "r")
    sim = Simulator(c)
    reg.poke(sim, FIRST_VALUE)
    sim.set_bus(data, SECOND_VALUE)
    sim.tick(clock)
    assert reg.peek(sim) == FIRST_VALUE
    sim.set(load, 1)
    sim.tick(clock)
    assert reg.peek(sim) == SECOND_VALUE
    assert sim.get_bus(reg.q) == SECOND_VALUE


def test_poke_survives_many_ticks() -> None:
    """A poked value is not undone by the master latch on later ticks."""
    c = Circuit()
    clock = make_clock(c)
    data = c.bus_input("d", WORD)
    reg = Register(c, WORD, data, c.input("load"), clock, "r")
    sim = Simulator(c)
    reg.poke(sim, SURVIVOR)
    for _ in range(MANY_TICKS):
        sim.tick(clock)
    assert reg.peek(sim) == SURVIVOR


def test_poke_rejects_a_value_that_does_not_fit() -> None:
    """Poking 2**width is refused, like set_bus."""
    c = Circuit()
    clock = make_clock(c)
    reg = Register(c, LOW_BYTE, c.bus_input("d", LOW_BYTE), c.input("load"), clock, "r")
    sim = Simulator(c)
    with pytest.raises(ValueError, match="does not fit"):
        reg.poke(sim, BYTE_RANGE)


def test_register_needs_data_as_wide_as_itself() -> None:
    """A data bus of the wrong width is refused."""
    c = Circuit()
    clock = make_clock(c)
    with pytest.raises(ValueError, match="width"):
        Register(c, WORD, c.bus_input("d", LOW_BYTE), c.input("load"), clock, "r")


def test_poke_pairs_writes_both_wires_and_waits_for_settle() -> None:
    """poke_pairs sets q and its opposite at once; settle then keeps them."""
    c = Circuit()
    data, enable = c.input("data"), c.input("enable")
    q, q_n = d_latch(c, data, enable)
    c.state_pair("cell", q, q_n)
    sim = Simulator(c)
    sim.poke_pairs([(q, q_n)], 1)
    assert (sim.get(q), sim.get(q_n)) == (1, 0)
    sim.settle()
    assert (sim.get(q), sim.get(q_n)) == (1, 0)
    sim.poke_pairs([(q, q_n)], 0)
    sim.settle()
    assert (sim.get(q), sim.get(q_n)) == (0, 1)


def test_state_pairs_are_named_by_their_part() -> None:
    """A flip-flop registers its master and slave cells under its part's path."""
    c = Circuit()
    clock = make_clock(c)
    Register(c, 2, c.bus_input("d", 2), c.input("load"), clock, "r")
    names = [name for name, _, _ in c.state_pairs]
    assert "r.bit0.master" in names
    assert "r.bit1.slave" in names
    assert len(names) == TWO_BITS_OF_CELLS


def test_a_counter_built_from_register_and_adder_counts() -> None:
    """A register fed its own value plus one counts, wrapping at 256."""
    c = Circuit()
    clock = make_clock(c)
    nxt = tuple(c.wire_placeholder() for _ in range(LOW_BYTE))
    counter = Register(c, LOW_BYTE, nxt, c.high, clock, "counter")
    one = (c.high, *([c.low] * (LOW_BYTE - 1)))
    total, _ = ripple_adder(c, counter.q, one, c.low)
    for wire, bit in zip(nxt, total, strict=True):
        buffer_into(c, bit, wire)
    sim = Simulator(c)
    for beat in range(1, COUNT_BEATS + 1):
        sim.tick(clock)
        assert counter.peek(sim) == beat % BYTE_RANGE


def test_power_on_state_is_identical_across_builds() -> None:
    """Two builds of the same circuit start with the same register contents."""

    def build() -> tuple[Simulator, Register]:
        c = Circuit()
        clock = make_clock(c)
        data = c.bus_input("d", WORD)
        reg = Register(c, WORD, data, c.input("load"), clock, "r")
        return Simulator(c), reg

    (one, reg_one), (two, reg_two) = build(), build()
    assert reg_one.peek(one) == reg_two.peek(two) == 0


def test_poke_pairs_refuses_a_value_that_is_not_a_bit() -> None:
    """Only 0 or 1 can be written into a storage cell."""
    c = Circuit()
    q_n = c.wire_placeholder()
    q = c.nand(c.high, q_n)
    c.nand_into(c.high, q, q_n)
    sim = Simulator(c)
    with pytest.raises(ValueError, match="0 or 1"):
        sim.poke_pairs([(q, q_n)], 2)


def test_chained_registers_shift_one_step_per_tick() -> None:
    """Each register copies the one before it, so a value moves one place a tick."""
    c = Circuit()
    clock = make_clock(c)
    data = c.bus_input("d", LOW_BYTE)
    first = Register(c, LOW_BYTE, data, c.high, clock, "first")
    second = Register(c, LOW_BYTE, first.q, c.high, clock, "second")
    third = Register(c, LOW_BYTE, second.q, c.high, clock, "third")
    sim = Simulator(c)
    sim.set_bus(data, SHIFT_VALUE)
    sim.tick(clock)
    assert (first.peek(sim), second.peek(sim), third.peek(sim)) == (SHIFT_VALUE, 0, 0)
    sim.tick(clock)
    assert (first.peek(sim), second.peek(sim), third.peek(sim)) == (SHIFT_VALUE,) * 2 + (0,)
    sim.tick(clock)
    assert (first.peek(sim), second.peek(sim), third.peek(sim)) == (SHIFT_VALUE,) * 3
