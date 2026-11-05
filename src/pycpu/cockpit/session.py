"""The Cockpit's session: the one running computer and every rule about moving it.

Think of the pilot's seat: the pilot is the only one who moves the controls, and the
seat refuses anything that would break the aeroplane. A `Cockpit` owns the single
real `Computer`, the program on it (with its Pebble source map when there is one),
and the state just before the last move. Every move goes through its methods (play
too, one slice at a time through `play_tick`), which refuse bad requests with a
`CockpitRefusal` that names the reason; the web app only reads requests and answers,
and the picture module only reads.
"""

from dataclasses import dataclass

from pycpu.assembler import AssemblyError, assemble
from pycpu.cockpit.explain import (
    END_NOTE,
    FINISHED_NOTE,
    MAIN_CLOCK,
    NO_GATE_ENDING,
    Depth,
    count_instructions,
    describe_gate_steps,
    describe_move,
    describe_rewind,
    describe_run,
    no_gate_note,
)
from pycpu.computer import Computer, StepSize
from pycpu.cpu import MicroStep
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.state import MachineState
from pycpu.translator import FRAME_POINTER, TranslatedProgram, translate

# Depth and the notes live in explain.py, which writes every sentence; they are listed
# here too so the moves' old imports (`from pycpu.cockpit.session import Depth`) still work.
__all__ = [
    "BUSY_MESSAGE",
    "DEMO_PROGRAM",
    "END_NOTE",
    "FINISHED_NOTE",
    "LIMIT_REASON",
    "MAIN_CLOCK",
    "MAX_GATE_STEPS",
    "MAX_LINE_INSTRUCTIONS",
    "MAX_PEBBLE_CHARACTERS",
    "MAX_RUN",
    "MAX_SPEED",
    "NOT_PEBBLE_MESSAGE",
    "NOT_PLAYING_MESSAGE",
    "NO_GATE_ENDING",
    "NO_LINES_NOTE",
    "TICK_SECONDS",
    "Cockpit",
    "CockpitBusy",
    "CockpitRefusal",
    "Depth",
    "LineStep",
]

MAX_RUN = 10_000  # the most instructions one press of Run may ask for
MAX_GATE_STEPS = 100_000  # the most gate steps one request may ask for
MAX_PEBBLE_CHARACTERS = 65_536  # far more Pebble than fits in 4K words once translated
MAX_LINE_INSTRUCTIONS = 10_000  # the most instructions one line step may run before giving up
MAX_SPEED = 100_000  # the fastest play, in instructions a second
TICK_SECONDS = 0.1  # how long play waits between two slices (and two live events)

DEMO_PROGRAM = """\
    set r1, 0xFFFF    ; the output port's address
    li r2, 3          ; count down from 3
loop:
    call show         ; print the digit for r2
    addi r2, -1
    br ne, loop       ; again, until r2 reaches 0
    halt
show:
    li r3, 48         ; 48 is the character '0'
    add r3, r3, r2    ; '0' + r2 is the digit for r2
    store r3, [r1]    ; send it to the screen
    ret
"""

BUSY_MESSAGE = "the computer is running: press pause first"
NOT_PEBBLE_MESSAGE = "line steps need a Pebble program: this one is assembly"
NOT_PLAYING_MESSAGE = "the computer is not playing: press play first"
LIMIT_REASON = "the line may be stuck in a loop, or a call it makes is very long"
NO_LINES_NOTE = (
    "This program is machine code, so it has no Pebble lines to step. "
    "Look closer to step an instruction."
)


class CockpitRefusal(Exception):  # noqa: N818
    """Say that the Cockpit will not do what was asked, and why, in one sentence."""


class CockpitBusy(CockpitRefusal):
    """Say that the computer is playing, so only pause or a load is allowed."""


@dataclass(frozen=True)
class LineStep:
    """What one Pebble line step did: how far it ran and why it stopped.

    Attributes:
        instructions: How many instructions ran on the fast engine.
        stopped: `"line"` if it reached the next line, `"halted"` if the program
            stopped (or had already stopped), `"limit"` if it gave up after
            `MAX_LINE_INSTRUCTIONS` instructions.

    """

    instructions: int
    stopped: str


def _check_whole(name: str, value: int, largest: int) -> None:
    """Refuse `value` unless it is a whole number from 1 to `largest`."""
    if not 1 <= value <= largest:
        msg = f"{name} must be a whole number from 1 to {largest}"
        raise CockpitRefusal(msg)


class Cockpit:
    """One running computer, paused, with the rules for moving and loading it.

    Attributes:
        computer: The real computer, paused at an instruction boundary unless playing.
        translated: The Pebble program on it, or None for an assembly program.
        assembly: The assembly text shown in the listing.
        program: The assembled program on the machine, for the listing.
        before: The state just before the last move, for marking what changed.
        last_gate: The micro step of the last gate step, else None.
        note: One sentence about the last move, else None.
        happened: The "What just happened" sentence for the last move, written from
            the real change by `explain.py`. None before any move, after a load, while
            playing, and after a step that could not move (`note` says why).
        playing: Whether the computer is running on its own.
        loads: How many programs have been loaded, 0 for the demo it starts with. Every
            load adds one, so the page can tell which program a listing belongs to.

    """

    def __init__(self, address_bits: int = RAM_ADDRESS_BITS) -> None:
        """Build the computer with `DEMO_PROGRAM` loaded and paused at its start."""
        self.program = assemble(DEMO_PROGRAM, words=1 << address_bits)
        self.computer = Computer(self.program, address_bits)
        self.computer.pause()
        self.translated: TranslatedProgram | None = None
        self.assembly = DEMO_PROGRAM
        self.before: MachineState = self.computer.state()
        self.last_gate: MicroStep | None = None
        self.note: str | None = None
        self.happened: str | None = None
        self.playing = False
        self.loads = 0

    def _begin(self) -> None:
        """Start a move: refuse it while playing, then set `before` and clear the notes."""
        if self.playing:
            raise CockpitBusy(BUSY_MESSAGE)
        self._mark()

    def _mark(self) -> None:
        """Remember the state before a move, and clear the last move's sentences and gate step."""
        self.before = self.computer.state()
        self.note = None
        self.happened = None
        self.last_gate = None

    def start_with_pebble(self, source: str) -> None:
        """Load a Pebble program as the Cockpit's starting program.

        This is for a Cockpit that has just been built: the program is loaded as
        `load_pebble` does, and a load marks nothing changed, because a visitor never
        saw the demo program it replaced.

        Raises:
            CockpitRefusal: If the program does not fit this Cockpit's memory.
            PebbleError: If Pebble itself finds a mistake in the program.
            UnsupportedFeature: If the program uses something PyCPU cannot do yet.

        """
        self.load_pebble(source)

    def start_playing(self) -> None:
        """Let the computer run on its own: resume it onto the fast engine and mark it playing.

        `resume` first finishes a part-done instruction in the gates. After this the
        computer only moves through `play_tick`, until `stop_playing` (or a load)
        pauses it again. Starting is a move, so `before` is set and the notes cleared.

        Raises:
            CockpitBusy: If it is already playing.

        """
        self._begin()
        self.computer.resume()
        self.playing = True

    def play_tick(self, instructions: int) -> bool:
        """Run one slice of play: up to `instructions` instructions on the fast engine.

        A tick is a move, so `before` becomes the state at the start of the slice,
        and the changed marks show what this slice changed. A tick of 0 instructions
        is allowed: at slow speeds most ticks run nothing.

        Returns:
            True while the program is still going, False once it has halted.

        Raises:
            CockpitRefusal: If the computer is not playing.

        """
        if not self.playing:
            raise CockpitRefusal(NOT_PLAYING_MESSAGE)
        self._mark()
        self.computer.run(instructions)
        return not self.computer.state().halted

    def stop_playing(self) -> None:
        """Stop play and pause just before the next instruction, in the gate engine.

        Stopping when not playing does nothing, so pause and load can both call it.
        """
        self.playing = False
        if not self.computer.paused:
            self.computer.pause()

    def load_assembly(self, source: str) -> None:
        """Assemble `source`, load it and pause at its start.

        If the computer is playing, play stops first; a refused text leaves it playing.

        Raises:
            CockpitRefusal: Naming the line the assembler refused; the machine is left as it was.

        """
        try:
            assembled = assemble(source, words=self.computer.gate.words)
        except AssemblyError as error:
            raise CockpitRefusal(str(error)) from None
        self.stop_playing()
        self.computer.load_program(assembled)
        self.computer.pause()
        self._mark()  # a load marks nothing changed: `before` is the loaded state
        self.translated = None
        self.assembly = source
        self.program = assembled
        self.loads += 1

    def load_pebble(self, source: str) -> None:
        """Translate a Pebble program, load it and pause at its start.

        If the computer is playing, play stops first; a refused program leaves it playing.

        Raises:
            CockpitRefusal: If the text is longer than `MAX_PEBBLE_CHARACTERS` or the
                program (with room for its stack) needs more words than this memory has.
            PebbleError: If Pebble itself finds a mistake in the program.
            UnsupportedFeature: If the program uses something PyCPU cannot do yet.

        """
        # Refuse a huge text before Pebble's compiler spends time on it: anything this long
        # could never fit in memory once translated.
        if len(source) > MAX_PEBBLE_CHARACTERS:
            msg = f"a Pebble program may be at most {MAX_PEBBLE_CHARACTERS:,} characters long"
            raise CockpitRefusal(msg)
        translated = translate(source)
        needed, words = len(translated.program.words), self.computer.gate.words
        if needed > words:
            msg = f"this program needs {needed} words, but this Cockpit's memory has only {words}"
            raise CockpitRefusal(msg)
        # Main's first frame sits just past the program; without room it would stop at once.
        if translated.memory_needed > words:
            msg = (
                f"this program needs room for its stack too ({translated.memory_needed} words "
                f"in all), but this Cockpit's memory has only {words}"
            )
            raise CockpitRefusal(msg)
        self.stop_playing()
        self.computer.load_program(translated.program)
        self.computer.pause()
        self._mark()  # a load marks nothing changed: `before` is the loaded state
        self.translated = translated
        self.assembly = translated.assembly
        self.program = translated.program
        self.loads += 1

    def step(self, size: StepSize, count: int = 1) -> None:
        """Step the paused computer by `size`, `count` times.

        A gate step may carry a `count` from 1 to `MAX_GATE_STEPS`, because one
        instruction is thousands of gate steps; the steps stop early if the machine
        halts. A cycle or instruction step may only say `count` 1.

        Raises:
            CockpitRefusal: For a count out of range or a count with a bigger step.
            CockpitBusy: While playing.

        """
        _check_whole("count", count, MAX_GATE_STEPS)
        if size != StepSize.GATE and count != 1:
            msg = "count is only for gate steps"
            raise CockpitRefusal(msg)
        self._begin()
        start = self.computer.instruction_start
        taken = finished = 0
        for _ in range(count):
            micro = self.computer.step(size)
            self.last_gate = micro
            taken += 1
            # Only an instruction's end can leave the machine halted, so look only there.
            if micro is not None and micro.kind == "end":
                finished += 1
                if self.computer.state().halted:
                    break
        # A clock beat is made of clock-wire moves as well as gates, so a gate step can end
        # on one; say so, rather than leave the page with nothing to show and no reason.
        last = self.last_gate
        if size == StepSize.GATE and last is not None and last.kind != "gate":
            self.note = no_gate_note(last)
        if not self.before.halted:
            self._describe_step(size, start, finished, taken)

    def _describe_step(
        self, size: StepSize, start: MachineState, finished: int, taken: int
    ) -> None:
        """Write `happened` for a gate, beat or instruction step that has just moved.

        Args:
            size: The step size that was taken.
            start: `instruction_start` before the step, so the sentence covers the
                whole instruction even when the step began part-way through it.
            finished: How many instructions the gate steps finished.
            taken: How many gate steps were taken.

        """
        after = self.computer.state()
        match size:
            case StepSize.GATE:
                last = self.last_gate
                path = None
                if last is not None and last.kind == "gate":
                    path = self.computer.gate.simulator.circuit.scope_of(last.gate)
                sentence = describe_move(
                    Depth.GATE, start, after, last, self.translated, finished, gate_path=path
                )
                self.happened = sentence if taken == 1 else describe_gate_steps(taken, sentence)
            case StepSize.CYCLE:
                ran = int(self.computer.gate.at_boundary)  # a beat that ends an instruction
                self.happened = describe_move(Depth.PART, start, after, None, self.translated, ran)
            case StepSize.INSTRUCTION:
                self.happened = describe_move(
                    Depth.INSTRUCTION, start, after, None, self.translated, 1
                )

    def step_at(self, depth: Depth) -> None:
        """Press Step at `depth`: one line, one instruction, one beat or one gate.

        Each depth is one of the older moves: `step_line(into=False)` for a line,
        `step` with `StepSize.INSTRUCTION`, `CYCLE` or `GATE` for the others. A depth
        that cannot move does not raise: the machine stays as it is and `note` says
        why, in plain words. That is a halted machine at any depth
        (`FINISHED_NOTE`), or a line step on assembly (`NO_LINES_NOTE`). A step
        started part-way through a smaller one finishes that one first.

        Raises:
            CockpitBusy: While playing.

        """
        self._begin()
        if self.computer.state().halted:
            self.note = FINISHED_NOTE
            return
        match depth:
            case Depth.LINE if self.translated is None:
                self.note = NO_LINES_NOTE
            case Depth.LINE:
                self.step_line(into=False)
            case Depth.INSTRUCTION:
                self.step(StepSize.INSTRUCTION)
            case Depth.PART:
                self.step(StepSize.CYCLE)
            case Depth.GATE:
                self.step(StepSize.GATE)

    def rewind(self) -> None:
        """Go back to the start of the current instruction."""
        self._begin()
        moved = not self.computer.gate.at_boundary
        self.computer.rewind()
        self.happened = describe_rewind(moved=moved)

    def run(self, instructions: int) -> int:
        """Resume, run up to `instructions` instructions on the fast engine, and pause again.

        Returns:
            How many instructions ran.

        Raises:
            CockpitRefusal: For a count outside 1 to `MAX_RUN`.
            CockpitBusy: While playing.

        """
        _check_whole("instructions", instructions, MAX_RUN)
        self._begin()
        # `resume` finishes a part-done instruction in the gates; it ran too, so say so.
        finishing = int(not self.computer.gate.at_boundary)
        self.computer.resume()
        try:
            ran = self.computer.run(instructions)
        finally:
            self.computer.pause()
        self.happened = describe_run(ran, self.computer.state(), finishing)
        return ran

    def step_line(self, *, into: bool) -> LineStep:
        """Run to the next Pebble line on the fast engine, then pause there in the gates.

        The step starts from the current instruction's line and frame pointer (`r7`).
        It finishes a part-done instruction in the gates (`resume`), then runs one
        instruction at a time on the fast engine. Before each one it stops if the
        word has a ready frame and a Pebble line, and that line or the frame pointer
        differs from the start. A step over (`into=False`) also needs the frame
        pointer at or above the start's, so it runs a whole call; a step into stops
        on the called function's first line. Runtime routine words have no line, so
        they never stop a step. It also stops when the program halts, or after
        `MAX_LINE_INSTRUCTIONS` instructions, and it always pauses at the end.
        `note` says why it stopped, and `instructions` counts only the fast engine's
        instructions, not one the gates finish first.

        A step that starts where no frame is ready (a prologue word, a return's `ret`
        or a routine) has no frame of its own to compare against. Its `start_fp` is
        taken from the first ready word it reaches instead, so it stops at the next
        *different* line: pressing it just after a load reaches the program's second
        line, and a step over from a function's prologue runs on past its first line.

        Args:
            into: True to step into a call; False to step over it.

        Returns:
            How many instructions ran and why the step stopped.

        Raises:
            CockpitRefusal: If the program is assembly, which has no lines to step.
            CockpitBusy: While playing.

        """
        translated = self.translated
        if translated is None:
            raise CockpitRefusal(NOT_PEBBLE_MESSAGE)
        self._begin()
        if self.before.halted:
            self.note = FINISHED_NOTE
            return LineStep(0, "halted")
        start = self.computer.instruction_start
        frames = translated.frames
        start_line, start_fp = translated.line_at(start.pc), start.registers[FRAME_POINTER]
        settled = start.pc < len(frames) and frames[start.pc] is not None
        finishing = int(not self.computer.gate.at_boundary)  # `resume` finishes it in the gates
        self.computer.resume()
        fast = self.computer.fast
        ran, stopped, line = 0, "limit", None
        try:
            while True:
                if fast.halted:
                    stopped = "halted"
                    break
                pc, fp = fast.pc, fast.register(FRAME_POINTER)
                line = translated.line_at(pc)
                ready = pc < len(frames) and frames[pc] is not None
                if ready and not settled:
                    start_fp, settled = fp, True  # the start's own frame, now made
                moved = line != start_line or fp != start_fp
                if ready and line is not None and moved and (into or fp >= start_fp):
                    stopped = "line"
                    break
                if ran == MAX_LINE_INSTRUCTIONS:
                    break
                fast.step()
                ran += 1
        finally:
            self.computer.pause()
        self.note = _line_note(ran, stopped, line)
        self.happened = describe_move(
            Depth.LINE, start, self.computer.state(), None, translated, ran, finishing=finishing
        )
        return LineStep(ran, stopped)


def _line_note(ran: int, stopped: str, line: int | None) -> str:
    """Say in one sentence why a line step that moved stopped where it did."""
    if stopped == "line":
        return f"Ran {count_instructions(ran)} to reach line {line}."
    if stopped == "halted":
        return f"Ran {count_instructions(ran)}, and then the program stopped."
    return (
        f"Ran {count_instructions(ran)} without reaching another line, so the step gave up "
        f"there; {LIMIT_REASON}."
    )
