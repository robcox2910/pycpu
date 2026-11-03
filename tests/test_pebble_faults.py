"""Check that faults on PyCPU are reported against the Pebble line that caused them.

Where a program fails on Pebble's own VM, the VM's error names a line. These tests run
the same program on both machines and check that PyCPU stops with the right fault and
names the same line, then check the friendly sentence for every way a run can end.
"""

from collections.abc import Callable

import pebble
import pytest

from pycpu.computer import Computer, StepSize
from pycpu.fast import FastMachine
from pycpu.isa import Fault
from pycpu.state import MachineState
from pycpu.translator import PebbleRun, UnsupportedFeature, run_pebble, translate

THREE_DEEP = (
    "fn c(n) {\n    return 10 OP n\n}\nfn b(n) {\n    return c(n)\n}\n"
    "fn a(n) {\n    return b(n)\n}\nprint(1)\nprint(a(0))"
)
ENDLESS_RECURSION = "fn f(n) {\n    return f(n + 1)\n}\nprint(f(0))"
ENDLESS_LOOP = "let i = 0\nwhile i < 1 {\n    i = i + 0\n}"
DIVISION_LINE = 2
TOP_LEVEL_LINE = 3
CALL_LINE = 4
TOP_LEVEL_CALL_LINE = 5
TWO_STEP_BUDGET = 500
# Three prints fit in 128 words (119) but main's frame after them (130 in all) does not.
MAIN_OVERFLOW_PRINTS = 3
MAIN_OVERFLOW_WORDS = 128
# Measured: the three-deep program stops with pc one past its `halt 3` word.
HALT_WORD = 42
ENDLESS_RECURSION_STEPS = 23654


def _nearly_full_program() -> str:
    """Build a program whose text leaves so little RAM that calling `f` once overflows."""
    for length in range(3900, 4000):
        source = f'fn f(n) {{\n    return n\n}}\nprint("{"a" * length}")\nprint(f(1))'
        try:
            run = run_pebble(source)
        except UnsupportedFeature:
            break
        if run.fault is Fault.STACK_OVERFLOW:
            return source
    msg = "no length of text made the first call overflow"
    raise AssertionError(msg)


def vm_error_line(source: str) -> int:
    """Run `source` on the Pebble VM, which must fail, and return the line it names."""
    with pytest.raises(pebble.PebbleError) as caught:
        pebble.run_source(source)
    return caught.value.line


class TestDivisionByZero:
    """Dividing by zero stops the machine and names the VM's own line."""

    @pytest.mark.parametrize("operator", ["//", "%"])
    def test_three_calls_deep_names_the_same_line_as_the_vm(self, operator: str) -> None:
        """A divide or remainder by zero in `c`, called from `b` from `a`, names line 2."""
        source = THREE_DEEP.replace("OP", operator)
        run = run_pebble(source)
        assert run.fault is Fault.DIVIDE_BY_ZERO
        assert run.halted
        assert run.line == vm_error_line(source) == DIVISION_LINE

    @pytest.mark.parametrize("operator", ["//", "%"])
    def test_at_the_top_level_names_the_same_line_as_the_vm(self, operator: str) -> None:
        """A divide by zero on line 2 of main, after a print, names line 2 too."""
        source = f"print(1)\nlet z = 0\nprint(5 {operator} z)"
        run = run_pebble(source)
        assert run.fault is Fault.DIVIDE_BY_ZERO
        assert run.line == vm_error_line(source) == TOP_LEVEL_LINE

    def test_what_was_printed_before_the_fault_is_kept(self) -> None:
        """The `1` printed before the whistle is still in the output."""
        assert run_pebble(THREE_DEEP.replace("OP", "//")).output == "1\n"

    def test_the_fault_word_is_one_before_the_program_counter(self) -> None:
        """An execute fault leaves pc past the `halt`, and the source map knows that word."""
        translated = translate(THREE_DEEP.replace("OP", "//"))
        machine = FastMachine()
        machine.load_program(translated.program.words)
        machine.run(1_000_000)
        state = machine.state()
        assert state.pc - 1 == HALT_WORD
        assert translated.line_at(HALT_WORD) == DIVISION_LINE


class TestStackOverflow:
    """Endless recursion fills the stack and stops the machine at the function's line."""

    def test_endless_recursion_faults_at_the_function_line(self) -> None:
        """`f` calling itself for ever gives STACK_OVERFLOW, at the line of `f`'s body."""
        run = run_pebble(ENDLESS_RECURSION)
        assert run.fault is Fault.STACK_OVERFLOW
        assert run.halted
        assert run.line == DIVISION_LINE
        assert run.steps == ENDLESS_RECURSION_STEPS

    def test_a_multi_line_body_names_the_line_of_the_call_not_the_function(self) -> None:
        """The call `f(y)` on line 4 is blamed, not line 2 where `f`'s body starts."""
        source = "fn f(n) {\n    let x = n + 1\n    let y = x\n    return f(y)\n}\nprint(f(0))"
        run = run_pebble(source)
        assert run.fault is Fault.STACK_OVERFLOW
        assert run.line == CALL_LINE

    def test_nothing_is_printed_by_the_endless_recursion(self) -> None:
        """The overflow stops the program before `print` runs."""
        assert run_pebble(ENDLESS_RECURSION).output == ""

    def test_a_call_from_the_top_level_that_never_fits_names_that_call(self) -> None:
        """With almost no RAM left, the very first call on line 5 overflows and is blamed."""
        run = run_pebble(_nearly_full_program())
        assert run.fault is Fault.STACK_OVERFLOW
        assert run.line == TOP_LEVEL_CALL_LINE
        assert run.describe().startswith("The stack ran out of room at line 5")


class TestRunningOutOfSteps:
    """A program that never stops is given up on, not blamed."""

    def test_an_endless_while_is_still_running_after_max_steps(self) -> None:
        """No fault, no line, and `halted` is False."""
        run = run_pebble(ENDLESS_LOOP, max_steps=TWO_STEP_BUDGET)
        assert not run.halted
        assert run.fault is None
        assert run.line is None
        assert run.steps == TWO_STEP_BUDGET


class TestNormalFinish:
    """A program that works ends with no fault and no line."""

    def test_a_normal_finish_has_no_fault_and_no_line(self) -> None:
        """`print(7)` halts with fault None and line None."""
        run = run_pebble("print(7)")
        assert run.halted
        assert run.fault is None
        assert run.line is None


class TestDescribe:
    """`describe()` says how a run ended in one friendly sentence."""

    def test_division_by_zero(self) -> None:
        """The sentence names the fault and the line."""
        assert run_pebble(THREE_DEEP.replace("OP", "//")).describe() == "Division by zero at line 2"

    def test_stack_overflow(self) -> None:
        """The sentence names the line and suggests what to look for."""
        assert run_pebble(ENDLESS_RECURSION).describe() == (
            "The stack ran out of room at line 2 (the call on that line found no room for another frame; does a function keep calling itself?)"
        )

    def test_a_main_that_does_not_fit_blames_no_call(self) -> None:
        """When main's own frame has no room, the sentence does not mention a call."""
        source = "print(1)\n" * MAIN_OVERFLOW_PRINTS
        translated = translate(source)
        machine = FastMachine(MAIN_OVERFLOW_WORDS)
        machine.load_program(translated.program.words)
        steps = machine.run(TWO_STEP_BUDGET)
        run = PebbleRun.from_state(translated, machine.state(), steps)
        assert run.fault is Fault.STACK_OVERFLOW
        assert not run.by_call
        assert run.describe().startswith("The program needs more stack room than there is at line")
        assert "call" not in run.describe()

    def test_still_running(self) -> None:
        """The sentence says how many steps it was given."""
        run = run_pebble(ENDLESS_LOOP, max_steps=TWO_STEP_BUDGET)
        assert run.describe() == "The program was still running after 500 steps"

    def test_finished(self) -> None:
        """A clean run says it finished."""
        assert run_pebble("print(7)").describe() == "The program finished"

    def test_a_bad_address_without_a_line(self) -> None:
        """A fault with no known line leaves the line out."""
        run = run_pebble("print(7)")
        broken = type(run)("", True, Fault.BAD_ADDRESS, None, 1)
        assert broken.describe() == "The program used a memory address that does not exist"

    def test_a_fault_without_a_line_names_only_the_fault(self) -> None:
        """Division by zero with line None still reads well."""
        run = run_pebble("print(7)")
        assert type(run)("", True, Fault.DIVIDE_BY_ZERO, None, 1).describe() == "Division by zero"


SMALL_BITS = 8  # 256 words: room for each program below and a few frames
GATE_TAIL = 3  # how many final instructions run on the gate engine
RECURSIVE_CALL_LINE = 2  # `return f(n + 1)`, the call that finds no room
FROM_STATE_CASES = [
    ("let a = 7\nprint(a)\n", "7\n", None, None),
    ("let a = 7\nprint(a // 0)\n", "", Fault.DIVIDE_BY_ZERO, DIVISION_LINE),
    (ENDLESS_RECURSION, "", Fault.STACK_OVERFLOW, RECURSIVE_CALL_LINE),
]


def _fast_state(source: str) -> tuple[MachineState, int]:
    """Run `source` to its halt on a small fast engine; return its state and step count."""
    machine = FastMachine(1 << SMALL_BITS)
    machine.load_program(translate(source).program.words)
    steps = machine.run(1_000_000)
    return machine.state(), steps


def _gate_state(source: str) -> tuple[MachineState, int]:
    """Run `source` fast to just before its halt, then finish on the gate engine."""
    _, steps = _fast_state(source)
    computer = Computer(translate(source).program, SMALL_BITS)
    computer.run(steps - GATE_TAIL)
    computer.pause()
    while not computer.state().halted:
        computer.step(StepSize.INSTRUCTION)
    return computer.state(), steps


class TestReadingARunFromAState:
    """`PebbleRun.from_state` reads the same ending from either engine's state."""

    @pytest.mark.parametrize("engine", [_fast_state, _gate_state], ids=["fast", "gate"])
    @pytest.mark.parametrize(
        ("source", "output", "fault", "line"),
        FROM_STATE_CASES,
        ids=["finished", "divide-by-zero", "stack-overflow"],
    )
    def test_the_ending_is_read_from_the_machine(
        self,
        engine: Callable[[str], tuple[MachineState, int]],
        source: str,
        output: str,
        fault: Fault | None,
        line: int | None,
    ) -> None:
        """Output, fault and blamed line come from the state; the step count is passed through."""
        state, steps = engine(source)
        run = PebbleRun.from_state(translate(source), state, steps)
        assert run == PebbleRun(output, True, fault, line, steps)
