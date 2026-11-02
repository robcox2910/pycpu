"""The computer: watch the live match fast, pause into the slow-motion replay, rewind, go live.

A `Computer` runs a program on the fast engine and, when paused, carries the whole
machine into the gate engine so a learner can creep through one instruction gate by
gate, rewind to its start, and resume. These tests check the promise that makes that
honest: however you pause, step and rewind, resuming ends in exactly the state a
straight fast run reaches, with no drift.
"""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pycpu.assembler import Program, assemble
from pycpu.computer import Computer, StepSize
from pycpu.cpu import Phase
from pycpu.fast import FastMachine
from pycpu.state import MachineState

ADDRESS_BITS = 6
WORDS = 1 << ADDRESS_BITS
RUN_LIMIT = 1_000
COUNTDOWN_STEPS = 19  # instructions the countdown runs, counting its HALT
# One countdown instruction takes about 6,300 to 13,400 gate steps at this size, so
# these ranges reach the start, middle and end of an instruction and spill past it.
MAX_REWIND_GATE_STEPS = 15_000
MAX_RESUME_GATE_STEPS = 30_000
FIRST_PAUSE = 3
FIRST_STORE = 5  # the countdown's first `store r3, [r1]`, to the output port

COUNTDOWN = """
    set r1, 0xFFFF
    li r2, 3
loop:
    li r3, 48
    add r3, r3, r2
    store r3, [r1]
    addi r2, -1
    br ne, loop
    halt
"""


@pytest.fixture(scope="module")
def program() -> Program:
    """Assemble the countdown once for the whole module."""
    return assemble(COUNTDOWN, words=WORDS)


@pytest.fixture(scope="module")
def computer(program: Program) -> Computer:
    """Build one small computer for the module; each test reloads its program."""
    return Computer(program, address_bits=ADDRESS_BITS)


def _fresh(computer: Computer, program: Program) -> Computer:
    """Put the shared computer back to the start of the program, running and unpaused."""
    computer.load_program(program)
    return computer


def _fast_after(state: MachineState, steps: int) -> MachineState:
    """Return the state the fast engine alone reaches after `steps` steps from `state`."""
    fast = FastMachine(len(state.memory))
    fast.load_state(state)
    fast.run(steps)
    return fast.state()


def test_a_computer_accepts_plain_words_as_its_program(program: Program) -> None:
    """A list of words works as well as an assembled `Program`."""
    computer = Computer(list(program.words), address_bits=ADDRESS_BITS)
    computer.run(RUN_LIMIT)
    assert computer.state().output_text == "321"


def test_running_a_program_prints_the_countdown(computer: Computer, program: Program) -> None:
    """Unpaused, the computer runs the fast engine to the end and counts the steps."""
    _fresh(computer, program)
    assert computer.run(RUN_LIMIT) == COUNTDOWN_STEPS
    assert computer.state().output_text == "321"
    assert computer.state().halted


def test_pause_lands_on_an_instruction_boundary(computer: Computer, program: Program) -> None:
    """After pausing, the gates sit between two instructions holding the fast engine's state."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    assert computer.paused
    assert computer.gate.at_boundary
    assert computer.state() == computer.fast.state()
    assert computer.instruction_start == computer.fast.state()


@settings(max_examples=60, deadline=None)
@given(gate_steps=st.integers(0, MAX_REWIND_GATE_STEPS))
def test_rewind_after_gate_steps_restores_the_instruction_start(
    computer: Computer, program: Program, gate_steps: int
) -> None:
    """Any number of gate steps, then rewind, puts the machine back at the instruction's start."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    for _ in range(gate_steps):
        computer.step(StepSize.GATE)
    computer.rewind()
    start = computer.instruction_start
    assert computer.state() == start
    assert computer.gate.at_boundary
    computer.step(StepSize.INSTRUCTION)
    assert computer.state() == _fast_after(start, 1)


@settings(max_examples=60, deadline=None)
@given(
    stop=st.integers(0, COUNTDOWN_STEPS + 1),
    gate_steps=st.integers(0, MAX_RESUME_GATE_STEPS),
    rewind_first=st.booleans(),
    more_gate_steps=st.integers(0, MAX_RESUME_GATE_STEPS),
)
def test_resume_mid_instruction_matches_a_straight_run(
    computer: Computer,
    program: Program,
    stop: int,
    gate_steps: int,
    rewind_first: bool,
    more_gate_steps: int,
) -> None:
    """Pause, wander through the gates, maybe rewind, wander again, resume: no drift at the end."""
    straight = FastMachine(WORDS)
    straight.load_program(program.words)
    straight.run(RUN_LIMIT)
    _fresh(computer, program)
    computer.run(stop)
    computer.pause()
    for _ in range(gate_steps):
        computer.step(StepSize.GATE)
    if rewind_first:
        computer.rewind()
    for _ in range(more_gate_steps):
        computer.step(StepSize.GATE)
    computer.resume()
    assert not computer.paused
    computer.run(RUN_LIMIT)
    assert computer.state() == straight.state()


def test_rewind_takes_back_a_character_already_sent_to_the_screen(
    computer: Computer, program: Program
) -> None:
    """Rewinding a STORE to the output port takes its character back off the screen."""
    _fresh(computer, program)
    computer.run(FIRST_STORE)
    computer.pause()
    start = computer.instruction_start
    assert start.output == ()
    while True:
        micro = computer.step(StepSize.GATE)
        assert micro is not None
        assert micro.kind != "end"
        if micro.phase == Phase.EXECUTE and micro.wire == "write" and micro.value == 1:
            break
    assert computer.state().output == (ord("3"),)
    computer.rewind()
    assert computer.state().output == ()
    assert computer.state() == start
    computer.step(StepSize.INSTRUCTION)
    assert computer.state() == _fast_after(start, 1)
    assert computer.state().output == (ord("3"),)


def test_resume_mid_instruction_finishes_that_instruction(
    computer: Computer, program: Program
) -> None:
    """Resuming half-way through an instruction hands the fast engine the finished one."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    start = computer.instruction_start
    computer.step(StepSize.CYCLE)
    computer.resume()
    assert computer.fast.state() == _fast_after(start, 1)


def test_resume_at_a_boundary_runs_nothing_extra(computer: Computer, program: Program) -> None:
    """Pausing and resuming straight away leaves the machine exactly where it was."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    before = computer.fast.state()
    computer.pause()
    computer.resume()
    assert computer.state() == before


def test_step_instruction_moves_the_rewind_point(computer: Computer, program: Program) -> None:
    """After a whole instruction, the next rewind goes back to the new boundary, not the old."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    old_start = computer.instruction_start
    computer.step(StepSize.INSTRUCTION)
    assert computer.instruction_start == _fast_after(old_start, 1)
    assert computer.instruction_start == computer.state()
    computer.rewind()
    assert computer.state() == _fast_after(old_start, 1)


def test_step_instruction_from_mid_instruction_finishes_only_that_one(
    computer: Computer, program: Program
) -> None:
    """Part-way through, an instruction step completes the current instruction, not one more."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    start = computer.instruction_start
    computer.step(StepSize.CYCLE)
    assert not computer.gate.at_boundary
    computer.step(StepSize.INSTRUCTION)
    assert computer.state() == _fast_after(start, 1)
    assert computer.instruction_start == computer.state()


def test_step_cycle_does_one_beat_and_moves_the_rewind_point_only_at_a_boundary(
    computer: Computer, program: Program
) -> None:
    """The fetch beat leaves the rewind point alone; the execute beat that ends the instruction moves it."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    start = computer.instruction_start
    computer.step(StepSize.CYCLE)
    assert computer.gate.phase == Phase.EXECUTE
    assert computer.state().pc == start.pc + 1
    assert computer.instruction_start == start
    computer.step(StepSize.CYCLE)
    assert computer.gate.at_boundary
    assert computer.instruction_start == _fast_after(start, 1)


def test_a_gate_step_returns_the_micro_step_and_the_end_moves_the_rewind_point(
    computer: Computer, program: Program
) -> None:
    """Gate steps hand back what moved; the step of kind "end" makes a new rewind point."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    start = computer.instruction_start
    first = computer.step(StepSize.GATE)
    assert first is not None
    assert first.kind in {"gate", "edge"}
    assert first.phase == Phase.FETCH
    micro = first
    while micro is not None and micro.kind != "end":
        assert computer.instruction_start == start
        micro = computer.step(StepSize.GATE)
    assert computer.instruction_start == _fast_after(start, 1)
    assert computer.state() == computer.instruction_start


def test_cycle_and_instruction_steps_return_nothing(computer: Computer, program: Program) -> None:
    """Only a gate step has a micro step to hand back."""
    _fresh(computer, program)
    computer.pause()
    assert computer.step(StepSize.CYCLE) is None
    assert computer.step(StepSize.INSTRUCTION) is None


def test_a_paused_halted_machine_stays_put(computer: Computer, program: Program) -> None:
    """Once halted, every step size changes nothing, and resume just copies the state back."""
    _fresh(computer, program)
    computer.run(RUN_LIMIT)
    final = computer.state()
    computer.pause()
    micro = computer.step(StepSize.GATE)
    assert micro is not None
    assert micro.kind == "end"
    computer.step(StepSize.CYCLE)
    computer.step(StepSize.INSTRUCTION)
    assert computer.state() == final
    assert computer.instruction_start == final
    computer.resume()
    assert computer.fast.state() == final


def test_loading_a_program_while_paused_goes_back_to_running(
    computer: Computer, program: Program
) -> None:
    """A fresh program starts on the fast engine, unpaused, at power-on."""
    _fresh(computer, program)
    computer.run(FIRST_PAUSE)
    computer.pause()
    computer.load_program(program)
    assert not computer.paused
    assert computer.run(RUN_LIMIT) == COUNTDOWN_STEPS


def test_run_while_paused_is_refused(computer: Computer, program: Program) -> None:
    """The fast engine cannot run while the gates hold the machine."""
    _fresh(computer, program)
    computer.pause()
    with pytest.raises(RuntimeError, match="paused"):
        computer.run(1)


def test_pausing_twice_is_refused(computer: Computer, program: Program) -> None:
    """A second pause would throw away the gates' progress, so it is refused."""
    _fresh(computer, program)
    computer.pause()
    with pytest.raises(RuntimeError, match="already paused"):
        computer.pause()


def test_stepping_while_running_is_refused(computer: Computer, program: Program) -> None:
    """Stepping, rewinding and resuming all need a paused computer."""
    _fresh(computer, program)
    with pytest.raises(RuntimeError, match="not paused"):
        computer.step(StepSize.GATE)
    with pytest.raises(RuntimeError, match="not paused"):
        computer.rewind()
    with pytest.raises(RuntimeError, match="not paused"):
        computer.resume()
