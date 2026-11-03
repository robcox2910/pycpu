"""The instruction set: the codebook that says what every 16-bit order means.

Think of a spy's codebook. Each order is a row of boxes on a card: the first box
says what to do and the other boxes give the details. Whoever writes a card and
whoever reads it must use the very same book, or the spy opens the wrong door.
This file is that book for PyCPU. The assembler writes cards with it, the fast
engine and the gate-built CPU read them with it, and nothing else in the project
decides what a number means.

An instruction is one 16-bit word with the opcode in the top four bits. The other
fields sit at fixed places: `rd` (or the condition) in bits 11-9, `ra` in 8-6, `rb`
in 5-3, `fn` in 2-0, and the immediate (a number written inside the instruction)
in the low bits. Unused bits are written as 0 and ignored when read, so every word
from 0 to 65535 is a valid instruction.
"""

from dataclasses import dataclass
from enum import IntEnum

from pycpu.state import REGISTER_COUNT, WORD_MASK, Flags

OUTPUT_PORT = 0xFFFF

OPCODE_SHIFT = 12
RD_SHIFT = 9
RA_SHIFT = 6
RB_SHIFT = 3
REGISTER_MASK = 0b111
FN_MASK = 0b111
FN_COUNT = 8

IMM8_BITS = 8
OFF6_BITS = 6
OFF9_BITS = 9
ADDR12_BITS = 12


class Opcode(IntEnum):
    """What an instruction does: the top four bits of the word."""

    ALU = 0
    CMP = 1
    LI = 2
    LHI = 3
    LOAD = 4
    STORE = 5
    JMP = 6
    CALL = 7
    BR = 8
    RET = 9
    PUSH = 10
    POP = 11
    GETSP = 12
    SETSP = 13
    ADDI = 14
    HALT = 15


class Condition(IntEnum):
    """The question a branch asks about the flag lamps (3 bits)."""

    EQ = 0
    NE = 1
    LT = 2
    GE = 3
    LE = 4
    GT = 5
    LTU = 6
    GEU = 7


class Fault(IntEnum):
    """Why a machine stopped when it did not finish normally (the `halt_code`)."""

    BAD_ADDRESS = 1
    STACK_OVERFLOW = 2
    DIVIDE_BY_ZERO = 3


@dataclass(frozen=True)
class Instruction:
    """One instruction taken apart into its fields.

    `rd` holds bits 11-9: the destination register for most opcodes, the
    condition for `BR`, and the register to read for `STORE`, `PUSH` and `SETSP`.
    `imm` holds the signed value of whichever immediate the opcode uses; fields
    that the opcode does not use are 0.

    Attributes:
        opcode: What to do.
        rd: The destination register, or the condition for `BR`.
        ra: The first source register.
        rb: The second source register.
        fn: The ALU operation (an `AluOp` number) for `ALU`.
        imm: The immediate: 0-255 for `LI`/`LHI`/`HALT`, -128 to 127 for `ADDI`,
            a signed 6-bit offset for `LOAD`/`STORE`, a signed 9-bit offset for
            `BR`, and a 12-bit address for `JMP`/`CALL`.

    """

    opcode: Opcode
    rd: int = 0
    ra: int = 0
    rb: int = 0
    fn: int = 0
    imm: int = 0


# Which register-like fields each opcode reads or writes. Fields not listed are ignored.
_USES: dict[Opcode, tuple[str, ...]] = {
    Opcode.ALU: ("rd", "ra", "rb", "fn"),
    Opcode.CMP: ("ra", "rb"),
    Opcode.LI: ("rd",),
    Opcode.LHI: ("rd",),
    Opcode.LOAD: ("rd", "ra"),
    Opcode.STORE: ("rd", "ra"),
    Opcode.JMP: (),
    Opcode.CALL: (),
    Opcode.BR: ("rd",),
    Opcode.RET: (),
    Opcode.PUSH: ("rd",),
    Opcode.POP: ("rd",),
    Opcode.GETSP: ("rd",),
    Opcode.SETSP: ("rd",),
    Opcode.ADDI: ("rd",),
    Opcode.HALT: (),
}

# The immediate each opcode carries: (width in bits, signed?). No entry means no immediate.
_IMMEDIATE: dict[Opcode, tuple[int, bool]] = {
    Opcode.LI: (IMM8_BITS, False),
    Opcode.LHI: (IMM8_BITS, False),
    Opcode.HALT: (IMM8_BITS, False),
    Opcode.ADDI: (IMM8_BITS, True),
    Opcode.LOAD: (OFF6_BITS, True),
    Opcode.STORE: (OFF6_BITS, True),
    Opcode.BR: (OFF9_BITS, True),
    Opcode.JMP: (ADDR12_BITS, False),
    Opcode.CALL: (ADDR12_BITS, False),
}


def _check(name: str, value: int, low: int, high: int) -> None:
    """Raise a ValueError naming the field when `value` is outside `low`..`high`."""
    if not low <= value <= high:
        msg = f"{name} {value} does not fit: it must be from {low} to {high}"
        raise ValueError(msg)


def encode(
    opcode: Opcode,
    *,
    rd: int = 0,
    ra: int = 0,
    rb: int = 0,
    fn: int = 0,
    imm: int = 0,
) -> int:
    """Write an instruction as one 16-bit word.

    Every register and `fn` value is checked, and so is the immediate when the
    opcode has one. Fields that the opcode does not use are left out of the word.

    Args:
        opcode: What to do.
        rd: Destination register (or the condition for `BR`), 0 to 7.
        ra: First source register, 0 to 7.
        rb: Second source register, 0 to 7.
        fn: ALU operation number, 0 to 7.
        imm: The immediate, signed or not as the opcode needs.

    Raises:
        ValueError: If a value does not fit its field; the message names the field.

    """
    _check("rd", rd, 0, REGISTER_COUNT - 1)
    _check("ra", ra, 0, REGISTER_COUNT - 1)
    _check("rb", rb, 0, REGISTER_COUNT - 1)
    _check("fn", fn, 0, FN_COUNT - 1)
    word = int(opcode) << OPCODE_SHIFT
    uses = _USES[opcode]
    if "rd" in uses:
        word |= rd << RD_SHIFT
    if "ra" in uses:
        word |= ra << RA_SHIFT
    if "rb" in uses:
        word |= rb << RB_SHIFT
    if "fn" in uses:
        word |= fn
    if opcode in _IMMEDIATE:
        bits, signed = _IMMEDIATE[opcode]
        if signed:
            _check("imm", imm, -(1 << (bits - 1)), (1 << (bits - 1)) - 1)
        else:
            _check("imm", imm, 0, (1 << bits) - 1)
        word |= imm & ((1 << bits) - 1)
    return word


def decode(word: int) -> Instruction:
    """Take a 16-bit word apart into an `Instruction`. Every word is accepted.

    Fields the opcode does not use come back as 0, whatever bits the word holds.
    """
    word &= WORD_MASK
    opcode = Opcode(word >> OPCODE_SHIFT)
    uses = _USES[opcode]
    imm = 0
    if opcode in _IMMEDIATE:
        bits, signed = _IMMEDIATE[opcode]
        imm = word & ((1 << bits) - 1)
        if signed and imm >> (bits - 1):
            imm -= 1 << bits
    return Instruction(
        opcode=opcode,
        rd=(word >> RD_SHIFT) & REGISTER_MASK if "rd" in uses else 0,
        ra=(word >> RA_SHIFT) & REGISTER_MASK if "ra" in uses else 0,
        rb=(word >> RB_SHIFT) & REGISTER_MASK if "rb" in uses else 0,
        fn=word & FN_MASK if "fn" in uses else 0,
        imm=imm,
    )


def condition_holds(cond: Condition, flags: Flags) -> bool:
    """Answer a branch's question: does `cond` hold for these flag lamps.

    Signed comparisons (`LT`, `GE`, `LE`, `GT`) compare `negative` with `overflow`;
    the unsigned ones (`LTU`, `GEU`) use `carry`, which after a subtraction is 1
    when nothing had to be borrowed.
    """
    zero, carry = bool(flags.zero), bool(flags.carry)
    signed_less = flags.negative != flags.overflow
    answers = {
        Condition.EQ: zero,
        Condition.NE: not zero,
        Condition.LT: signed_less,
        Condition.GE: not signed_less,
        Condition.LE: zero or signed_less,
        Condition.GT: not zero and not signed_less,
        Condition.LTU: not carry,
        Condition.GEU: carry,
    }
    return answers[cond]
