"""Tests for named scopes and the live circuit view."""

import time
from typing import cast

import pytest

from pycpu.circuit import Circuit
from pycpu.logic import and_, decoder, is_zero, not_, xor
from pycpu.simulator import OscillationError, Simulator
from pycpu.view import circuit_view

XOR_GATES = 4
MANY_CHILDREN = 3000
DECODER_BITS = 12
VIEW_SECONDS = 1.0
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


def test_not_gate_opens_no_scope_of_its_own() -> None:
    """A NOT is a single NAND, so its gate sits in the calling part."""
    c = Circuit()
    a = c.input("a")
    with c.scope("part"):
        not_(c, a)
    assert c.children("part") == []
    assert len(c.gates_in("part")) == 1


def test_gate_count_in_is_right_at_every_depth() -> None:
    """A part counts its own gates plus those of every part nested inside."""
    c = Circuit()
    a = c.input("a")
    with c.scope("top"):
        c.nand(a, a)
        with c.scope("mid"):
            c.nand(a, a)
            c.nand(a, a)
            with c.scope("low"):
                c.nand(a, a)
    assert c.gate_count_in("top.mid.low") == 1
    assert c.gate_count_in("top.mid") == 3  # noqa: PLR2004
    assert c.gate_count_in("top") == 4  # noqa: PLR2004
    assert c.gate_count_in("") == 4  # noqa: PLR2004
    assert len(c.gates_in("top.mid")) == 2  # noqa: PLR2004


def test_a_parent_with_thousands_of_children_counts_correctly() -> None:
    """Three thousand sibling parts are all listed and all counted."""
    c = Circuit()
    a = c.input("a")
    with c.scope("parent"):
        for _ in range(MANY_CHILDREN):
            with c.scope("kid"):
                c.nand(a, a)
                c.nand(a, a)
    names = c.children("parent")
    assert len(names) == MANY_CHILDREN
    assert names[:2] == ["kid", "kid#1"]
    assert names[-1] == f"kid#{MANY_CHILDREN - 1}"
    assert c.gate_count_in("parent") == 2 * MANY_CHILDREN
    assert c.gate_count_in(f"parent.kid#{MANY_CHILDREN - 1}") == 2  # noqa: PLR2004


def test_viewing_a_real_decoder_with_thousands_of_children_is_fast() -> None:
    """Zooming into a 12-bit decoder (over 4,000 parts) takes well under a second."""
    c = Circuit()
    decoder(c, c.bus_input("sel", DECODER_BITS))
    sim = Simulator(c)
    started = time.perf_counter()
    view = circuit_view(sim, "decoder")
    elapsed = time.perf_counter() - started
    assert len(_children(view)) > 2**DECODER_BITS
    assert (
        sum(cast("int", child["gate_count"]) for child in _children(view)) + len(_gates(view))
        == c.gate_count
    )
    assert elapsed < VIEW_SECONDS
