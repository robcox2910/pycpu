"""Every everyday logic gate, built from NAND and nothing else.

Think of a box of identical building blocks. With enough of the one kind of
block you can make doors, windows, stairs and roofs, if you are clever about
how they fit together. NAND is the one block here, and this file is the
instructions for the doors and windows: NOT, AND, OR, XOR, a chooser (mux) and
a decoder.

Each function takes a `Circuit`, adds NAND gates to it, and returns the wire
(or bus) where the answer will appear. None of them works out a value; the
`Simulator` does that. The only logic primitive used anywhere in this file is
`Circuit.nand`.
"""

from collections.abc import Callable, Sequence
from functools import wraps
from typing import Concatenate

from pycpu.circuit import Bus, Circuit, Wire


def _in_own_scope[**P, R](
    build: Callable[Concatenate[Circuit, P], R],
) -> Callable[Concatenate[Circuit, P], R]:
    """Make `build` file its gates in a scope named after itself.

    The scope is a child of whatever part is being built when `build` is
    called, so `xor` called inside `with c.scope("alu")` lands in `alu.xor`.
    Underscores at the end of a name are dropped (`and_` becomes `and`). A
    single NAND (`not_`) is too small to be worth a part and is not wrapped.
    """
    name = build.__name__.strip("_")

    @wraps(build)
    def wrapper(c: Circuit, *args: P.args, **kwargs: P.kwargs) -> R:
        """Open the scope, then build the gates inside it."""
        with c.scope(name):
            return build(c, *args, **kwargs)

    return wrapper


def not_(c: Circuit, a: Wire) -> Wire:
    """Add a NOT gate: the output is 1 when `a` is 0, and 0 when `a` is 1.

    A NAND with both inputs joined to the same wire. One NAND gate.
    """
    return c.nand(a, a)


@_in_own_scope
def and_(c: Circuit, a: Wire, b: Wire) -> Wire:
    """Add an AND gate: the output is 1 only when both `a` and `b` are 1.

    A NAND followed by a NOT. Two NAND gates.
    """
    return not_(c, c.nand(a, b))


@_in_own_scope
def or_(c: Circuit, a: Wire, b: Wire) -> Wire:
    """Add an OR gate: the output is 1 when `a`, `b` or both are 1.

    Flip both inputs, then NAND them. Three NAND gates.
    """
    return c.nand(not_(c, a), not_(c, b))


@_in_own_scope
def xor(c: Circuit, a: Wire, b: Wire) -> Wire:
    """Add an XOR gate: the output is 1 when `a` and `b` differ.

    The classic recipe: `n = NAND(a, b)`, then NAND `a` with `n`, NAND `b` with
    `n`, and NAND those two answers. Four NAND gates.
    """
    n = c.nand(a, b)
    return c.nand(c.nand(a, n), c.nand(b, n))


@_in_own_scope
def _choose(c: Circuit, not_select: Wire, select: Wire, when_0: Wire, when_1: Wire) -> Wire:
    """Pick between two wires when the lever and its opposite are already made.

    Sharing one NOT of the lever across a whole bus saves a gate per bit.
    """
    return c.nand(c.nand(when_0, not_select), c.nand(when_1, select))


@_in_own_scope
def mux(c: Circuit, select: Wire, when_0: Wire, when_1: Wire) -> Wire:
    """Add a chooser: pass `when_0` if `select` is 0, or `when_1` if it is 1.

    Four NAND gates (one of them the NOT of `select`).
    """
    return _choose(c, not_(c, select), select, when_0, when_1)


def _check_widths(a: Bus, b: Bus) -> None:
    """Raise unless the two buses have the same number of wires."""
    if len(a) != len(b):
        msg = f"bus width mismatch: {len(a)} wires against {len(b)}"
        raise ValueError(msg)


@_in_own_scope
def not_bus(c: Circuit, a: Bus) -> Bus:
    """Add a NOT gate to every wire of `a` and return the flipped bus."""
    return tuple(not_(c, bit) for bit in a)


@_in_own_scope
def and_bus(c: Circuit, a: Bus, b: Bus) -> Bus:
    """Add an AND gate for each pair of matching wires in `a` and `b`.

    Raises:
        ValueError: If the buses differ in width.

    """
    _check_widths(a, b)
    return tuple(and_(c, x, y) for x, y in zip(a, b, strict=True))


@_in_own_scope
def or_bus(c: Circuit, a: Bus, b: Bus) -> Bus:
    """Add an OR gate for each pair of matching wires in `a` and `b`.

    Raises:
        ValueError: If the buses differ in width.

    """
    _check_widths(a, b)
    return tuple(or_(c, x, y) for x, y in zip(a, b, strict=True))


@_in_own_scope
def xor_bus(c: Circuit, a: Bus, b: Bus) -> Bus:
    """Add an XOR gate for each pair of matching wires in `a` and `b`.

    Raises:
        ValueError: If the buses differ in width.

    """
    _check_widths(a, b)
    return tuple(xor(c, x, y) for x, y in zip(a, b, strict=True))


@_in_own_scope
def mux_bus(c: Circuit, select: Wire, when_0: Bus, when_1: Bus) -> Bus:
    """Pass the whole bus `when_0` if `select` is 0, or `when_1` if it is 1.

    The NOT of `select` is made once and shared by every bit.

    Raises:
        ValueError: If the buses differ in width.

    """
    _check_widths(when_0, when_1)
    not_select = not_(c, select)
    return tuple(_choose(c, not_select, select, x, y) for x, y in zip(when_0, when_1, strict=True))


@_in_own_scope
def or_many(c: Circuit, wires: Sequence[Wire]) -> Wire:
    """Return a wire that is 1 when any of `wires` is 1.

    The ORs are arranged as a balanced tree, so a change on one input passes
    through only about log2(n) gates. With no wires the answer is `c.low`.
    """
    level = list(wires)
    if not level:
        return c.low
    while len(level) > 1:
        paired = [or_(c, level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            paired.append(level[-1])
        level = paired
    return level[0]


@_in_own_scope
def _and_many(c: Circuit, wires: Sequence[Wire]) -> Wire:
    """Return a wire that is 1 when all of `wires` are 1 (they must not be empty)."""
    level = list(wires)
    while len(level) > 1:
        paired = [and_(c, level[i], level[i + 1]) for i in range(0, len(level) - 1, 2)]
        if len(level) % 2:
            paired.append(level[-1])
        level = paired
    return level[0]


@_in_own_scope
def is_zero(c: Circuit, a: Bus) -> Wire:
    """Return a wire that is 1 when every bit of `a` is 0."""
    return not_(c, or_many(c, a))


@_in_own_scope
def decoder(c: Circuit, select: Bus) -> Bus:
    """Turn a number into one lit line out of many.

    Output line `i` is 1 exactly when `select` holds the number `i`, so the
    result has `2 ** len(select)` wires and exactly one of them is high.
    """
    flipped = not_bus(c, select)
    lines: list[Wire] = []
    for value in range(2 ** len(select)):
        bits = [select[i] if (value >> i) & 1 else flipped[i] for i in range(len(select))]
        lines.append(_and_many(c, bits) if bits else c.high)
    return tuple(lines)
