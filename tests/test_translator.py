"""Check the translator: Pebble programs in, PyCPU machine code out, run on the fast engine.

Every program that runs here is also run on the real Pebble VM (`pebble.run_source`),
and the two outputs are compared whenever the numbers stay inside 16 bits. The
friendly-error tests take one row of the subset contract each and check the feature
name, the Pebble line and the column.
"""

from dataclasses import replace

import pebble
import pytest

from pycpu.assembler import assemble
from pycpu.fast import FastMachine
from pycpu.isa import Fault
from pycpu.memory import RAM_WORDS
from pycpu.translator import (
    RUNTIME_STACK_WORDS,
    PebbleCPUError,
    PebbleRun,
    TranslatedProgram,
    UnsupportedFeature,
    run_pebble,
    translate,
)
from pycpu.translator.codegen import generate
from pycpu.translator.subset import (
    BITWISE,
    BOOL_OUTSIDE_CONDITIONS,
    DECIMALS,
    DICTIONARIES,
    DIVIDE,
    FUNCTIONS_AS_VALUES,
    LISTS,
    NULL_VALUES,
    NUMBER_RANGE,
    OUTSIDE_VARIABLES,
    POWER,
    STRUCTS,
    TEXT_BRACES,
    TEXT_OUTSIDE_PRINT,
    TOO_BIG,
    TOO_MANY_VARIABLES,
    ZERO_CHARACTER,
    CheckedCode,
    CheckedProgram,
    builtin_function,
    check_program,
)

MAX_LOCALS = 32
TOO_MANY_PRINTS = 1100
BOUNDARY_SEARCH_START = 980
STACK_FOR_ONE_PRINT = 1 + 1 + RUNTIME_STACK_WORDS  # old r7, one slot, the routines
SECOND_LINE = 2
A_FEW_STEPS = 3
SMALLEST = -32768


def run_and_compare(source: str) -> PebbleRun:
    """Run `source` on PyCPU, check it finished cleanly and printed what the Pebble VM prints."""
    run = run_pebble(source)
    assert run.halted
    assert run.fault is None
    assert run.output == pebble.run_source(source)
    return run


def fits(source: str) -> bool:
    """Say whether `source` translates without being refused."""
    try:
        translate(source)
    except UnsupportedFeature:
        return False
    return True


def refusal(source: str) -> UnsupportedFeature:
    """Translate `source`, which must be refused, and return the friendly error."""
    with pytest.raises(UnsupportedFeature) as caught:
        translate(source)
    return caught.value


class TestRunningPebble:
    """Straight-line Pebble programs print the same on PyCPU as on the Pebble VM."""

    def test_printing_one_prints_one(self) -> None:
        """`print(1)` prints 1 and a newline."""
        assert run_and_compare("print(1)").output == "1\n"

    def test_a_variable_can_be_changed_and_printed(self) -> None:
        """`x = x * 4 - 5` with x = 3 leaves 7."""
        source = "let x = 3\nx = x * 4 - 5\nprint(x)"
        assert run_and_compare(source).output == "7\n"

    def test_floor_division_and_modulo_round_down(self) -> None:
        """`-7 // 2` is -4 and `-7 % 2` is 1, whether Pebble or the CPU works it out."""
        assert run_and_compare("print(-7 // 2)\nprint(-7 % 2)").output == "-4\n1\n"
        source = "let a = -7\nprint(a // 2)\nprint(a % 2)"
        assert run_and_compare(source).output == "-4\n1\n"

    def test_text_is_printed_as_it_is(self) -> None:
        """`print("hello")` prints hello."""
        assert run_and_compare('print("hello")').output == "hello\n"

    def test_tricky_text_survives_the_trip_through_the_assembler(self) -> None:
        """Quotes, backslashes, tabs, semicolons and empty text print exactly."""
        source = 'print("say \\"hi\\" ; a\\\\b\\tc")\nprint("")\nprint("café")'
        run_and_compare(source)

    def test_the_same_text_twice_is_stored_once(self) -> None:
        """Two prints of the same text share one copy in memory."""
        program = translate('print("hi")\nprint("hi")')
        assert program.assembly.count('.string "hi"') == 1
        run_and_compare('print("hi")\nprint("hi")')

    def test_negating_a_variable_flips_its_sign(self) -> None:
        """`-a` with a = 5 is -5, and the smallest number prints too."""
        assert run_and_compare("let a = 5\nprint(-a)").output == "-5\n"
        assert run_and_compare(f"print({SMALLEST})").output == f"{SMALLEST}\n"

    def test_every_operator_agrees_with_the_pebble_vm(self) -> None:
        """Adding, subtracting, multiplying, dividing and remainders all match the VM."""
        source = (
            "let a = 123\nlet b = -45\n"
            "print(a + b)\nprint(a - b)\nprint(a * b)\nprint(a // b)\nprint(a % b)\n"
            "print(b // a)\nprint(b % a)\nprint(b * b - a)"
        )
        run_and_compare(source)

    def test_an_expression_statement_is_worked_out_and_thrown_away(self) -> None:
        """A bare `y + 1` line changes nothing and prints nothing."""
        assert run_and_compare("let y = 2\ny + 1\nprint(y)").output == "2\n"

    def test_a_type_note_on_a_number_is_fine(self) -> None:
        """`let x: Int = 3` makes no code for the `Int` check, and works."""
        assert run_and_compare("let x: Int = 3\nprint(x)").output == "3\n"

    def test_an_empty_program_halts_quietly(self) -> None:
        """A program with nothing in it prints nothing."""
        assert run_and_compare("").output == ""

    def test_adding_past_the_top_wraps_round_to_the_bottom(self) -> None:
        """32767 + 1 is -32768 on the CPU (the VM, with no 16-bit limit, says 32768)."""
        run = run_pebble("let big = 32767\nprint(big + 1)")
        assert run.output == "-32768\n"
        assert pebble.run_source("let big = 32767\nprint(big + 1)") == "32768\n"
        assert run.halted
        assert run.fault is None

    def test_a_sum_of_two_numbers_is_done_by_pebbles_compiler(self) -> None:
        """`print(32767 + 1)` reaches us as the single number 32768, which is too big."""
        error = refusal("print(32767 + 1)")
        assert error.feature == NUMBER_RANGE
        assert (error.line, error.column) == (1, 7)

    def test_a_sum_of_plain_numbers_reaches_the_cpu_as_its_answer(self) -> None:
        """`print(1 + 2 * 3)` is just `LOAD_CONST 7`: no multiply is written."""
        assembly = translate("print(1 + 2 * 3)").assembly
        assert "; line 1: LOAD_CONST 7" in assembly
        assert "MULTIPLY" not in assembly
        assert run_and_compare("print(1 + 2 * 3)").output == "7\n"

    def test_a_constant_power_is_done_by_pebbles_compiler(self) -> None:
        """`print(2 ** 3)` reaches us as the single number 8, so it runs."""
        assert run_and_compare("print(2 ** 3)").output == "8\n"

    @pytest.mark.parametrize("statement", ["true", "false", "1 < 2", "null"])
    def test_a_value_nobody_uses_is_worked_out_and_dropped(self, statement: str) -> None:
        """`true`, `false`, a folded comparison and `null` alone on a line are fine."""
        source = f"print(1)\n{statement}\nprint(2)"
        assert run_and_compare(source).output == "1\n2\n"

    def test_running_out_of_steps_stops_without_halting(self) -> None:
        """With only a few steps allowed, the run stops early and says so."""
        run = run_pebble("print(1)", max_steps=A_FEW_STEPS)
        assert run.steps == A_FEW_STEPS
        assert not run.halted
        assert run.fault is None
        assert run.line is None

    def test_dividing_by_zero_faults_on_the_dividing_line(self) -> None:
        """`5 // z` with z = 0 stops the machine with DIVIDE_BY_ZERO on line 2."""
        run = run_pebble("let z = 0\nprint(5 // z)\nprint(1)")
        assert run.halted
        assert run.fault is Fault.DIVIDE_BY_ZERO
        assert run.line == SECOND_LINE
        assert run.output == ""
        with pytest.raises(pebble.PebbleError, match="line 2"):
            pebble.run_source("let z = 0\nprint(5 // z)\nprint(1)")

    def test_a_remainder_by_zero_faults_too(self) -> None:
        """`5 % z` with z = 0 also stops with DIVIDE_BY_ZERO."""
        assert run_pebble("let z = 0\nprint(5 % z)").fault is Fault.DIVIDE_BY_ZERO


class TestTheTranslatedProgram:
    """`translate` gives assembly that assembles, with a Pebble line for every word."""

    def test_main_starts_at_address_zero_and_end_closes_the_text(self) -> None:
        """`__main` is at 0 and the assembly ends with `__end:`."""
        program = translate("print(1)")
        assert isinstance(program, TranslatedProgram)
        assert program.program.labels["__main"] == 0
        assert program.assembly.rstrip().endswith("__end:")
        assert program.program.labels["__end"] == len(program.program.words)

    def test_every_word_has_a_pebble_line(self) -> None:
        """There is one entry in `pebble_lines` per machine word."""
        program = translate("let x = 3\nprint(x)")
        assert len(program.pebble_lines) == len(program.program.words)

    def test_the_words_of_a_one_line_program_all_belong_to_line_one(self) -> None:
        """Everything before the runtime comes from line 1; the runtime belongs to no line."""
        program = translate("print(1)")
        runtime_start = program.program.labels["__mul"]
        assert set(program.pebble_lines[:runtime_start]) == {1}
        assert set(program.pebble_lines[runtime_start:]) == {None}

    def test_each_word_belongs_to_the_line_that_made_it(self) -> None:
        """A two-line program's words go to line 1, then to line 2, in order."""
        program = translate("let x = 3\nprint(x)")
        main = [line for line in program.pebble_lines if line is not None]
        assert main == sorted(main)
        assert set(main) == {1, 2}

    def test_line_at_answers_none_outside_the_program(self) -> None:
        """Asking about an address past the end gives None."""
        program = translate("print(1)")
        assert program.line_at(0) == 1
        assert program.line_at(len(program.program.words)) is None
        assert program.line_at(-1) is None

    def test_the_assembly_names_each_pebble_instruction(self) -> None:
        """A reader can find every Pebble instruction as a comment in the assembly."""
        assembly = translate("let x = 3\nprint(x * 2)").assembly
        for note in ("; line 1: LOAD_CONST 3", "; line 1: STORE_NAME x", "; line 2: MULTIPLY"):
            assert note in assembly

    def test_a_frame_with_too_little_room_halts_with_stack_overflow(self) -> None:
        """If the stack starts just above the program, the prologue refuses to start."""
        program = translate("let x = 3\nprint(x)").program
        machine = FastMachine()
        machine.load_program(program.words)
        machine.load_state(replace(machine.state(), sp=program.labels["__end"] + 1))
        machine.run(100)
        assert machine.state().halted
        assert machine.state().halt_code == Fault.STACK_OVERFLOW
        assert machine.state().output == ()


class TestFriendlyErrors:
    """Each thing outside the subset is refused by name, at its Pebble line and column."""

    @pytest.mark.parametrize(
        ("source", "feature", "line", "column"),
        [
            ("let a = 7\nprint(a / 2)", DIVIDE, 2, 9),
            ("print(7 / 2)", DECIMALS, 1, 7),
            ("let x = 1.5", DECIMALS, 1, 9),
            ("let a = 2\nprint(a ** 3)", POWER, 2, 9),
            ("let a = 1\nprint(a & 2)", BITWISE, 2, 9),
            ("let a = 1\nprint(~a)", BITWISE, 2, 7),
            ('print("a{1}")', TEXT_BRACES, 1, 7),
            ('let s = "hi"', TEXT_OUTSIDE_PRINT, 1, 9),
            ("let a = [1]", LISTS, 1, 9),
            ('let d = {"a": 1}', DICTIONARIES, 1, 9),
            ('print(len("ab"))', builtin_function("len"), 1, 7),
            ("let x = 40000", NUMBER_RANGE, 1, 9),
            ("let b = true", BOOL_OUTSIDE_CONDITIONS, 1, 9),
            ("print(true)", BOOL_OUTSIDE_CONDITIONS, 1, 7),
            ("print(1 + true)", BOOL_OUTSIDE_CONDITIONS, 1, 11),
            ("print(null)", NULL_VALUES, 1, 7),
            ("let x = null", NULL_VALUES, 1, 9),
            ("print(1 + null)", NULL_VALUES, 1, 11),
            ("struct P { x: Int }\nlet p = P(1)", STRUCTS, 2, 9),
            ("fn f() { print(1) }\nlet g = f", FUNCTIONS_AS_VALUES, 2, 9),
            ("let b: Bool = true", "the Bool type", 1, 1),
            ("let g = 1\nfn f() { return g }\nprint(1)", OUTSIDE_VARIABLES, 2, 17),
            ('print("a\\0b")', ZERO_CHARACTER, 1, 7),
        ],
    )
    def test_an_unsupported_feature_is_named_with_its_place(
        self, source: str, feature: str, line: int, column: int
    ) -> None:
        """The error names the feature, the line and the column."""
        error = refusal(source)
        assert (error.feature, error.line, error.column) == (feature, line, column)
        assert isinstance(error, PebbleCPUError)

    def test_the_message_reads_as_a_sentence(self) -> None:
        """A plural feature says "are not", a singular one says "is not"."""
        assert str(refusal("let a = [1]")) == (
            "lists are not supported on PyCPU yet at line 1, column 9"
        )
        assert str(refusal('print(len("ab"))')) == (
            "the built-in function len() is not supported on PyCPU yet at line 1, column 7"
        )

    def test_the_first_problem_in_the_source_wins(self) -> None:
        """Of two problems, the one nearer the top of the program is reported."""
        assert refusal('let s = "hi"\nlet x = 1.5').feature == TEXT_OUTSIDE_PRINT
        # The list starts at column 9; the `/` inside it at column 12 comes later.
        error = refusal("let x = 1\nlet a = [x / 2]")
        assert (error.feature, error.column) == (LISTS, 9)

    def test_more_variables_than_the_frame_can_reach_are_refused(self) -> None:
        """A 33rd variable is one too many for a 6-bit memory offset."""
        names = [f"v{n}" for n in range(MAX_LOCALS + 1)]
        source = "\n".join(f"let {name} = 1" for name in names)
        error = refusal(source)
        assert (error.feature, error.line) == (TOO_MANY_VARIABLES, MAX_LOCALS + 1)
        run_and_compare("\n".join(f"let {name} = 1" for name in names[:MAX_LOCALS]))

    def test_characters_too_big_for_a_word_are_refused(self) -> None:
        """An emoji needs more than 16 bits, so it cannot be one word of text."""
        assert refusal('print("\U0001f600")').line == 1

    def test_a_program_too_long_for_memory_is_refused(self) -> None:
        """Over a thousand prints make more machine code than 4,096 words can hold."""
        error = refusal("print(1)\n" * TOO_MANY_PRINTS)
        assert error.feature == TOO_BIG
        assert error.line is None
        assert str(error) == f"{TOO_BIG} are not supported on PyCPU yet"

    def test_the_biggest_program_that_fits_still_runs(self) -> None:
        """At the edge, one more print leaves no room for the stack, and is refused."""
        prints = BOUNDARY_SEARCH_START
        while fits("print(1)\n" * (prints + 1)):
            prints += 1
        error = refusal("print(1)\n" * (prints + 1))
        assert error.feature == TOO_BIG
        program = translate("print(1)\n" * prints)
        end = program.program.labels["__end"]
        assert end + STACK_FOR_ONE_PRINT <= RAM_WORDS
        source = "print(1)\n" * prints
        assert run_and_compare(source).output == "1\n" * prints
        # The refused program's code alone would fit: it was the stack room that ran out.
        refused = generate(check_program(pebble.compile_source(source + "print(1)\n").compiled))
        assert len(assemble(refused.text).words) < RAM_WORDS

    def test_a_function_that_is_never_called_is_fine(self) -> None:
        """Defining a function is allowed; main still runs."""
        assert run_and_compare("fn f(a) { return a }\nprint(1)").output == "1\n"

    def test_calling_your_own_function_is_refused_for_now(self) -> None:
        """Calls to user functions are not translated yet, and say so politely."""
        assert refusal("fn f(a) { return a }\nprint(f(2))").line == SECOND_LINE

    def test_a_problem_inside_a_function_is_found_too(self) -> None:
        """A function body is checked even if nobody calls it."""
        error = refusal('fn f() { return "hi" }\nprint(1)')
        assert (error.feature, error.line, error.column) == (TEXT_OUTSIDE_PRINT, 1, 17)

    def test_a_comparison_of_two_numbers_is_folded_into_true(self) -> None:
        """`print(1 < 2)` reaches us as `true`, which cannot be printed on PyCPU."""
        assert refusal("print(1 < 2)").feature == BOOL_OUTSIDE_CONDITIONS

    def test_an_instruction_the_checker_wrongly_lets_through_is_a_loud_bug(self) -> None:
        """If the code generator meets an instruction it has no cards for, it says so."""
        code = pebble.compile_source("let a = 1\nprint(a < 2)").compiled.main
        unchecked = CheckedCode("main", code, ("a",), frozenset(), deepest=2)
        with pytest.raises(PebbleCPUError, match="translator bug: no code for LESS_THAN"):
            generate(CheckedProgram(unchecked, {}))

    def test_a_pebble_mistake_is_passed_through_unchanged(self) -> None:
        """A syntax error is Pebble's own error, not ours."""
        with pytest.raises(pebble.PebbleError) as caught:
            translate("print(")
        assert not isinstance(caught.value, PebbleCPUError)
