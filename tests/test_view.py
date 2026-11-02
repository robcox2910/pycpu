"""Tests for named scopes and the live circuit view."""

from typing import cast

import pytest

from pycpu.circuit import Circuit
from pycpu.logic import and_, is_zero, xor
from pycpu.simulator import OscillationError, Simulator
from pycpu.view import circuit_view

XOR_GATES = 4
ZERO_GATES_16 = 46


def _gates(view: dict[str, object]) -> list[dict[str, int]]:
    """Pull the gate rows out of a view, typed for the checker."""
    return cast("list[dict[str, int]]", view["gates"])


def _children(view: dict[str, object]) -> list[dict[str, object]]:
    """Pull the child rows out of a view, typed for the checker."""
    return cast("list[dict[str, object]]", view["children"])


def test_gates_land_in_their_scope() -> None:
    """XOR built inside a scope puts its four gates in a child named xor."""
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    with c.scope("half"):
        xor(c, a, b)
    assert c.children("") == ["half"]
    assert c.children("half") == ["xor"]
    assert len(c.gates_in("half.xor")) == XOR_GATES
    assert c.gates_in("half") == []
    assert c.has_scope("half.xor")
    assert not c.has_scope("half.nope")


def test_repeated_names_under_one_parent_are_numbered() -> None:
    """Calling xor twice in one place gives xor and xor#1."""
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    xor(c, a, b)
    xor(c, a, b)
    assert c.children("") == ["xor", "xor#1"]


def test_nested_scopes_have_dotted_paths() -> None:
    """A scope inside a scope is reached by a dotted path."""
    c = Circuit()
    a = c.input("a")
    with c.scope("alu"), c.scope("adder"):
        c.nand(a, a)
    assert c.children("alu") == ["adder"]
    assert len(c.gates_in("alu.adder")) == 1
    assert c.scope_of(0) == "alu.adder"


def test_scope_is_left_even_when_the_block_fails() -> None:
    """After an exception inside a scope, new gates go back to the parent."""
    c = Circuit()
    a = c.input("a")
    with pytest.raises(RuntimeError), c.scope("broken"):
        raise RuntimeError
    c.nand(a, a)
    assert len(c.gates_in("")) == 1


def test_bad_scope_names_are_refused() -> None:
    """A scope name cannot be empty or hold a dot, which would break paths."""
    c = Circuit()
    for bad in ("", "a.b"):
        with pytest.raises(ValueError, match="scope name"), c.scope(bad):
            pass


def test_scopes_do_not_change_gate_counts() -> None:
    """Putting gates in scopes adds no gates: is_zero of 16 bits is still 46."""
    c = Circuit()
    is_zero(c, c.bus_input("x", 16))
    assert c.gate_count == ZERO_GATES_16
    assert c.gate_count_in("") == ZERO_GATES_16
    assert c.gate_count_in("is_zero") == ZERO_GATES_16


def test_view_reports_real_live_values() -> None:
    """A gate in the view shows the values the simulator holds right now."""
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    with c.scope("one"):
        out = c.nand(a, b)
    sim = Simulator(c)
    sim.set(a, 1)
    sim.set(b, 1)
    sim.settle()
    gate = _gates(circuit_view(sim, "one"))[0]
    assert (gate["value_a"], gate["value_b"], gate["value_out"]) == (1, 1, 0)
    assert gate["out"] == out
    assert (gate["a"], gate["b"]) == (a, b)


def test_view_follows_the_simulator_as_it_changes() -> None:
    """Flip an input and the very next view shows the new values."""
    c = Circuit()
    a = c.input("a")
    with c.scope("not"):
        c.nand(a, a)
    sim = Simulator(c)
    assert _gates(circuit_view(sim, "not"))[0]["value_out"] == 1
    sim.set(a, 1)
    sim.settle()
    assert _gates(circuit_view(sim, "not"))[0]["value_out"] == 0


def test_view_lists_children_with_nested_gate_counts() -> None:
    """A child's gate count includes everything nested inside it."""
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    with c.scope("top"):
        and_(c, a, b)
        xor(c, a, b)
    view = circuit_view(Simulator(c), "top")
    assert view["path"] == "top"
    assert _children(view) == [{"name": "and", "gate_count": 2}, {"name": "xor", "gate_count": 4}]
    assert _gates(view) == []
    assert _children(circuit_view(Simulator(c), ""))[0] == {"name": "top", "gate_count": 6}


def test_unknown_scope_raises_key_error() -> None:
    """Asking for a part that does not exist is a KeyError."""
    with pytest.raises(KeyError):
        circuit_view(Simulator(Circuit()), "nope")


def test_oscillation_error_names_the_part_still_changing() -> None:
    """A ring built inside a scope is named in the error."""
    c = Circuit()
    with c.scope("alu"), c.scope("adder"):
        loop = c.wire_placeholder()
        c.nand_into(loop, loop, loop)
    with pytest.raises(
        OscillationError, match=r"1000 gate evaluations \(still changing in part 'alu\.adder'\)"
    ):
        Simulator(c, max_events=1000)


def test_oscillation_error_in_the_root_reads_sensibly() -> None:
    """A ring in no scope says it is at the top level."""
    c = Circuit()
    loop = c.wire_placeholder()
    c.nand_into(loop, loop, loop)
    with pytest.raises(OscillationError, match=r"\(still changing at the top level\)"):
        Simulator(c, max_events=1000)
