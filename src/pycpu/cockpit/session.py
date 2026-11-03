"""The Cockpit's session: the one running computer and every rule about moving it.

Think of the pilot's seat: the pilot is the only one who moves the controls, and the
seat refuses anything that would break the aeroplane. A `Cockpit` owns the single
real `Computer`, the program on it (with its Pebble source map when there is one),
and the state just before the last move. Every move goes through its methods, which
refuse bad requests with a `CockpitRefusal` that names the reason; the web app only
reads requests and answers, and the picture module only reads.
"""

from pycpu.assembler import AssemblyError, assemble
from pycpu.computer import Computer, StepSize
from pycpu.cpu import MicroStep
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.state import MachineState
from pycpu.translator import TranslatedProgram, translate

MAX_RUN = 10_000  # the most instructions one press of Run may ask for
MAX_GATE_STEPS = 100_000  # the most gate steps one request may ask for
MAX_PEBBLE_CHARACTERS = 65_536  # far more Pebble than fits in 4K words once translated

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


class CockpitRefusal(Exception):  # noqa: N818
    """Say that the Cockpit will not do what was asked, and why, in one sentence."""


class CockpitBusy(CockpitRefusal):
    """Say that the computer is playing, so only pause or a load is allowed."""


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
        playing: Whether the computer is running on its own.

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
        self.playing = False

    def _begin(self, *, load: bool = False) -> None:
        """Start a move: refuse it if playing (loads excepted), then set `before` and clear notes."""
        if self.playing and not load:
            raise CockpitBusy(BUSY_MESSAGE)
        self.before = self.computer.state()
        self.note = None
        self.last_gate = None

    def load_assembly(self, source: str) -> None:
        """Assemble `source`, load it and pause at its start.

        Raises:
            CockpitRefusal: Naming the line the assembler refused; the machine is left as it was.

        """
        try:
            assembled = assemble(source, words=self.computer.gate.words)
        except AssemblyError as error:
            raise CockpitRefusal(str(error)) from None
        self._begin(load=True)
        self.computer.load_program(assembled)
        self.computer.pause()
        self.translated = None
        self.assembly = source
        self.program = assembled

    def load_pebble(self, source: str) -> None:
        """Translate a Pebble program, load it and pause at its start.

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
        self._begin(load=True)
        self.computer.load_program(translated.program)
        self.computer.pause()
        self.translated = translated
        self.assembly = translated.assembly
        self.program = translated.program

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
        for _ in range(count):
            micro = self.computer.step(size)
            self.last_gate = micro
            # Only an instruction's end can leave the machine halted, so look only there.
            if micro is not None and micro.kind == "end" and self.computer.state().halted:
                break

    def rewind(self) -> None:
        """Go back to the start of the current instruction."""
        self._begin()
        self.computer.rewind()

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
        self.computer.resume()
        ran = self.computer.run(instructions)
        self.computer.pause()
        return ran
