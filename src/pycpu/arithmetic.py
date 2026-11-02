"""Adders and the ALU, built from the logic gates and nothing else.

Think of adding on paper: you work one column at a time from the right, write
down a digit and carry a one to the next column. A ripple adder is that same
row of columns made of gates, each column handing its carry to its neighbour.
The ALU is a kitchen multi-tool wrapped around one such adder: two numbers go
in, a dial picks the job, and one result comes out with four little lamps
(flags) that describe it.

Like `logic.py`, every function here takes a `Circuit`, adds gates and returns
wires. None of them works out a value; the `Simulator` does that.
"""

from dataclasses import dataclass
from enum import IntEnum

from pycpu.circuit import Bus, Circuit, Wire
from pycpu.logic import (
    and_,
    and_bus,
    in_own_scope,
    is_zero,
    mux_bus,
    not_,
    or_,
    or_bus,
    xor,
    xor_bus,
)

OP_WIDTH = 3


@in_own_scope
def half_adder(c: Circuit, a: Wire, b: Wire) -> tuple[Wire, Wire]:
    """Add two bits and return `(sum, carry)`.

    The sum digit is 1 when the bits differ (an XOR) and the carry is 1 when
    both are 1 (an AND). Six NAND gates.
    """
    return xor(c, a, b), and_(c, a, b)


@in_own_scope
def full_adder(c: Circuit, a: Wire, b: Wire, carry_in: Wire) -> tuple[Wire, Wire]:
    """Add two bits and a carry that came in, and return `(sum, carry)`.

    Two half adders in a row, then an OR to join their carries (they can never
    both be 1). Fifteen NAND gates.
    """
    first_sum, first_carry = half_adder(c, a, b)
    total, second_carry = half_adder(c, first_sum, carry_in)
    return total, or_(c, first_carry, second_carry)


def ripple_adder(c: Circuit, a: Bus, b: Bus, carry_in: Wire) -> tuple[Bus, Wire]:
    """Add two numbers one column at a time and return `(sum, carry_out)`.

    Column `i` is a full adder filed in a scope named `bit{i}` in whatever part
    is being built, so a caller can zoom into any column. The carry out of each
    column feeds the next, which is the ripple. Sixteen columns cost 240 gates.

    Raises:
        ValueError: If the buses differ in width.

    """
    if len(a) != len(b):
        msg = f"bus width mismatch: {len(a)} wires against {len(b)}"
        raise ValueError(msg)
    carry = carry_in
    total: list[Wire] = []
    for i, (x, y) in enumerate(zip(a, b, strict=True)):
        with c.scope(f"bit{i}"):
            digit, carry = full_adder(c, x, y, carry)
        total.append(digit)
    return tuple(total), carry


class AluOp(IntEnum):
    """The settings on the ALU's dial, as the number the `op` wires spell."""

    ADD = 0
    SUB = 1
    AND = 2
    OR = 3
    XOR = 4
    SHL = 5
    SHR = 6
    PASS_B = 7


@dataclass(frozen=True)
class AluOutput:
    """What comes out of the ALU: the answer and four lamps describing it.

    Attributes:
        result: The answer, 16 wires.
        zero: 1 when every bit of the result is 0.
        negative: 1 when the top bit of the result is 1.
        carry: 1 when a bit fell off the end (see `alu`).
        overflow: 1 when a signed ADD or SUB gave an answer that does not fit.

    """

    result: Bus
    zero: Wire
    negative: Wire
    carry: Wire
    overflow: Wire


def alu(c: Circuit, a: Bus, b: Bus, op: Bus) -> AluOutput:
    """Add an ALU that does the job `op` names to `a` and `b`.

    Every answer is worked out all the time and a tree of choosers steered by
    the three `op` wires picks one. Only one adder exists: for `SUB` the bits
    of `b` are flipped and the carry in is 1, because `a - b` is
    `a + NOT b + 1`. The carry flag is the carry out for `ADD` (and for `SUB`,
    where 1 means no borrow), the bit shifted out for `SHL` and `SHR`, and 0
    for the logic operations. The overflow flag is only ever 1 for `ADD` and
    `SUB`. `SHR` is logical: it shifts in a 0.

    Raises:
        ValueError: If `a` and `b` differ in width, or `op` is not 3 wires wide.

    """
    if len(a) != len(b):
        msg = f"bus width mismatch: {len(a)} wires against {len(b)}"
        raise ValueError(msg)
    if len(op) != OP_WIDTH:
        msg = f"the op bus must be {OP_WIDTH} wires wide, not {len(op)}"
        raise ValueError(msg)
    top = len(a) - 1
    with c.scope("alu"):
        with c.scope("control"):
            not_o1, not_o2 = not_(c, op[1]), not_(c, op[2])
            subtract = and_(c, and_(c, op[0], not_o1), not_o2)  # op == SUB
            arithmetic = and_(c, not_o1, not_o2)  # op is ADD or SUB
        with c.scope("operand"):
            b_in = xor_bus(c, b, (subtract,) * len(b))
        with c.scope("adder"):
            total, carry_out = ripple_adder(c, a, b_in, subtract)
        with c.scope("overflow"):
            same_sign = not_(c, xor(c, a[top], b_in[top]))
            changed_sign = xor(c, a[top], total[top])
            overflow = and_(c, arithmetic, and_(c, same_sign, changed_sign))
        low = c.low
        # Each candidate is the 16 result wires, then carry, then overflow.
        candidates = [
            (*total, carry_out, overflow),  # ADD
            (*total, carry_out, overflow),  # SUB
            (*and_bus(c, a, b), low, low),  # AND
            (*or_bus(c, a, b), low, low),  # OR
            (*xor_bus(c, a, b), low, low),  # XOR
            (low, *a[:top], a[top], low),  # SHL: 0 then a0..a14, carry is a15
            (*a[1:], low, a[0], low),  # SHR: a1..a15 then 0, carry is a0
            (*b, low, low),  # PASS_B
        ]
        with c.scope("select"):
            level = candidates
            for select in op:
                level = [
                    mux_bus(c, select, level[i], level[i + 1]) for i in range(0, len(level), 2)
                ]
        chosen = level[0]
        result = chosen[: len(a)]
        with c.scope("flags"):
            zero = is_zero(c, result)
    return AluOutput(
        result=result,
        zero=zero,
        negative=result[top],
        carry=chosen[len(a)],
        overflow=chosen[len(a) + 1],
    )
