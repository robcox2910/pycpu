"""The control unit's parts: a signal box, a row of lockers, and two small helpers.

Think of a railway signal box beside the tracks. The signaller pulls lever 7 and
exactly the signals for route 7 turn green, because the wiring does the thinking.
A CPU has the same thing: an opcode goes in and one wire lights up. Next to the
signal box is a row of eight lockers (the register file), each holding one number,
with two windows to look through and one slot to post a new number into a locker.

Everything here is built from the gates in `logic.py` and the registers in
`memory.py`, so underneath it is all NAND. Each part opens its own scope (`decode`,
`condition`, `registers`, `address_check`) so the Bench can zoom in on it.
"""

from collections.abc import Sequence

from pycpu.circuit import Bus, Circuit, Clock, Wire
from pycpu.logic import and_, decoder, mux_bus, not_, or_, or_many, xor
from pycpu.memory import Register

REGISTER_COUNT = 8
REGISTER_SELECT_BITS = 3
WORD_BITS = 16
CONDITION_PAIR_BIT = 0  # the lowest condition bit says "the opposite answer"


def opcode_lines(c: Circuit, opcode: Bus) -> Bus:
    """Turn the 4-bit opcode into 16 wires, of which exactly one is high.

    Line `n` is high when the opcode bits spell the number `n`. This is a
    `decoder` filed in a part named `decode`.
    """
    with c.scope("decode"):
        return decoder(c, opcode)


def condition_met(
    c: Circuit, cond: Bus, zero: Wire, negative: Wire, carry: Wire, overflow: Wire
) -> Wire:
    """Return a wire that is 1 when the branch condition `cond` holds for the flags.

    The eight conditions come in opposite pairs (EQ/NE, LT/GE, LE/GT, LTU/GEU),
    so only four answers are built: zero, less-than, less-or-equal and
    not-carry. A chooser tree steered by the top two bits of `cond` picks one,
    then an XOR with the lowest bit turns it into its opposite when that bit is 1.
    """
    with c.scope("condition"):
        less = xor(c, negative, overflow)  # signed less-than: the sign, unless it overflowed
        answers: list[Bus] = [
            (zero,),
            (less,),
            (or_(c, zero, less),),
            (not_(c, carry),),
        ]
        level = answers
        for select in cond[CONDITION_PAIR_BIT + 1 :]:
            level = [mux_bus(c, select, level[i], level[i + 1]) for i in range(0, len(level), 2)]
        return xor(c, level[0][0], cond[CONDITION_PAIR_BIT])


def sign_extend(c: Circuit, bits: Bus, width: int = WORD_BITS) -> Bus:
    """Stretch a short signed number to `width` bits by copying its top bit.

    This adds no gates: the top wire is simply run to every new place.

    Raises:
        ValueError: If `width` is narrower than `bits`.

    """
    if width < len(bits):
        msg = f"cannot sign-extend {len(bits)} wires into a narrower {width}"
        raise ValueError(msg)
    del c  # wires only: the circuit is not touched, but callers pass it for symmetry
    return (*bits, *([bits[-1]] * (width - len(bits))))


def outside_ram(c: Circuit, address: Bus, ram_bits: int) -> Wire:
    """Return a wire that is 1 when `address` is too big for a RAM of `ram_bits` bits.

    RAM holds addresses 0 up to `(1 << ram_bits) - 1`, so any 1 in a higher
    address bit means the address points off the end of memory.
    """
    with c.scope("address_check"):
        return or_many(c, address[ram_bits:])


class RegisterFile:
    """Eight 16-bit registers, `r0` to `r7`, with two read windows and one write slot.

    The windows are `a` and `b`: they show the registers picked by `read_a` and
    `read_b`, both at once. To write, put a number on `data`, spell the register
    on `write_select` and raise `write`; on the next clock beat only that
    register loads. Each window is a tree of choosers (the same shape as the
    ALU's answer picker), and register `n` loads when `write` is 1 and a decoder
    on `write_select` lights line `n`.
    """

    def __init__(
        self,
        c: Circuit,
        data: Bus,
        write: Wire,
        write_select: Bus,
        read_a: Bus,
        read_b: Bus,
        clock: Clock,
    ) -> None:
        """Add the register file's gates to the circuit, inside a part named `registers`.

        Args:
            c: The circuit to build in.
            data: The 16 wires to copy into the chosen register; may be placeholders.
            write: 1 when a register should load on the next beat.
            write_select: 3 wires spelling which register loads.
            read_a: 3 wires spelling which register shows in window `a`.
            read_b: 3 wires spelling which register shows in window `b`.
            clock: The clock whose beat steps the registers.

        """
        self.registers: list[Register] = []
        with c.scope("registers"):
            lines = decoder(c, write_select)
            for n in range(REGISTER_COUNT):
                load = and_(c, write, lines[n])
                self.registers.append(Register(c, WORD_BITS, data, load, clock, f"r{n}"))
            outputs = [register.q for register in self.registers]
            with c.scope("read_a"):
                self.a: Bus = _pick(c, outputs, read_a)
            with c.scope("read_b"):
                self.b: Bus = _pick(c, outputs, read_b)


def _pick(c: Circuit, buses: Sequence[Bus], select: Bus) -> Bus:
    """Choose one of `buses` by the number on `select`, with a tree of choosers.

    The lowest select bit picks between neighbours first, then the next bit
    picks between those winners, and so on until one bus is left.
    """
    level = list(buses)
    for bit in select:
        level = [mux_bus(c, bit, level[i], level[i + 1]) for i in range(0, len(level), 2)]
    return level[0]
