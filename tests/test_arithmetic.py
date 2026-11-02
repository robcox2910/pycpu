"""Tests for the adders and the ALU, checked against plain Python arithmetic.

The model functions below use ordinary integers and never touch a circuit, so
the circuit and the model cannot share a mistake.
"""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycpu.arithmetic import AluOp, AluOutput, alu, full_adder, half_adder, ripple_adder
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

WORD = 16
WORD_MAX = (1 << WORD) - 1
SIGN = 1 << (WORD - 1)
HALF_ADDER_GATES = 6
FULL_ADDER_GATES = 15
words = st.integers(min_value=0, max_value=WORD_MAX)
ops = st.sampled_from(list(AluOp))


def _signed(value: int) -> int:
    """Read a 16-bit pattern as a signed number."""
    return value - (1 << WORD) if value & SIGN else value


def _fits(value: int) -> bool:
    """Say whether a signed number fits in 16 bits."""
    return -SIGN <= value < SIGN


def model(op: AluOp, a: int, b: int) -> tuple[int, int, int, int, int]:
    """Work out (result, zero, negative, carry, overflow) with plain integers."""
    carry = overflow = 0
    match op:
        case AluOp.ADD:
            total = a + b
            result, carry = total & WORD_MAX, total >> WORD
            overflow = int(not _fits(_signed(a) + _signed(b)))
        case AluOp.SUB:
            total = a + (WORD_MAX - b) + 1
            result, carry = total & WORD_MAX, total >> WORD
            overflow = int(not _fits(_signed(a) - _signed(b)))
        case AluOp.AND:
            result = a & b
        case AluOp.OR:
            result = a | b
        case AluOp.XOR:
            result = a ^ b
        case AluOp.SHL:
            result, carry = (a << 1) & WORD_MAX, a >> (WORD - 1)
        case AluOp.SHR:
            result, carry = a >> 1, a & 1
        case AluOp.PASS_B:
            result = b
    return result, int(result == 0), int(result >= SIGN), carry, overflow


class Rig:
    """A 16-bit ALU wired to inputs and a simulator, for the tests to poke."""

    def __init__(self) -> None:
        """Build the circuit once and bring it to life."""
        self.c = Circuit()
        self.a = self.c.bus_input("a", WORD)
        self.b = self.c.bus_input("b", WORD)
        self.op = self.c.bus_input("op", 3)
        self.out: AluOutput = alu(self.c, self.a, self.b, self.op)
        self.sim = Simulator(self.c)

    def run(self, op: AluOp, a: int, b: int) -> tuple[int, int, int, int, int]:
        """Return (result, zero, negative, carry, overflow) for one operation."""
        self.sim.set_bus(self.a, a)
        self.sim.set_bus(self.b, b)
        self.sim.set_bus(self.op, op)
        self.sim.settle()
        get = self.sim.get
        return (
            self.sim.get_bus(self.out.result),
            get(self.out.zero),
            get(self.out.negative),
            get(self.out.carry),
            get(self.out.overflow),
        )


@pytest.fixture(scope="module")
def rig() -> Rig:
    """Share one ALU between tests, because building it is the slow part."""
    return Rig()


@pytest.mark.parametrize(("x", "y"), [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_half_adder_adds_two_bits(x: int, y: int) -> None:
    """A half adder gives the sum digit and the carry of two bits."""
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    total, carry = half_adder(c, a, b)
    sim = Simulator(c)
    sim.set(a, x)
    sim.set(b, y)
    sim.settle()
    assert (sim.get(carry), sim.get(total)) == divmod(x + y, 2)
    assert c.gate_count == HALF_ADDER_GATES


@pytest.mark.parametrize("carry_in", [0, 1])
@pytest.mark.parametrize(("x", "y"), [(0, 0), (0, 1), (1, 0), (1, 1)])
def test_full_adder_adds_three_bits(x: int, y: int, carry_in: int) -> None:
    """A full adder adds two bits and a carry that came in."""
    c = Circuit()
    a, b, cin = c.input("a"), c.input("b"), c.input("cin")
    total, carry = full_adder(c, a, b, cin)
    sim = Simulator(c)
    sim.set(a, x)
    sim.set(b, y)
    sim.set(cin, carry_in)
    sim.settle()
    assert (sim.get(carry), sim.get(total)) == divmod(x + y + carry_in, 2)
    assert c.gate_count == FULL_ADDER_GATES


@given(a=words, b=words, carry_in=st.sampled_from([0, 1]))
def test_ripple_adder_adds_any_two_words(a: int, b: int, carry_in: int) -> None:
    """The ripple adder gives the 16-bit sum and carries out the 17th bit."""
    c = Circuit()
    bus_a, bus_b, cin = c.bus_input("a", WORD), c.bus_input("b", WORD), c.input("cin")
    total, carry = ripple_adder(c, bus_a, bus_b, cin)
    sim = Simulator(c)
    sim.set_bus(bus_a, a)
    sim.set_bus(bus_b, b)
    sim.set(cin, carry_in)
    sim.settle()
    expected = a + b + carry_in
    assert sim.get_bus(total) == expected & WORD_MAX
    assert sim.get(carry) == expected >> WORD


def test_ripple_adder_names_each_column() -> None:
    """Sixteen columns, each filed in its own scope, bit0 to bit15."""
    c = Circuit()
    ripple_adder(c, c.bus_input("a", WORD), c.bus_input("b", WORD), c.low)
    assert c.children("") == [f"bit{i}" for i in range(WORD)]


def test_ripple_adder_refuses_buses_of_different_widths() -> None:
    """Adding a 4-bit number to a 3-bit number is a mistake worth shouting about."""
    c = Circuit()
    with pytest.raises(ValueError, match="width"):
        ripple_adder(c, c.bus_input("a", 4), c.bus_input("b", 3), c.low)


def test_a_carry_really_ripples() -> None:
    """Adding 1 to all ones makes every column change its mind, one after another."""
    c = Circuit()
    a, b = c.bus_input("a", WORD), c.bus_input("b", WORD)
    total, carry = ripple_adder(c, a, b, c.low)
    sim = Simulator(c)
    sim.set_bus(a, WORD_MAX)
    sim.settle()
    sim.set_bus(b, 1)
    sim.settle()
    assert sim.get_bus(total) == 0
    assert sim.get(carry) == 1


@given(op=ops, a=words, b=words)
def test_alu_matches_the_plain_python_model(op: AluOp, a: int, b: int) -> None:
    """For any operation and any two words, the result and all four flags agree."""
    assert _shared_rig().run(op, a, b) == model(op, a, b)


_RIG: list[Rig] = []


def _shared_rig() -> Rig:
    """Build the one ALU on first use, so the property test does not rebuild it."""
    if not _RIG:
        _RIG.append(Rig())
    return _RIG[0]


@pytest.mark.parametrize(
    ("op", "a", "b", "result", "carry", "overflow"),
    [
        (AluOp.ADD, 0xFFFF, 1, 0x0000, 1, 0),
        (AluOp.ADD, 0x7FFF, 1, 0x8000, 0, 1),
        (AluOp.SUB, 0x8000, 1, 0x7FFF, 1, 1),
        (AluOp.SUB, 0, 1, 0xFFFF, 0, 0),
        (AluOp.SHL, 0x8000, 0, 0x0000, 1, 0),
        (AluOp.SHR, 0x0001, 0, 0x0000, 1, 0),
    ],
)
def test_alu_edge_cases(
    rig: Rig, op: AluOp, a: int, b: int, result: int, carry: int, overflow: int
) -> None:
    """The edges of the number circle wrap exactly and raise the right flags."""
    got = rig.run(op, a, b)
    assert got[0] == result
    assert got[3] == carry
    assert got[4] == overflow


def test_subtracting_a_number_from_itself_is_zero(rig: Rig) -> None:
    """SUB a a gives 0 with the zero flag up and no borrow."""
    result, zero, negative, carry, overflow = rig.run(AluOp.SUB, 0x1234, 0x1234)
    assert (result, zero, negative, carry, overflow) == (0, 1, 0, 1, 0)


def test_the_zero_flag_is_down_for_a_non_zero_result(rig: Rig) -> None:
    """Zero is 0 when any bit of the result is on."""
    assert rig.run(AluOp.PASS_B, 0, 1)[1] == 0


def test_the_negative_flag_follows_the_top_bit(rig: Rig) -> None:
    """Negative is up exactly when bit 15 of the result is 1."""
    assert rig.run(AluOp.PASS_B, 0, 0x8000)[2] == 1
    assert rig.run(AluOp.PASS_B, 0, 0x7FFF)[2] == 0


def test_the_alu_has_one_adder_with_sixteen_columns(rig: Rig) -> None:
    """The adder lives in alu.adder and its columns are bit0 to bit15."""
    assert rig.c.children("") == ["alu"]
    assert rig.c.children("alu.adder") == [f"bit{i}" for i in range(WORD)]
    assert rig.c.children("alu").count("adder") == 1


def test_the_alu_dial_must_be_three_wires_wide() -> None:
    """A dial of the wrong width is refused, since it could not name every setting."""
    c = Circuit()
    a, b = c.bus_input("a", WORD), c.bus_input("b", WORD)
    with pytest.raises(ValueError, match="3"):
        alu(c, a, b, c.bus_input("op", 2))


def test_the_alu_refuses_inputs_of_different_widths() -> None:
    """A 16-bit number and an 8-bit number cannot go in the two slots."""
    c = Circuit()
    with pytest.raises(ValueError, match="width"):
        alu(c, c.bus_input("a", WORD), c.bus_input("b", 8), c.bus_input("op", 3))


def test_alu_dial_values_are_pinned() -> None:
    """The numbers on the dial are part of the machine's design and never change."""
    assert [int(op) for op in AluOp] == list(range(8))
    assert [op.name for op in AluOp] == [
        "ADD", "SUB", "AND", "OR", "XOR", "SHL", "SHR", "PASS_B",
    ]  # fmt: skip
