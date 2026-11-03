"""The computer: a football match you can pause, replay in slow motion, rewind and rejoin live.

The match races along live on the fast engine. Press pause and the picture freezes
just before the next move, and the whole machine is carried over to the slow-motion
camera, the gate engine, where every gate can be watched thinking. Nudge the replay
forward a gate, a clock beat or an instruction at a time; rewind it to the start of
the move; press play, and the replay finishes the move before the match carries on
live from exactly that moment.

`Computer` is the remote control. It works nothing out itself: it only decides which
engine is live and copies a `MachineState` from one to the other, always at an
instruction boundary, the only moment both engines understand.
"""

from collections.abc import Sequence
from enum import StrEnum

from pycpu.assembler import Program
from pycpu.cpu import GateMachine, MicroStep
from pycpu.fast import FastMachine
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.state import MachineState


class StepSize(StrEnum):
    """How far one paused step moves the gate engine.

    Attributes:
        GATE: One gate works out its output, or one clock wire moves.
        CYCLE: Finish the current clock beat, or play a whole one from its start.
        INSTRUCTION: Finish the current instruction, or play a whole one from its start.

    """

    GATE = "gate"
    CYCLE = "cycle"
    INSTRUCTION = "instruction"


class Computer:
    """A whole computer with two engines: run it fast, pause it into the gates, step and rewind.

    While running, the fast engine is live. `pause` copies its state into the gate
    engine and remembers it as `instruction_start`, the frame `rewind` goes back to.
    `step` moves the gates forward; whenever an instruction ends, `instruction_start`
    moves to the new boundary. `resume` finishes the current instruction in the gates
    and copies the state back to the fast engine.

    Attributes:
        fast: The fast engine, live while running.
        gate: The gate engine, live while paused. It is built once, here, because
            building a full-size one takes a few seconds.
        paused: True while the gate engine holds the machine.
        instruction_start: The state at the start of the current instruction, set by
            `pause` and moved on whenever a step finishes an instruction.

    """

    def __init__(
        self, program: Program | Sequence[int], address_bits: int = RAM_ADDRESS_BITS
    ) -> None:
        """Build both engines and load `program` into them, running and unpaused.

        Args:
            program: An assembled `Program`, or the plain words of one.
            address_bits: How many address wires the RAM has; both engines get
                `2 ** address_bits` words.

        """
        self.gate = GateMachine(address_bits)
        self.fast = FastMachine(self.gate.words)
        self.paused = False
        self.instruction_start = self.fast.state()
        self.load_program(program)

    def load_program(self, program: Program | Sequence[int]) -> None:
        """Power both engines on with `program` in memory, and go back to running."""
        words = program.words if isinstance(program, Program) else program
        self.fast.load_program(words)
        self.gate.load_program(words)
        self.paused = False
        self.instruction_start = self.fast.state()

    def _require(self, *, paused: bool) -> None:
        """Refuse a call that only makes sense for the other engine being live."""
        if self.paused != paused:
            msg = "the computer is paused" if self.paused else "the computer is not paused"
            raise RuntimeError(msg)

    def run(self, max_steps: int) -> int:
        """Run up to `max_steps` instructions on the fast engine; return how many ran.

        Raises:
            RuntimeError: If the computer is paused; `resume` first.

        """
        self._require(paused=False)
        return self.fast.run(max_steps)

    def pause(self) -> None:
        """Freeze between two instructions and carry the machine into the gate engine.

        Raises:
            RuntimeError: If the computer is already paused, because pausing again
                would throw away the steps taken in the gates.

        """
        if self.paused:
            msg = "the computer is already paused"
            raise RuntimeError(msg)
        self.instruction_start = self.fast.state()
        self.gate.load_state(self.instruction_start)
        self.paused = True

    def step(self, size: StepSize) -> MicroStep | None:
        """Move the paused gate engine forward by one gate, one beat or one instruction.

        `GATE` returns the `MicroStep` that happened; when it is of kind `"end"`, the
        instruction has finished. `CYCLE` finishes the current clock beat (or plays a
        whole one). `INSTRUCTION` finishes the current instruction if one is part-way
        through, and otherwise plays one whole instruction. Whenever a step leaves the
        machine at an instruction boundary having moved, `instruction_start` becomes
        that new state. A halted machine does not move.

        Returns:
            The micro step for `GATE`; None for `CYCLE` and `INSTRUCTION`.

        Raises:
            RuntimeError: If the computer is not paused.

        """
        self._require(paused=True)
        micro = None
        match size:
            case StepSize.GATE:
                micro = self.gate.micro_step()
                finished = micro.kind == "end"
            case StepSize.CYCLE:
                self.gate.step_cycle()
                finished = self.gate.at_boundary
            case StepSize.INSTRUCTION:
                self.gate.step()
                finished = True
        if finished:
            self.instruction_start = self.gate.state()
        return micro

    def rewind(self) -> None:
        """Go back to the start of the current instruction by reloading `instruction_start`.

        Raises:
            RuntimeError: If the computer is not paused.

        """
        self._require(paused=True)
        self.gate.load_state(self.instruction_start)

    def resume(self) -> None:
        """Finish the current instruction in the gates, copy the state to the fast engine, run on.

        At a boundary there is nothing to finish, so the state is copied as it is.

        Raises:
            RuntimeError: If the computer is not paused.

        """
        self._require(paused=True)
        if not self.gate.at_boundary:
            self.gate.step()
        self.fast.load_state(self.gate.state())
        self.paused = False

    def state(self) -> MachineState:
        """Return the live engine's state: the gates' while paused, the fast engine's otherwise."""
        return self.gate.state() if self.paused else self.fast.state()
