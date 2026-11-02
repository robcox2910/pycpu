"""Tests for the logic gates, which are all built from NAND and nothing else."""

from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycpu.circuit import Bus, Circuit, Wire
from pycpu.logic import (
    and_,
    and_bus,
    decoder,
    is_zero,
    mux,
    mux_bus,
    not_,
    not_bus,
    or_,
    or_bus,
    or_many,
    xor,
    xor_bus,
)
from pycpu.simulator import Simulator

WORD = 16
WORD_MAX = (1 << WORD) - 1
SELECT_WIDTH = 3
XOR_GATES = 4
SEVEN = 7
words = st.integers(min_value=0, max_value=WORD_MAX)

TWO_INPUT: dict[str, tuple[Callable[[Circuit, Wire, Wire], Wire], Callable[[int, int], int]]] = {
    "and": (and_, lambda a, b: a & b),
    "or": (or_, lambda a, b: a | b),
    "xor": (xor, lambda a, b: a ^ b),
}
BUS_TWO: dict[str, tuple[Callable[[Circuit, Bus, Bus], Bus], Callable[[int, int], int]]] = {
    "and": (and_bus, lambda a, b: a & b),
    "or": (or_bus, lambda a, b: a | b),
    "xor": (xor_bus, lambda a, b: a ^ b),
}


@pytest.mark.parametrize("name", sorted(TWO_INPUT))
@pytest.mark.parametrize(("x", "y"), [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_two_input_gates_follow_their_truth_tables(name: str, x: int, y: int) -> None:
    """Each two-input gate gives the answer its truth table promises."""
    build, expect = TWO_INPUT[name]
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    out = build(c, a, b)
    sim = Simulator(c)
    sim.set(a, x)
    sim.set(b, y)
    sim.settle()
    assert sim.get(out) == expect(x, y)


@pytest.mark.parametrize(("x", "want"), [(0, 1), (1, 0)])
def test_not_flips_its_input(x: int, want: int) -> None:
    """NOT turns 0 into 1 and 1 into 0."""
    c = Circuit()
    a = c.input("a")
    out = not_(c, a)
    sim = Simulator(c)
    sim.set(a, x)
    sim.settle()
    assert sim.get(out) == want


@pytest.mark.parametrize(
    ("s", "x", "y"), [(s, x, y) for s in (0, 1) for x in (0, 1) for y in (0, 1)]
)
def test_mux_passes_the_chosen_input(s: int, x: int, y: int) -> None:
    """A mux passes `when_0` when select is 0 and `when_1` when select is 1."""
    c = Circuit()
    sel, w0, w1 = c.input("s"), c.input("w0"), c.input("w1")
    out = mux(c, sel, w0, w1)
    sim = Simulator(c)
    sim.set(sel, s)
    sim.set(w0, x)
    sim.set(w1, y)
    sim.settle()
    assert sim.get(out) == (y if s else x)


@given(a=words)
def test_not_bus_flips_every_bit(a: int) -> None:
    """not_bus matches Python's bitwise not, kept to 16 bits."""
    c = Circuit()
    bus = c.bus_input("a", WORD)
    out = not_bus(c, bus)
    sim = Simulator(c)
    sim.set_bus(bus, a)
    sim.settle()
    assert sim.get_bus(out) == ~a & WORD_MAX


@pytest.mark.parametrize("name", sorted(BUS_TWO))
@given(a=words, b=words)
def test_bus_gates_match_python(name: str, a: int, b: int) -> None:
    """Each bus gate matches the Python operator on 16-bit numbers."""
    build, expect = BUS_TWO[name]
    c = Circuit()
    bus_a, bus_b = c.bus_input("a", WORD), c.bus_input("b", WORD)
    out = build(c, bus_a, bus_b)
    sim = Simulator(c)
    sim.set_bus(bus_a, a)
    sim.set_bus(bus_b, b)
    sim.settle()
    assert sim.get_bus(out) == expect(a, b)


@given(a=words, b=words, s=st.integers(min_value=0, max_value=1))
def test_mux_bus_picks_a_whole_word(a: int, b: int, s: int) -> None:
    """mux_bus passes one whole word and ignores the other."""
    c = Circuit()
    sel = c.input("s")
    bus_a, bus_b = c.bus_input("a", WORD), c.bus_input("b", WORD)
    out = mux_bus(c, sel, bus_a, bus_b)
    sim = Simulator(c)
    sim.set(sel, s)
    sim.set_bus(bus_a, a)
    sim.set_bus(bus_b, b)
    sim.settle()
    assert sim.get_bus(out) == (b if s else a)


def test_is_zero_of_zero_is_one() -> None:
    """The number 0 has no bit on, so is_zero says 1."""
    c = Circuit()
    bus = c.bus_input("a", WORD)
    out = is_zero(c, bus)
    sim = Simulator(c)
    sim.set_bus(bus, 0)
    sim.settle()
    assert sim.get(out) == 1


@given(a=words)
def test_is_zero_is_true_only_for_zero(a: int) -> None:
    """is_zero is 1 exactly when every bit is 0."""
    c = Circuit()
    bus = c.bus_input("a", WORD)
    out = is_zero(c, bus)
    sim = Simulator(c)
    sim.set_bus(bus, a)
    sim.settle()
    assert sim.get(out) == int(a == 0)


@pytest.mark.parametrize("count", [0, 1, SEVEN])
def test_or_many_is_one_if_any_wire_is_one(count: int) -> None:
    """or_many over 0, 1 and 7 wires is 1 exactly when some wire is 1."""
    c = Circuit()
    wires = [c.input(f"w{i}") for i in range(count)]
    out = or_many(c, wires)
    sim = Simulator(c)
    sim.settle()
    assert sim.get(out) == 0
    for wire in wires:
        sim.set(wire, 1)
        sim.settle()
        assert sim.get(out) == 1
        sim.set(wire, 0)
        sim.settle()


def test_or_many_of_nothing_is_the_low_wire() -> None:
    """With no wires there is nothing to be 1, so the answer is `c.low`."""
    c = Circuit()
    assert or_many(c, []) == c.low


@pytest.mark.parametrize("value", range(2**SELECT_WIDTH))
def test_decoder_raises_exactly_the_selected_line(value: int) -> None:
    """For a 3-bit select, exactly the line numbered by the select is high."""
    c = Circuit()
    select = c.bus_input("s", SELECT_WIDTH)
    lines = decoder(c, select)
    assert len(lines) == 2**SELECT_WIDTH
    sim = Simulator(c)
    sim.set_bus(select, value)
    sim.settle()
    assert [sim.get(line) for line in lines] == [int(i == value) for i in range(len(lines))]


def test_bus_width_mismatch_is_rejected() -> None:
    """Joining a 16-bit bus to an 8-bit bus is an error, not a silent truncation."""
    c = Circuit()
    with pytest.raises(ValueError, match="width"):
        and_bus(c, c.bus_input("a", 16), c.bus_input("b", 8))


def test_mux_bus_width_mismatch_is_rejected() -> None:
    """A mux cannot choose between buses of different widths."""
    c = Circuit()
    with pytest.raises(ValueError, match="width"):
        mux_bus(c, c.input("s"), c.bus_input("a", 16), c.bus_input("b", 8))


def test_gates_are_built_only_from_nand() -> None:
    """XOR costs exactly four NAND gates, the classic recipe."""
    c = Circuit()
    xor(c, c.input("a"), c.input("b"))
    assert c.gate_count == XOR_GATES
