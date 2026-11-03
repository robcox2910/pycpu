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

from pebble import compile_source

from pycpu.assembler import Program, ProgramTooLongError, assemble
from pycpu.fast import FastMachine
from pycpu.isa import Fault
from pycpu.memory import RAM_WORDS
from pycpu.translator.codegen import END_LABEL, frame_words, generate
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

    """

    source: str
    assembly: str
    program: Program
    pebble_lines: tuple[int | None, ...]

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

    """

    output: str
    halted: bool
    fault: Fault | None
    line: int | None
    steps: int

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
            return f"The stack ran out of room{where} (the call on that line found no room for another frame; does a function keep calling itself?)"
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
    # The prologue would stop the machine with STACK_OVERFLOW before printing anything,
    # so a program with no room left for main's frame is refused here instead.
    if program.labels[END_LABEL] + frame_words(checked.main) > RAM_WORDS:
        raise UnsupportedFeature(TOO_BIG)
    lines = tuple(assembly.lines[line - 1] for line in program.lines)
    return TranslatedProgram(source, assembly.text, program, lines)


def _fault_line(
    translated: TranslatedProgram,
    pc: int,
    sp: int,
    memory: tuple[int, ...],
    words: int,
    fault: Fault,
) -> int | None:
    """Find the Pebble line to blame for a fault.

    A stack overflow is blamed on the call that needed one more frame than there was
    room for. The room check comes before the prologue's `push r7`, so nothing has been
    pushed yet and the top of the stack still holds the return address `call` left; the
    call instruction is the word just before it. Main has no caller (the stack is still
    empty), so its own first line is used. Any other fault is blamed on the faulting
    word: `pc - 1` for an execute fault, `pc` for a fetch fault.
    """
    if fault is Fault.STACK_OVERFLOW and sp < words:
        return translated.line_at(memory[sp] - 1)
    # A fetch fault leaves pc on the bad address; any other fault has moved past it.
    return translated.line_at(pc if pc >= words else pc - 1)


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
    state = machine.state()
    fault = Fault(state.halt_code) if state.halted and state.halt_code else None
    line = None
    if fault is not None:
        line = _fault_line(translated, state.pc, state.sp, state.memory, machine.words, fault)
    output = "".join(chr(code) for code in state.output)
    return PebbleRun(output, state.halted, fault, line, steps)
