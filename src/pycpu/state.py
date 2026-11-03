"""The machine state: everything a computer remembers, written on one sheet of paper.

Imagine freezing a kitchen mid-recipe and writing down exactly what is where: which
card the cook's finger is on, what is in every bowl, what is on every shelf of the
pantry. Anyone with that sheet could rebuild the kitchen and carry on cooking.
`MachineState` is that sheet for a PyCPU computer. Both engines, the fast one and the
gate one, can write their state onto it and read one back, which is how they are
compared, and how a paused computer is carried from one engine to the other.

This file only holds values. It works nothing out.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

from pycpu.memory import RAM_WORDS, WORD_BITS

REGISTER_COUNT = 8
WORD_MASK = (1 << WORD_BITS) - 1  # the biggest 16-bit number: 65535
BYTE_MASK = 0xFF
HALT_CODE_MAX = 0xFF  # HALT carries an 8-bit code, so every halt code fits in a byte


class Flags(NamedTuple):
    """The four lamps that describe the last sum: each one is 0 or 1.

    Attributes:
        zero: 1 when the result was 0.
        negative: 1 when the top bit of the result was 1.
        carry: 1 when a bit fell off the end (see `pycpu.arithmetic.alu`).
        overflow: 1 when a signed add or subtract gave an answer that does not fit.

    """

    zero: int
    negative: int
    carry: int
    overflow: int


@dataclass(frozen=True)
class MachineState:
    """One frozen moment of a computer: every value it would need to carry on.

    Attributes:
        pc: The program counter, the address of the next instruction.
        sp: The stack pointer.
        registers: The eight registers `r0` to `r7`.
        flags: The four flag lamps.
        memory: Every word of RAM.
        halted: True once the machine has stopped.
        halt_code: Why it stopped: 0 for normal, otherwise a `Fault` or a program's own
            code; always 0 to `HALT_CODE_MAX` (255), because `HALT` carries 8 bits.
        output: Every word the program has sent to the output port, in order.

    """

    pc: int
    sp: int
    registers: tuple[int, ...]
    flags: Flags
    memory: tuple[int, ...]
    halted: bool
    halt_code: int
    output: tuple[int, ...]

    @property
    def output_text(self) -> str:
        """The output as text: the low byte of each output word, as a character."""
        return "".join(chr(word & BYTE_MASK) for word in self.output)


def power_on(words: int = RAM_WORDS) -> MachineState:
    """Return the state of a computer the moment it is switched on.

    Everything is 0, except the stack pointer, which starts at `words` (one past
    the last word of RAM) so that the first push lands on the top word.

    Args:
        words: How many words of RAM the computer has.

    """
    return MachineState(
        pc=0,
        sp=words,
        registers=(0,) * REGISTER_COUNT,
        flags=Flags(0, 0, 0, 0),
        memory=(0,) * words,
        halted=False,
        halt_code=0,
        output=(),
    )


def program_state(program: Sequence[int], words: int = RAM_WORDS) -> MachineState:
    """Return a freshly powered-on state with `program` copied in from address 0.

    Both engines load programs this way, so they start from the very same sheet.

    Args:
        program: The 16-bit words to put at the start of memory.
        words: How many words of RAM the computer has.

    Raises:
        ValueError: If the program is bigger than memory or holds a non-word.

    """
    if len(program) > words:
        msg = f"a program of {len(program)} words does not fit in {words} words of memory"
        raise ValueError(msg)
    for word in program:
        if not 0 <= word <= WORD_MASK:
            msg = f"program word {word} is not a 16-bit number"
            raise ValueError(msg)
    start = power_on(words)
    return replace(start, memory=(*program, *start.memory[len(program) :]))


def validate_state(state: MachineState, words: int) -> None:
    """Raise a ValueError unless `state` is a state a machine of `words` words could hold."""
    if len(state.memory) != words:
        msg = f"memory has {len(state.memory)} words, but this machine has {words}"
        raise ValueError(msg)
    if len(state.registers) != REGISTER_COUNT:
        msg = f"there must be {REGISTER_COUNT} registers, not {len(state.registers)}"
        raise ValueError(msg)
    numbers = {
        "pc": [state.pc],
        "sp": [state.sp],
        "register": state.registers,
        "memory word": state.memory,
        "output word": state.output,
    }
    for name, values in numbers.items():
        for value in values:
            if not 0 <= value <= WORD_MASK:
                msg = f"{name} {value} is not a 16-bit number"
                raise ValueError(msg)
    if not 0 <= state.halt_code <= HALT_CODE_MAX:
        msg = f"halt code {state.halt_code} must be from 0 to {HALT_CODE_MAX}"
        raise ValueError(msg)
    for name, flag in zip(Flags._fields, state.flags, strict=True):
        if flag not in (0, 1):
            msg = f"flag {name} must be 0 or 1, not {flag}"
            raise ValueError(msg)
