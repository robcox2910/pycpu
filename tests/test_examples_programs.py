"""Check the Cockpit's example programs: each one fits, runs, and agrees with Pebble's VM.

The examples are the first programs a visitor to the Cockpit loads, like the demo
discs in a shop's games console, so each must fit in the real 4K machine and print
exactly what Pebble's own VM prints. The tour must also show off every piece of
Pebble that PyCPU can run.
"""

import re
from pathlib import Path

import pebble
import pytest
from pebble import CodeObject, OpCode, compile_source

from pycpu.cockpit.app import EXAMPLE_NAMES
from pycpu.isa import Fault
from pycpu.memory import RAM_WORDS
from pycpu.translator import run_pebble, translate

EXAMPLES = Path(__file__).parent.parent / "src" / "pycpu" / "cockpit" / "examples"
FAULTING = "divide-by-zero"
TOUR_MEMORY_WORDS = 456  # pinned: the Cockpit page says the tour needs 456 words
FOR_RANGE = re.compile(r"^\s*for \w+ in range\(", flags=re.MULTILINE)
TOUR_OPCODES = {
    OpCode.JUMP_IF_FALSE,
    OpCode.JUMP_IF_FALSE_OR_POP,
    OpCode.JUMP_IF_TRUE_OR_POP,
    OpCode.NOT,
    OpCode.MULTIPLY,
    OpCode.FLOOR_DIVIDE,
    OpCode.MODULO,
    OpCode.NEGATE,
    OpCode.PRINT,
    OpCode.CALL,
}


def _source(name: str) -> str:
    """Read the example called `name`."""
    return (EXAMPLES / f"{name}.pebble").read_text(encoding="utf-8")


def _codes(source: str) -> list[CodeObject]:
    """Compile `source` with Pebble and return main's code and every function's."""
    compiled = compile_source(source).compiled
    return [compiled.main, *compiled.functions.values()]


def test_the_list_names_every_file_once() -> None:
    """Every .pebble file in the folder is in the fixed list, and nothing else is."""
    assert sorted(p.stem for p in EXAMPLES.glob("*.pebble")) == sorted(EXAMPLE_NAMES)
    assert EXAMPLE_NAMES[0] == "tour"


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_each_example_starts_with_a_title_comment(name: str) -> None:
    """The first line is a `#` comment with words in it: the example's title."""
    first = _source(name).splitlines()[0]
    assert first.startswith("# ")
    assert first.removeprefix("# ").strip()


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_each_example_fits_in_the_real_machine(name: str) -> None:
    """The program, its text and main's first frame fit in 4K words."""
    assert translate(_source(name)).memory_needed <= RAM_WORDS


@pytest.mark.parametrize("name", [n for n in EXAMPLE_NAMES if n != FAULTING])
def test_each_example_prints_what_pebbles_vm_prints(name: str) -> None:
    """On PyCPU's fast engine the example finishes cleanly with the VM's output."""
    source = _source(name)
    run = run_pebble(source)
    assert run.halted
    assert run.fault is None
    assert run.output == pebble.run_source(source)


def test_divide_by_zero_faults_on_the_vms_line() -> None:
    """The faulting example stops with DIVIDE_BY_ZERO on the line the VM blames."""
    source = _source(FAULTING)
    run = run_pebble(source)
    assert run.fault is Fault.DIVIDE_BY_ZERO
    with pytest.raises(pebble.PebbleError) as caught:
        pebble.run_source(source)
    assert run.line == caught.value.line


class TestTheTour:
    """The tour uses every subset feature, which spec section 9 asks for."""

    def test_its_bytecode_has_every_feature_opcode(self) -> None:
        """Conditions, and/or/not, multiply, divide, remainder, negation, print and calls all appear."""
        used = {i.opcode for code in _codes(_source("tour")) for i in code.instructions}
        assert used >= TOUR_OPCODES

    def test_it_calls_a_function_that_calls_itself(self) -> None:
        """Some function's code CALLs that same function, and main calls it."""
        compiled = compile_source(_source("tour")).compiled
        recursive = {
            name
            for name, code in compiled.functions.items()
            if any(i.opcode is OpCode.CALL and i.operand == name for i in code.instructions)
        }
        assert recursive
        called = {i.operand for code in _codes(_source("tour")) for i in code.instructions}
        assert recursive <= called

    def test_it_prints_text_and_a_number(self) -> None:
        """One PRINT follows a text constant, another follows something that is not text."""
        kinds: set[bool] = set()
        for code in _codes(_source("tour")):
            for before, now in zip(code.instructions, code.instructions[1:], strict=False):
                if now.opcode is OpCode.PRINT:
                    index = before.operand
                    is_text = (
                        before.opcode is OpCode.LOAD_CONST
                        and isinstance(index, int)
                        and isinstance(code.constants[index], str)
                    )
                    kinds.add(is_text)
        assert kinds == {True, False}

    def test_it_has_a_for_over_range(self) -> None:
        """A `for ... in range(` line, lowered by Pebble to a hidden limit and jumps.

        Pebble has no FOR opcode for a range: it stores the end in a `$for_limit_`
        variable, compares with LESS_THAN, and jumps back with JUMP.
        """
        source = _source("tour")
        assert FOR_RANGE.search(source)
        main = compile_source(source).compiled.main.instructions
        stored = {i.operand for i in main if i.opcode is OpCode.STORE_NAME}
        assert any(str(name).startswith("$for_limit_") for name in stored)
        assert {OpCode.LESS_THAN, OpCode.JUMP} <= {i.opcode for i in main}

    def test_it_needs_the_memory_the_page_says(self) -> None:
        """The Cockpit page says the tour needs 456 words of memory."""
        assert translate(_source("tour")).memory_needed == TOUR_MEMORY_WORDS
