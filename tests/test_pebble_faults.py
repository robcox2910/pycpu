"""Check that faults on PyCPU are reported against the Pebble line that caused them.

Where a program fails on Pebble's own VM, the VM's error names a line. These tests run
the same program on both machines and check that PyCPU stops with the right fault and
names the same line, then check the friendly sentence for every way a run can end.
"""

import pebble
import pytest

from pycpu.fast import FastMachine
from pycpu.isa import Fault
from pycpu.translator import run_pebble, translate

THREE_DEEP = (
    "fn c(n) {\n    return 10 OP n\n}\nfn b(n) {\n    return c(n)\n}\n"
    "fn a(n) {\n    return b(n)\n}\nprint(1)\nprint(a(0))"
)
ENDLESS_RECURSION = "fn f(n) {\n    return f(n + 1)\n}\nprint(f(0))"
ENDLESS_LOOP = "let i = 0\nwhile i < 1 {\n    i = i + 0\n}"
DIVISION_LINE = 2
TOP_LEVEL_LINE = 3
TWO_STEP_BUDGET = 500
# Measured: the three-deep program stops with pc one past its `halt 3` word.
HALT_WORD = 42
ENDLESS_RECURSION_STEPS = 23654


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

    def test_the_vm_has_no_clean_error_for_the_same_program(self) -> None:
        """The program is endless on the VM, so it is only checked on PyCPU (see report)."""
        assert run_pebble(ENDLESS_RECURSION).output == ""


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
            "The stack ran out of room at line 2 (does a function keep calling itself?)"
        )

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
