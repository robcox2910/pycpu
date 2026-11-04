"""Translate and run: the front desk where a Pebble program goes in and its output comes out.

Think of a translation agency. You hand a recipe over the counter; behind the counter,
one person checks it for anything the cook cannot make (the subset check), another
writes the cards (the code generator), and a third turns the written cards into the
cook's number code (the assembler). You get back the finished pile, with a note on each
card saying which line of your recipe it came from.

`translate` is that counter. `run_pebble` goes one step further: it hands the pile to
the fast engine, lets the cook work, and tells you what was printed and, if something
went wrong, which Pebble line was running.
"""

from dataclasses import dataclass
from typing import Self

from pebble import compile_source

from pycpu.assembler import Program, ProgramTooLongError, assemble
from pycpu.fast import FastMachine
from pycpu.isa import Fault
from pycpu.memory import RAM_WORDS
from pycpu.state import MachineState
from pycpu.translator.codegen import END_LABEL, FrameLayout, frame_words, generate
from pycpu.translator.subset import TOO_BIG, UnsupportedFeature, check_program


@dataclass(frozen=True)
class TranslatedProgram:
    """A Pebble program turned into PyCPU machine code, with its source map.

    Attributes:
        source: The Pebble program as written.
        assembly: The assembly the translator wrote for it, comments and all.
        program: The assembled machine code, its labels and the assembly line of each word.
        pebble_lines: For every machine word, the Pebble line that made it, or None
            for the runtime routines and the text data.
        main_frame_words: The stack words the top-level code needs for its own frame.
        frames: For every machine word, the layout of the frame `r7` points at just
            before that word runs, or None where no frame is ready: the runtime
            routines, the text data, every prologue word and each return's `ret`.

    """

    source: str
    assembly: str
    program: Program
    pebble_lines: tuple[int | None, ...]
    main_frame_words: int
    frames: tuple[FrameLayout | None, ...]

    @property
    def memory_needed(self) -> int:
        """Count the words of memory the program, its text and main's first frame need."""
        return self.program.labels[END_LABEL] + self.main_frame_words

    def line_at(self, address: int) -> int | None:
        """Return the Pebble line of the word at `address`, or None if it has none."""
        if 0 <= address < len(self.pebble_lines):
            return self.pebble_lines[address]
        return None


@dataclass(frozen=True)
class PebbleRun:
    """What happened when a Pebble program ran on PyCPU.

    Attributes:
        output: Everything it printed.
        halted: True if the machine stopped by itself; False if it ran out of steps.
        fault: Why it stopped, if it stopped because something went wrong.
        line: The Pebble line that was running when the fault happened, else None.
        steps: How many instructions the machine carried out.
        by_call: For a stack overflow, True if a call that found no room is to blame;
            False when main's own first frame did not fit, so no call is involved.

    """

    output: str
    halted: bool
    fault: Fault | None
    line: int | None
    steps: int
    by_call: bool = True

    @classmethod
    def from_state(cls, translated: TranslatedProgram, state: MachineState, steps: int) -> Self:
        """Read how a run of `translated` went from the machine it ran on.

        Either engine's state will do: `run_pebble` passes the fast engine's, and the
        Cockpit passes the gate engine's.

        Args:
            translated: The program that was running.
            state: The machine as it is now.
            steps: How many instructions it has carried out, stored as given. A
                caller that does not count (the Cockpit) passes 0; `describe` only
                mentions the count for a run that has not halted.

        Returns:
            The output, whether it halted, any fault, and the Pebble line to blame.

        """
        fault = Fault(state.halt_code) if state.halted and state.halt_code else None
        line = None
        if fault is not None:
            line = _fault_line(translated, state, fault)
        # Each output word is one character's code, kept whole (not cut to a byte).
        output = "".join(chr(code) for code in state.output)
        # With an empty stack there is no return address, so main's own frame overflowed.
        by_call = not (fault is Fault.STACK_OVERFLOW and state.sp >= len(state.memory))
        return cls(output, state.halted, fault, line, steps, by_call)

    def describe(self) -> str:
        """Say in one friendly sentence how the run ended.

        Returns:
            For example "Division by zero at line 3", or "The program finished". When
            the Pebble line is unknown, the sentence leaves it out.

        """
        if self.fault is None:
            if self.halted:
                return "The program finished"
            return f"The program was still running after {self.steps} steps"
        where = "" if self.line is None else f" at line {self.line}"
        if self.fault is Fault.DIVIDE_BY_ZERO:
            return f"Division by zero{where}"
        if self.fault is Fault.STACK_OVERFLOW:
            if not self.by_call:
                return f"The program needs more stack room than there is{where}"
            return (
                f"The stack ran out of room{where} (the call on that line found no room "
                "for another frame; does a function keep calling itself?)"
            )
        return f"The program used a memory address that does not exist{where}"


def translate(source: str) -> TranslatedProgram:
    """Turn a Pebble program into PyCPU machine code.

    Pebble compiles it to bytecode, the subset check looks at every instruction, the
    code generator writes assembly, and the assembler turns that into words.

    Args:
        source: The Pebble program.

    Returns:
        The assembly, the machine code and the Pebble line of every word.

    Raises:
        pebble.PebbleError: If Pebble itself finds a mistake in the program.
        UnsupportedFeature: If the program uses something PyCPU cannot do yet.

    """
    checked = check_program(compile_source(source).compiled)
    assembly = generate(checked)
    try:
        program = assemble(assembly.text, words=RAM_WORDS)
    except ProgramTooLongError as error:
        raise UnsupportedFeature(TOO_BIG) from error
    lines = tuple(assembly.lines[line - 1] for line in program.lines)
    frames = tuple(assembly.frames[line - 1] for line in program.lines)
    translated = TranslatedProgram(
        source, assembly.text, program, lines, frame_words(checked.main), frames
    )
    # The prologue would stop the machine with STACK_OVERFLOW before printing anything,
    # so a program with no room left for main's frame is refused here instead.
    if translated.memory_needed > RAM_WORDS:
        raise UnsupportedFeature(TOO_BIG)
    return translated


def _fault_line(translated: TranslatedProgram, state: MachineState, fault: Fault) -> int | None:
    """Find the Pebble line to blame for a fault.

    A stack overflow is blamed on the call that needed one more frame than there was
    room for. The room check comes before the prologue's `push r7`, so nothing has been
    pushed yet and the top of the stack still holds the return address `call` left; the
    call instruction is the word just before it. Main has no caller (the stack is still
    empty), so its own first line is used. Any other fault is blamed on the faulting
    word: `pc - 1` for an execute fault, `pc` for a fetch fault.
    """
    words = len(state.memory)
    if fault is Fault.STACK_OVERFLOW and state.sp < words:
        return translated.line_at(state.memory[state.sp] - 1)
    # A fetch fault leaves pc on the bad address; any other fault has moved past it.
    return translated.line_at(state.pc if state.pc >= words else state.pc - 1)


def run_pebble(source: str, max_steps: int = 1_000_000) -> PebbleRun:
    """Translate a Pebble program and run it on the fast engine.

    Args:
        source: The Pebble program.
        max_steps: The most instructions to carry out before giving up.

    Returns:
        The output, whether it halted, any fault, the Pebble line of the fault, and
        the number of steps.

    Raises:
        pebble.PebbleError: If Pebble itself finds a mistake in the program.
        UnsupportedFeature: If the program uses something PyCPU cannot do yet.

    """
    translated = translate(source)
    machine = FastMachine()
    machine.load_program(translated.program.words)
    steps = machine.run(max_steps)
    return PebbleRun.from_state(translated, machine.state(), steps)
