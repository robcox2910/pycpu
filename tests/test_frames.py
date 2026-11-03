"""Tests for the frame map: which frame `r7` points at before each word of a Pebble program."""

from pathlib import Path

import pytest
from pebble import compile_source

from pycpu.fast import FastMachine
from pycpu.isa import Opcode, decode
from pycpu.translator import FrameLayout, Slot, TranslatedProgram, translate
from pycpu.translator.codegen import MAIN_LABEL, function_label, is_pebble_name
from pycpu.translator.subset import check_program

CORPUS = sorted((Path(__file__).parent / "pebble_programs").glob("*.pebble"))
FRAME_POINTER = 7
RUNTIME_START = "__mul"  # the first label of the runtime routines, which follow all the code
PROLOGUE_TAIL = 2  # after `<label>_room:` come `push r7` and `getsp r7`, then the zeroing pushes
MAX_STEPS = 20_000  # enough to cover every frame shape in the corpus, and keep the test quick
ADD = """\
fn add(a, b) {
    let c = a + b
    return c
}
print(add(2, 3))
"""
A_OFFSET = 3
B_OFFSET = 2
C_OFFSET = -1
RANGE = """\
for i in range(3) {
    print(i)
}
"""


def _expected_frames(source: str, translated: TranslatedProgram) -> list[str | None]:
    """Work out, from the labels alone, which code's frame each word should carry.

    Each entry is `"main"`, a function's name, or None. A region of code runs from its
    label to the next one; its prologue ends with the last zeroing `push r0`; each `ret`
    in it has no frame; everything from the runtime routines on has none.
    """
    checked = check_program(compile_source(source).compiled)
    labels = translated.program.labels
    regions = [(labels[MAIN_LABEL], MAIN_LABEL, checked.main)]
    regions += [
        (labels[function_label(name)], function_label(name), code)
        for name, code in checked.functions.items()
    ]
    regions.sort(key=lambda region: region[0])
    ends = [start for start, _, _ in regions[1:]] + [labels[RUNTIME_START]]
    expected: list[str | None] = [None] * len(translated.program.words)
    for (start, label, code), end in zip(regions, ends, strict=True):
        ready = labels[f"{label}_room"] + PROLOGUE_TAIL + len(code.variables)
        for address in range(ready, end):
            word = translated.program.words[address]
            if decode(word).opcode != Opcode.RET:
                expected[address] = code.name
        assert start < ready <= end
    return expected


def _main_frame_pointer(translated: TranslatedProgram) -> int:
    """Return the address of `getsp r7` in main's prologue, after which r7 is main's frame."""
    return translated.program.labels[f"{MAIN_LABEL}_room"] + 1


class TestTheLayout:
    """Each piece of code's layout lists its names at the offsets the code uses."""

    def test_a_function_lists_its_parameters_then_its_variables(self) -> None:
        """`add(a, b)` keeps `a` at +3, `b` at +2, and its own `c` at -1."""
        translated = translate(ADD)
        layouts = {f for f in translated.frames if f is not None and f.function == "add"}
        assert layouts == {
            FrameLayout(
                "add",
                (
                    Slot("a", A_OFFSET, "parameter", hidden=False),
                    Slot("b", B_OFFSET, "parameter", hidden=False),
                    Slot("c", C_OFFSET, "variable", hidden=False),
                ),
            )
        }

    def test_the_offsets_are_the_ones_the_code_uses(self) -> None:
        """The assembly loads `a` from `[r7+3]` and stores `c` to `[r7-1]`, as the layout says."""
        assembly = translate(ADD).assembly
        assert "load r1, [r7+3]" in assembly
        assert "store r1, [r7-1]" in assembly

    def test_the_top_level_has_no_function_name(self) -> None:
        """Main's layout says None, so a user function called `main` is never confused with it."""
        translated = translate("fn main() {\n    return 1\n}\nlet x = main()\nprint(x)\n")
        names = {f.function for f in translated.frames if f is not None}
        assert names == {None, "main"}

    def test_compiler_made_names_are_hidden(self) -> None:
        """A `for` loop's end value lives in a `$` name, which is hidden; `i` is not."""
        translated = translate(RANGE)
        main = next(f for f in translated.frames if f is not None)
        hidden = {slot.name: slot.hidden for slot in main.slots}
        assert hidden == {"$for_limit_0": True, "i": False}

    def test_a_pebble_name_is_a_letter_or_underscore_then_letters_digits_or_underscores(
        self,
    ) -> None:
        """Names Pebble can write pass; the compiler's `$` names and empty text do not."""
        assert all(is_pebble_name(name) for name in ("n", "_x", "café", "a1"))
        assert not any(is_pebble_name(name) for name in ("", "$for_limit_0", "1a", "a-b"))


class TestWhichWordsAreReady:
    """The map has one entry per word, None wherever `r7` cannot be trusted."""

    def test_one_entry_per_word(self) -> None:
        """`frames` is exactly as long as the machine code."""
        translated = translate(ADD)
        assert len(translated.frames) == len(translated.program.words)

    @pytest.mark.parametrize("path", CORPUS, ids=lambda path: path.stem)
    def test_only_the_body_of_each_piece_of_code_is_ready(self, path: Path) -> None:
        """None on prologues, return `ret`s, runtime and data; the right code everywhere else."""
        source = path.read_text(encoding="utf-8")
        translated = translate(source)
        expected = _expected_frames(source, translated)
        actual = [
            None if frame is None else frame.function or "main" for frame in translated.frames
        ]
        assert actual == expected


class TestTheFramePointerAgrees:
    """Running each corpus program, r7 really does point at the frame the map names."""

    @pytest.mark.parametrize("path", CORPUS, ids=lambda path: path.stem)
    def test_r7_is_the_frame_the_map_says(self, path: Path) -> None:
        """A function's r7 sits just below a return address; main's r7 is the one it made."""
        translated = translate(path.read_text(encoding="utf-8"))
        machine = FastMachine()
        machine.load_program(translated.program.words)
        made = _main_frame_pointer(translated)
        main_frame: int | None = None
        checked = 0
        for _ in range(MAX_STEPS):
            if machine.halted:
                break
            pc = machine.pc
            frame = translated.frames[pc] if pc < len(translated.frames) else None
            r7 = machine.register(FRAME_POINTER)
            if frame is not None:
                checked += 1
                if frame.function is None:
                    assert r7 == main_frame
                else:
                    memory = machine.state().memory
                    back = memory[r7 + 1]
                    assert decode(memory[back - 1]).opcode == Opcode.CALL
            machine.step()
            if pc == made:
                main_frame = machine.register(FRAME_POINTER)
        assert checked > 0
