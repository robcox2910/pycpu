"""Check Pebble functions on PyCPU: calls, real stack frames, returns and recursion.

Every program that runs here is also run on Pebble's own VM (`pebble.run_source`) and
the outputs are compared. Programs the translator refuses say in a comment what the VM
does with them instead.
"""

import re
from dataclasses import replace

import pebble
import pytest
from hypothesis import given
from hypothesis import strategies as st

from pycpu.assembler import OFF6_MAX
from pycpu.fast import FastMachine
from pycpu.isa import Fault, Opcode, encode
from pycpu.memory import RAM_WORDS
from pycpu.translator import PebbleRun, UnsupportedFeature, run_pebble, translate
from pycpu.translator.codegen import RETURN_ADDRESS_WORDS, frame_words, function_label
from pycpu.translator.runtime import RUNTIME_STACK_WORDS
from pycpu.translator.subset import (
    BOOL_OUTSIDE_CONDITIONS,
    FUNCTIONS_AS_VALUES,
    MAX_PARAMETERS,
    MAX_VARIABLES,
    NULL_USED,
    OUTSIDE_VARIABLES,
    TEXT_OUTSIDE_PRINT,
    TOO_MANY_PARAMETERS,
    TOO_MANY_VARIABLES,
    Kind,
    check_program,
)

FACTORIAL = """fn fact(n) {
    if n <= 1 {
        return 1
    }
    return n * fact(n - 1)
}
"""
ENDLESS = "fn f(n) {\n    return f(n + 1)\n}\nprint(f(0))"
ENDLESS_STEPS = 200_000
SECOND_LINE = 2
THIRD_LINE = 3
FOURTH_LINE = 4
FIFTH_LINE = 5
TENTH_LINE = 10
# Each endless call leaves 3 words: its argument, the return address and the old r7.
WORDS_PER_ENDLESS_CALL = 3
ROOM_SEARCH = 40
FRAMES_TO_MEASURE = 3
A_FEW_STEPS = 3
ADD3_FRAME = 4090
_LABEL_SUFFIXES = ("", "_room", "_0", "_12", "_yes_3", "_go_on_4", "_divisor_ok_5")


def run_and_compare(source: str) -> PebbleRun:
    """Run `source` on PyCPU, check it finished cleanly and printed what the Pebble VM prints."""
    run = run_pebble(source)
    assert run.halted
    assert run.fault is None
    assert run.output == pebble.run_source(source)
    return run


def refusal(source: str) -> UnsupportedFeature:
    """Translate `source`, which must be refused, and return the friendly error."""
    with pytest.raises(UnsupportedFeature) as caught:
        translate(source)
    return caught.value


class TestCallingFunctions:
    """Calls to your own functions print the same on PyCPU as on the Pebble VM."""

    def test_double_in_a_loop_prints_six_four_two(self) -> None:
        """The program from the Pebble research calls `double` three times."""
        source = (
            "fn double(n) {\n    return n * 2\n}\nlet i = 3\n"
            "while i > 0 {\n    print(double(i))\n    i = i - 1\n}"
        )
        assert run_and_compare(source).output == "6\n4\n2\n"

    def test_factorial_of_seven_is_5040(self) -> None:
        """Recursion: `fact` calls itself six times on the way down."""
        assert run_and_compare(FACTORIAL + "print(fact(7))").output == "5040\n"

    def test_three_parameters_keep_their_order(self) -> None:
        """The first argument lands in the first parameter, however many there are."""
        source = "fn digits(a, b, c) {\n    return a * 100 + b * 10 + c\n}\nprint(digits(1, 2, 3))"
        assert run_and_compare(source).output == "123\n"
        run_and_compare("fn f(a, b, c) {\n    return a - b - c\n}\nprint(f(10, 3, 2))")

    def test_a_default_argument_is_filled_in_by_the_caller(self) -> None:
        """Pebble compiles a missing argument's default at the call, so the call is the same."""
        assert run_and_compare("fn f(a, b = 5) {\n    return a - b\n}\nprint(f(1))").output == (
            "-4\n"
        )

    def test_two_functions_with_their_own_variables_keep_both_frames(self) -> None:
        """A function calling a function: each one's variables survive the other's work."""
        source = """fn g(x) {
    let t = x + 1
    let u = t * 2
    return u
}
fn f(a) {
    let s = a * 3
    let r = g(s)
    return s * 100 + r * 10 + a
}
let m = 2
let n = f(m)
print(n)
print(m)"""
        assert run_and_compare(source).output == "742\n2\n"

    def test_a_chain_of_calls_comes_back_in_the_right_order(self) -> None:
        """`a` calls `b` calls `c`: three frames on the pile, unwound one at a time.

        Pebble only lets a function call ones defined above it (or itself), so two
        functions can never call each other.
        """
        source = """fn c(x) {
    return x + 1
}
fn b(x) {
    let y = c(x) * 10
    return y + c(y)
}
fn a(x) {
    return b(x) - x
}
print(a(4))
print(a(-7))"""
        assert run_and_compare(source).output == "97\n-112\n"

    def test_a_function_with_no_return_works_as_a_statement(self) -> None:
        """A function that only prints gives back null, which a statement throws away."""
        source = 'fn hello(n) {\n    print(n)\n    print("hi")\n}\nhello(7)\nhello(8)'
        assert run_and_compare(source).output == "7\nhi\n8\nhi\n"

    def test_a_function_that_sometimes_returns_works_as_a_statement(self) -> None:
        """Its maybe-a-number answer is fine to throw away."""
        source = "fn f(a) {\n    if a > 0 {\n        return 1\n    }\n}\nf(1)\nf(0)\nprint(2)"
        assert run_pebble(source).output == "2\n"
        # Pebble's VM crashes when `f(0)` runs past the end of `f`; with `f(1)` alone it agrees.
        with pytest.raises(IndexError):
            pebble.run_source(source)
        run_and_compare(source.replace("f(0)\n", ""))

    def test_a_function_with_no_parameters_needs_no_tidying(self) -> None:
        """With no arguments to drop, the call is just `call` and `push r1`."""
        source = "fn seven() {\n    return 7\n}\nprint(seven() + seven())"
        assert run_and_compare(source).output == "14\n"
        lines = translate(source).assembly.splitlines()
        call = lines.index("    ; line 4: CALL seven")
        assert [line.split(";")[0].strip() for line in lines[call + 1 : call + 3]] == [
            "call __fn_seven",
            "push r1",
        ]

    def test_a_function_is_called_only_when_the_call_runs(self) -> None:
        """Defining a function prints nothing; calling it in a branch not taken does nothing."""
        source = "fn f() {\n    print(1)\n}\nlet a = 0\nif a {\n    f()\n}\nprint(2)"
        assert run_and_compare(source).output == "2\n"

    def test_a_function_can_store_to_a_name_that_main_also_uses(self) -> None:
        """Inside a function, a stored name is its own variable; main's stays the same."""
        source = "let g = 1\nfn f() {\n    g = 2\n    return g\n}\nprint(f())\nprint(g)"
        assert run_and_compare(source).output == "2\n1\n"

    def test_nested_functions_without_shared_variables_work(self) -> None:
        """A function defined inside another, using none of its variables, is plain."""
        source = "fn outer(x) {\n    fn inner(y) {\n        return y + 1\n    }\n"
        source += "    return inner(x)\n}\nprint(outer(4))"
        assert run_and_compare(source).output == "5\n"

    def test_the_greatest_number_of_parameters_and_variables_fit(self) -> None:
        """29 parameters and 32 variables in one function reach every slot."""
        params = [f"p{n}" for n in range(MAX_PARAMETERS)]
        names = [f"v{n}" for n in range(MAX_VARIABLES)]
        body = "\n".join(f"    let {name} = {n}" for n, name in enumerate(names))
        source = (
            f"fn f({', '.join(params)}) {{\n{body}\n"
            f"    return p0 * 100 + p{MAX_PARAMETERS - 1} + v{MAX_VARIABLES - 1}\n}}\n"
            f"print(f({', '.join(str(n) for n in range(1, MAX_PARAMETERS + 1))}))"
        )
        assert run_and_compare(source).output == f"{100 + MAX_PARAMETERS + MAX_VARIABLES - 1}\n"
        assert f"[r7+{OFF6_MAX - 1}]" in translate(source).assembly


class TestReturnKinds:
    """The checker works out what each function gives back, across every function."""

    def kinds(self, source: str) -> dict[str, frozenset[Kind]]:
        """Return what each function in `source` may give back."""
        checked = check_program(pebble.compile_source(source).compiled)
        return {name: code.returns for name, code in checked.functions.items()}

    def test_a_number_on_every_path_is_a_number(self) -> None:
        """`fact` returns 1 or a product: always a number, recursion included."""
        assert self.kinds(FACTORIAL) == {"fact": frozenset({Kind.INT})}

    def test_falling_off_the_end_gives_null(self) -> None:
        """No return at all, or a return on one path only, adds null."""
        source = "fn f() {\n    print(1)\n}\nfn g(a) {\n    if a {\n        return 1\n    }\n}"
        assert self.kinds(source) == {
            "f": frozenset({Kind.NULL}),
            "g": frozenset({Kind.INT, Kind.NULL}),
        }

    def test_null_flows_back_through_a_call(self) -> None:
        """`m` returns `n()`, and `n` gives back null, so `m` maybe gives a number."""
        source = (
            "fn n() {\n    print(1)\n}\n"
            "fn m(a) {\n    if a {\n        return 1\n    }\n    return n()\n}\n"
        )
        assert self.kinds(source)["m"] == frozenset({Kind.INT, Kind.NULL})
        error = refusal(source + "print(m(1))")
        assert (error.feature, error.line) == (NULL_USED, TENTH_LINE)

    def test_a_second_round_finds_a_maybe_inside_recursion(self) -> None:
        """At first `q(n - 1)` looks like it never comes back; round two learns it may be null.

        (The VM crashes with an IndexError when `q(0)` runs past the end of `q`.)
        """
        source = "fn q(n) {\n    if n > 0 {\n        return q(n - 1) * 2\n    }\n}"
        error = refusal(source)
        assert (error.feature, error.line, error.column) == (NULL_USED, THIRD_LINE, 16)

    def test_recursion_that_only_ever_ends_in_null_gives_null(self) -> None:
        """`h` returns `h(...)` or falls off the end: nothing but null ever comes back."""
        source = "fn h(n) {\n    if n > 0 {\n        return h(n - 1)\n    }\n}\nh(3)"
        assert self.kinds(source) == {"h": frozenset({Kind.NULL})}
        run = run_pebble(source)
        assert (run.output, run.fault) == ("", None)
        # Pebble's VM crashes here when `h(0)` runs past the end of `h`.
        with pytest.raises(IndexError):
            pebble.run_source(source)

    def test_a_function_that_never_returns_at_all_gives_nothing(self) -> None:
        """Endless recursion never comes back, so its answer is never really used."""
        assert self.kinds(ENDLESS) == {"f": frozenset()}


class TestFunctionErrors:
    """Functions outside the subset are refused by name, at the right place."""

    def test_using_the_answer_of_a_function_that_never_returns_a_number_is_refused(
        self,
    ) -> None:
        """`print(f())` where `f` gives back null is refused; the VM prints `null`."""
        error = refusal("fn f() {\n    print(1)\n}\nprint(f())")
        assert (error.feature, error.line, error.column) == (NULL_USED, 4, 7)
        assert str(error) == (
            "using the result of a function that does not always return a number "
            "is not supported on PyCPU yet at line 4, column 7"
        )

    def test_using_the_answer_of_a_function_that_returns_on_one_path_is_refused(self) -> None:
        """`f(0)` falls off the end; the VM crashes with an IndexError on `print(f(0))`."""
        source = "fn f(a) {\n    if a {\n        return 1\n    }\n}\nlet x = f(1) + 1"
        error = refusal(source)
        assert (error.feature, error.line, error.column) == (NULL_USED, 6, 9)

    def test_returning_a_maybe_is_refused_too(self) -> None:
        """Passing a maybe-a-number along with `return` is still using it."""
        source = "fn f(a) {\n    if a {\n        return 1\n    }\n}\nfn g() {\n    return f(1)\n}"
        assert refusal(source).feature == NULL_USED

    def test_a_variable_from_main_is_out_of_reach(self) -> None:
        """A function only sees its own names; the VM says "Undefined variable 'g'"."""
        error = refusal("let g = 1\nfn f() {\n    return g\n}\nprint(f())")
        assert (error.feature, error.line) == (OUTSIDE_VARIABLES, THIRD_LINE)

    def test_a_closure_is_refused(self) -> None:
        """A function using its parent's variable is a closure; the VM prints 1."""
        source = "fn outer() {\n    let a = 1\n    fn inner() {\n        return a\n    }\n"
        source += "    return inner()\n}\nprint(outer())"
        error = refusal(source)
        assert (error.feature, error.line) == (FUNCTIONS_AS_VALUES, SECOND_LINE)

    def test_a_function_stored_in_a_variable_is_refused(self) -> None:
        """A function's name used as a value is refused; the VM stores the function."""
        assert refusal("fn f() {\n    return 1\n}\nlet g = f").feature == FUNCTIONS_AS_VALUES

    def test_thirty_parameters_are_too_many(self) -> None:
        """Parameter 0 of 30 would sit at [r7+31], past what we allow for a frame."""
        params = ", ".join(f"p{n}" for n in range(MAX_PARAMETERS + 1))
        error = refusal(f"fn f({params}) {{\n    return p0\n}}")
        assert (error.feature, error.line) == (TOO_MANY_PARAMETERS, SECOND_LINE)
        assert str(error).startswith("more than 29 parameters are not supported")

    def test_too_many_parameters_with_no_line_names_the_function(self) -> None:
        """An empty body has no line to point at, so the message names the function."""
        params = ", ".join(f"p{n}" for n in range(MAX_PARAMETERS + 1))
        error = refusal(f"fn wide({params}) {{\n}}")
        assert (error.feature, error.line) == (f"{TOO_MANY_PARAMETERS} (in wide)", None)
        assert str(error) == "more than 29 parameters (in wide) are not supported on PyCPU yet"

    def test_thirty_three_variables_in_a_function_are_too_many(self) -> None:
        """The 33rd variable of a function has no slot left below r7."""
        body = "\n".join(f"    let v{n} = {n}" for n in range(MAX_VARIABLES + 1))
        error = refusal(f"fn f() {{\n{body}\n    return v0\n}}")
        assert (error.feature, error.line) == (TOO_MANY_VARIABLES, MAX_VARIABLES + 2)

    @pytest.mark.parametrize(
        ("argument", "feature"),
        [("1 < 2", BOOL_OUTSIDE_CONDITIONS), ('"hi"', TEXT_OUTSIDE_PRINT)],
    )
    def test_an_argument_must_be_a_number(self, argument: str, feature: str) -> None:
        """True/false and text cannot be passed: a parameter is a number slot."""
        error = refusal(f"fn f(a) {{\n    return a\n}}\nprint(f({argument}))")
        assert (error.feature, error.line) == (feature, FOURTH_LINE)


class TestFramesAndTheStack:
    """Calls build real frames, and endless recursion never tramples the program."""

    def test_the_frame_of_add3_matches_the_picture_in_the_doc(self) -> None:
        """The doc's addresses: arguments 4094-4092, return address, old r7 at r7, then `t`."""
        source = "fn add3(a, b, c) {\n    let t = a + b + c\n    return t\n}\n"
        source += "print(add3(10, 20, 30))"
        translated = translate(source)
        lines = translated.assembly.splitlines()
        for slot, name in (("[r7+4]", "a"), ("[r7+3]", "b"), ("[r7+2]", "c"), ("[r7-1]", "t")):
            assert any(slot in line and line.endswith(f"r1 = {name}") for line in lines)
        labels = translated.program.labels
        machine = FastMachine()
        machine.load_program(translated.program.words)
        while machine.state().pc != labels["__fn_add3_room"]:
            machine.step()
        machine.run(A_FEW_STEPS)  # push r7, getsp r7, push r0 (t = 0)
        state = machine.state()
        assert state.registers[7] == ADD3_FRAME
        main_top = RAM_WORDS - 1
        return_address = state.memory[ADD3_FRAME + 1]
        assert labels["__main"] < return_address < labels["__fn_add3"]
        assert state.memory[ADD3_FRAME - 1 :] == (
            0,  # t, at [r7-1]
            main_top,  # main's r7, at [r7]
            return_address,  # at [r7+1]
            30,  # c, at [r7+2]
            20,  # b
            10,  # a, at [r7+4]
            0,  # main's own old r7
        )

    def test_endless_recursion_ends_in_stack_overflow_at_a_pebble_line(self) -> None:
        """The prologue's room check stops the machine inside `f`, on its first line."""
        run = run_pebble(ENDLESS, max_steps=ENDLESS_STEPS)
        assert run.halted
        assert run.fault is Fault.STACK_OVERFLOW
        assert run.line == SECOND_LINE
        assert run.output == ""

    def test_endless_recursion_leaves_every_word_of_code_and_text_unchanged(self) -> None:
        """Memory below `__end` is exactly the loaded program when the machine stops."""
        source = 'fn f(n) {\n    print("deeper")\n    return f(n + 1)\n}\nprint(f(0))'
        program = translate(source).program
        end = program.labels["__end"]
        machine = FastMachine()
        machine.load_program(program.words)
        loaded = machine.state().memory[:end]
        lowest = machine.state().sp
        while machine.step():
            lowest = min(lowest, machine.state().sp)
        state = machine.state()
        assert state.halt_code == Fault.STACK_OVERFLOW
        assert state.memory[:end] == loaded
        assert lowest >= end
        assert "".join(map(chr, state.output)).count("deeper") > 1

    def test_each_endless_call_takes_three_words(self) -> None:
        """The doc's figure: an argument, a return address and an old r7 per call."""
        program = translate(ENDLESS).program
        machine = FastMachine()
        machine.load_program(program.words)
        entry = program.labels["__fn_f_room"]
        frames: list[int] = []
        while machine.step() and len(frames) < FRAMES_TO_MEASURE:
            if machine.state().pc == entry:
                frames.append(machine.state().sp)
        assert frames[0] - frames[1] == frames[1] - frames[2] == WORDS_PER_ENDLESS_CALL

    def test_the_room_check_counts_the_return_address_of_a_call(self) -> None:
        """A call's return address fits in the room the caller set aside for routines."""
        assert RUNTIME_STACK_WORDS >= RETURN_ADDRESS_WORDS
        checked = check_program(pebble.compile_source(FACTORIAL).compiled).functions["fact"]
        assert frame_words(checked) == 1 + checked.deepest + RUNTIME_STACK_WORDS

    def test_no_starting_stack_lets_a_call_write_into_the_program(self) -> None:
        """Start the stack just above `__end`, nearer and nearer: it finishes or overflows cleanly."""
        source = (
            FACTORIAL + "fn twice(a) {\n    let b = fact(a)\n    return b + b\n}\nprint(twice(3))"
        )
        program = translate(source).program
        end = program.labels["__end"]
        outcomes: set[int] = set()
        for room in range(1, ROOM_SEARCH):
            machine = FastMachine()
            machine.load_program(program.words)
            loaded = machine.state().memory[:end]
            machine.load_state(replace(machine.state(), sp=end + room))
            machine.run(10_000)
            state = machine.state()
            assert state.halted
            assert state.memory[:end] == loaded
            assert state.halt_code in {0, Fault.STACK_OVERFLOW}
            if state.halt_code == 0:
                assert "".join(map(chr, state.output)) == "12\n"
            outcomes.add(state.halt_code)
        assert outcomes == {0, Fault.STACK_OVERFLOW}


class TestFunctionLabels:
    """Every function gets labels that are safe for the assembler and never clash."""

    @pytest.mark.parametrize(
        ("name", "label"),
        [
            ("double", "__fn_double"),
            ("is_even", "__fn_is__even"),
            ("café", "__fn_caf_xe9_"),
            ("_", "__fn___"),
        ],
    )
    def test_a_name_becomes_a_label(self, name: str, label: str) -> None:
        """Letters and digits stay; `_` doubles; anything else becomes its hex number."""
        assert function_label(name) == label

    @given(
        st.lists(
            st.text(st.characters(categories=("L", "Nd")) | st.sampled_from("_xr0"), min_size=1),
            min_size=2,
            max_size=2,
            unique=True,
        ),
        st.sampled_from(_LABEL_SUFFIXES),
        st.sampled_from(_LABEL_SUFFIXES),
    )
    def test_two_different_names_never_share_a_label(
        self, names: list[str], first: str, second: str
    ) -> None:
        """Whatever the names, no label of one function equals a label of another."""
        one, two = names
        assert function_label(one) + first != function_label(two) + second
        assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", function_label(one), flags=re.ASCII)

    def test_awkward_names_that_look_like_labels_still_run(self) -> None:
        """`f`, `f_room`, `f_1` and `café` would clash if their names were used as they are."""
        source = """fn f(a) {
    if a {
        return 1
    }
    return 2
}
fn f_room() {
    return 3
}
fn f_1() {
    return 4
}
fn café() {
    return 5
}
print(f(0) + f_room() * 10 + f_1() * 100 + café() * 1000)"""
        assert run_and_compare(source).output == "5432\n"


class TestTheSourceMap:
    """Every word of a function points at the right Pebble line."""

    def test_a_prologue_belongs_to_the_functions_first_line(self) -> None:
        """The room check and frame of `fact` map to its first line with code: line 2."""
        translated = translate(FACTORIAL + "print(fact(3))")
        assert translated.line_at(translated.program.labels["__fn_fact"]) == SECOND_LINE

    def test_return_cards_belong_to_the_return_line(self) -> None:
        """The `ret` of each `return` maps to that return's line: 3 and 5 in `fact`."""
        translated = translate(FACTORIAL + "print(fact(3))")
        start = translated.program.labels["__fn_fact"]
        stop = translated.program.labels["__mul"]
        ret = encode(Opcode.RET)
        words = translated.program.words
        rets = [translated.line_at(a) for a in range(start, stop) if words[a] == ret]
        assert rets == [THIRD_LINE, FIFTH_LINE]
