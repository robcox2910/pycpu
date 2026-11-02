"""The machine state: everything a computer remembers, written on one sheet of paper.

Imagine freezing a kitchen mid-recipe and writing down exactly what is where: which
card the cook's finger is on, what is in every bowl, what is on every shelf of the
pantry. Anyone with that sheet could rebuild the kitchen and carry on cooking.
`MachineState` is that sheet for a PyCPU computer. Both engines, the fast one and the
gate one, can write their state onto it and read one back, which is how they are
compared, and how a paused computer is carried from one engine to the other.

This file only holds values. It works nothing out.
"""

from dataclasses import dataclass
from typing import NamedTuple

from pycpu.memory import RAM_WORDS

REGISTER_COUNT = 8
BYTE_MASK = 0xFF


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
        halt_code: Why it stopped: 0 for normal, otherwise a `Fault` or a program's own code.
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
