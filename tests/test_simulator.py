"""Tests for the netlist and the event-driven simulator."""

import pytest

from pycpu.circuit import Circuit
from pycpu.simulator import OscillationError, Simulator

WORD = 16
BEEF = 0xBEEF
TWO_UNDRIVEN = 2


def test_nand_truth_table() -> None:
    """A NAND gate is off only when both inputs are on."""
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    out = c.nand(a, b)
    sim = Simulator(c)
    for x, y, want in [(0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 0)]:
        sim.set(a, x)
        sim.set(b, y)
        sim.settle()
        assert sim.get(out) == want


def test_unchanged_input_costs_no_evaluations() -> None:
    """Setting an input to the value it already has wakes no gate."""
    c = Circuit()
    a = c.input("a")
    c.nand(a, a)
    sim = Simulator(c)
    sim.settle()
    sim.set(a, 0)
    assert sim.settle() == 0


def test_only_affected_gates_are_evaluated() -> None:
    """Flipping one input evaluates only the gates that listen to it."""
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    c.nand(a, a)
    for _ in range(1000):
        c.nand(b, b)
    sim = Simulator(c)
    sim.settle()
    sim.set(a, 1)
    assert sim.settle() == 1


def test_set_bus_round_trips_least_significant_bit_first() -> None:
    """A number set on a bus reads back the same, with bit 0 first."""
    c = Circuit()
    bus = c.bus_input("x", WORD)
    sim = Simulator(c)
    sim.set_bus(bus, BEEF)
    assert sim.get_bus(bus) == BEEF
    assert sim.get(bus[0]) == 1
    assert sim.get(bus[4]) == 0


def test_never_settling_loop_raises_oscillation_error() -> None:
    """A NOT gate fed its own output raises instead of hanging."""
    c = Circuit()
    x = c.wire_placeholder()
    c.nand_into(x, x, x)
    with pytest.raises(OscillationError):
        Simulator(c, max_events=1000)


def test_constant_wires() -> None:
    """The built-in low wire reads 0 and the high wire reads 1."""
    c = Circuit()
    sim = Simulator(c)
    assert (sim.get(c.low), sim.get(c.high)) == (0, 1)


def test_setting_a_gate_output_is_refused() -> None:
    """Only input wires may be set from outside."""
    c = Circuit()
    a = c.input("a")
    out = c.nand(a, a)
    sim = Simulator(c)
    with pytest.raises(ValueError, match="not an input"):
        sim.set(out, 1)


def test_setting_a_constant_is_refused() -> None:
    """The constant wires cannot be changed."""
    c = Circuit()
    sim = Simulator(c)
    with pytest.raises(ValueError, match="not an input"):
        sim.set(c.high, 0)


def test_a_bit_must_be_zero_or_one() -> None:
    """Setting a wire to 2 is an error, not a silent change."""
    c = Circuit()
    a = c.input("a")
    sim = Simulator(c)
    with pytest.raises(ValueError, match="0 or 1"):
        sim.set(a, 2)


def test_a_bus_value_must_fit() -> None:
    """A number too big for the bus, or negative, is refused."""
    c = Circuit()
    bus = c.bus_input("x", 4)
    sim = Simulator(c)
    with pytest.raises(ValueError, match="does not fit"):
        sim.set_bus(bus, 16)
    with pytest.raises(ValueError, match="does not fit"):
        sim.set_bus(bus, -1)


def test_power_on_is_deterministic() -> None:
    """Two simulators built from one circuit start in exactly the same state."""
    c = Circuit()
    a = c.input("a")
    w = a
    for _ in range(7):
        w = c.nand(w, w)
    first, second = Simulator(c), Simulator(c)
    assert all(first.get(i) == second.get(i) for i in range(c.wire_count))
    assert first.get(w) == 1  # seven NOTs flip a 0 an odd number of times
    assert first.events_total == second.events_total


def test_a_nand_latch_settles_thanks_to_immediate_writes() -> None:
    """Two NANDs facing each other hold a bit instead of oscillating."""
    c = Circuit()
    set_n, reset_n = c.input("set_n"), c.input("reset_n")
    q_n = c.wire_placeholder()
    q = c.nand(set_n, q_n)
    c.nand_into(reset_n, q, q_n)
    sim = Simulator(c)
    sim.set(set_n, 1)
    sim.set(reset_n, 1)
    sim.settle()
    sim.set(set_n, 0)
    sim.settle()
    sim.set(set_n, 1)
    sim.settle()
    assert sim.get(q) == 1
    sim.set(reset_n, 0)
    sim.settle()
    sim.set(reset_n, 1)
    sim.settle()
    assert sim.get(q) == 0
    assert sim.get(q_n) == 1


def test_events_total_counts_every_evaluation() -> None:
    """The running total adds up the evaluations of every settle."""
    c = Circuit()
    a = c.input("a")
    c.nand(a, a)
    sim = Simulator(c)
    before = sim.events_total
    sim.set(a, 1)
    done = sim.settle()
    assert sim.events_total == before + done


def test_counts_and_names() -> None:
    """Gates and wires are counted, and bus wires are distinct and in order."""
    c = Circuit()
    assert (c.gate_count, c.wire_count) == (0, 2)
    bus = c.bus_input("x", 3)
    c.nand(bus[0], bus[1])
    assert (c.gate_count, c.wire_count) == (1, 6)
    assert bus == (2, 3, 4)


def test_unknown_wires_are_refused() -> None:
    """A gate cannot read from a wire that does not exist."""
    c = Circuit()
    with pytest.raises(ValueError, match="no such wire"):
        c.nand(99, c.low)


def test_a_wire_has_only_one_driver() -> None:
    """Two gates cannot drive one wire, and gates cannot drive inputs."""
    c = Circuit()
    a = c.input("a")
    x = c.wire_placeholder()
    c.nand_into(a, a, x)
    with pytest.raises(ValueError, match="already driven"):
        c.nand_into(a, a, x)
    with pytest.raises(ValueError, match="already driven"):
        c.nand_into(a, a, a)


def test_input_names_must_be_unique() -> None:
    """Using the same input name twice is refused."""
    c = Circuit()
    c.input("a")
    with pytest.raises(ValueError, match="already"):
        c.input("a")


def test_cross_coupled_nands_power_on_by_the_order_gates_were_added() -> None:
    """With both inputs high, the loop gate added first wins and ends up at 1."""
    first = Circuit()
    q_n = first.wire_placeholder()
    q = first.nand(first.high, q_n)  # q's gate is added first
    first.nand_into(first.high, q, q_n)
    sim = Simulator(first)
    assert (sim.get(q), sim.get(q_n)) == (1, 0)

    second = Circuit()
    q = second.wire_placeholder()
    q_n = second.nand(second.high, q)  # q_n's gate is added first, so q's is second
    second.nand_into(second.high, q_n, q)
    sim = Simulator(second)
    assert (sim.get(q), sim.get(q_n)) == (0, 1)


def test_a_wire_nothing_drives_stops_the_simulator_with_a_clear_error() -> None:
    """A placeholder that never gets its gate is reported, with a count."""
    c = Circuit()
    c.wire_placeholder()
    c.wire_placeholder()
    done = c.wire_placeholder()
    c.nand_into(c.high, c.high, done)
    assert c.undriven_count == TWO_UNDRIVEN
    with pytest.raises(ValueError, match=r"2 wires have no gate driving them"):
        Simulator(c)


def test_one_undriven_wire_is_reported_in_the_singular() -> None:
    """The message reads naturally for a single wire."""
    c = Circuit()
    c.wire_placeholder()
    with pytest.raises(ValueError, match=r"1 wire has no gate driving it"):
        Simulator(c)
