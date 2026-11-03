"""Check the runtime routines (multiply, divide, print) by running them on the fast engine.

Each test builds a tiny caller (`call` the routine, then `halt`), appends the runtime
assembly, loads the numbers into registers and runs the real machine.
"""

from dataclasses import replace

from hypothesis import given, settings
from hypothesis import strategies as st

from pycpu.assembler import assemble
from pycpu.fast import FastMachine
from pycpu.state import WORD_MASK, MachineState, program_state
from pycpu.translator import RUNTIME, RUNTIME_STACK_WORDS

RAM = 256
STEP_LIMIT = 5000
SIGN_BIT = 0x8000
INT_MIN = -0x8000
INT_MAX = 0x7FFF
R0, R1, R2, R7 = 0, 1, 2, 7


def _program(routine: str) -> tuple[int, ...]:
    """Assemble a caller of `routine` followed by the runtime."""
    return assemble(f"call {routine}\nhalt\n{RUNTIME}", words=RAM).words


MUL = _program("__mul")
DIVMOD = _program("__divmod")
PRINT_INT = _program("__print_int")
MESSAGE = "message"


def _start(words: tuple[int, ...], a: int, b: int) -> MachineState:
    """Return a powered-on state with `a` in r1, `b` in r2 and r7 set to a marker."""
    state = program_state(words, RAM)
    registers = list(state.registers)
    registers[R1] = a & WORD_MASK
    registers[R2] = b & WORD_MASK
    registers[R7] = 0x1234
    return replace(state, registers=tuple(registers))


def _run(words: tuple[int, ...], a: int, b: int) -> tuple[MachineState, int]:
    """Run to the halt; return the final state and the deepest stack use in words."""
    machine = FastMachine(words=RAM)
    machine.load_state(_start(words, a, b))
    deepest = 0
    while machine.step():
        deepest = max(deepest, RAM - machine.state().sp)
        if machine.state().halted:
            break
    return machine.state(), deepest


def _signed(value: int) -> int:
    """Read a 16-bit word as a signed number."""
    return value - (1 << 16) if value & SIGN_BIT else value


def _wrap(value: int) -> int:
    """Wrap any whole number to a signed 16-bit one."""
    return _signed(value & WORD_MASK)


def _print_text_program(text: str) -> tuple[tuple[int, ...], int]:
    """Assemble a caller of `__print_text` with `text` as data; return words and its address."""
    source = f'call __print_text\nhalt\n{RUNTIME}\n{MESSAGE}: .string "{text}"'
    program = assemble(source, words=RAM)
    return program.words, program.labels[MESSAGE]


def printed_number(value: int) -> str:
    """Return the text `__print_int` sends to the output port for `value`."""
    final, _ = _run(PRINT_INT, value, 0)
    assert final.halted
    assert final.halt_code == 0
    return final.output_text


def printed_text(text: str) -> str:
    """Return the text `__print_text` sends to the output port for `text`."""
    words, address = _print_text_program(text)
    final, _ = _run(words, address, 0)
    assert final.halted
    assert final.halt_code == 0
    return final.output_text


def multiply(a: int, b: int) -> int:
    """Return the unsigned 16-bit product the machine computes."""
    final, _ = _run(MUL, a, b)
    assert final.halted
    assert final.halt_code == 0
    return final.registers[R1]


def divmod_(a: int, b: int) -> tuple[int, int]:
    """Return the signed (quotient, remainder) the machine computes."""
    final, _ = _run(DIVMOD, a, b)
    assert final.halted
    assert final.halt_code == 0
    return _signed(final.registers[R1]), _signed(final.registers[R2])


@settings(max_examples=500)
@given(st.integers(0, WORD_MASK), st.integers(0, WORD_MASK))
def test_multiply_matches_python_for_any_two_words(a: int, b: int) -> None:
    """Multiplying any two 16-bit words gives the product wrapped to 16 bits."""
    assert multiply(a, b) == (a * b) & WORD_MASK


def test_multiply_pinned_values() -> None:
    """300 times 300 wraps to 24464, and 65535 times 65535 wraps to 1."""
    assert multiply(300, 300) == 24464  # noqa: PLR2004
    assert multiply(0xFFFF, 0xFFFF) == 1


@settings(max_examples=500)
@given(st.integers(INT_MIN, INT_MAX), st.integers(INT_MIN, INT_MAX).filter(bool))
def test_divmod_matches_python_floor_division(a: int, b: int) -> None:
    """Quotient and remainder match Python's // and %, wrapped to 16 bits."""
    assert divmod_(a, b) == (_wrap(a // b), _wrap(a % b))


def test_divmod_pinned_values() -> None:
    """Negative numbers round down: the worked examples from the docs."""
    assert divmod_(-7, 2) == (-4, 1)
    assert divmod_(7, -2) == (-4, -1)
    assert divmod_(-7, -2) == (3, -1)
    assert divmod_(7, 2) == (3, 1)
    assert divmod_(-32768, -1) == (-32768, 0)
    assert divmod_(-32768, 1) == (-32768, 0)
    assert divmod_(32767, -32768) == (-1, -1)
    assert divmod_(-32768, -32768) == (1, 0)


@settings(max_examples=300)
@given(st.integers(INT_MIN, INT_MAX))
def test_print_int_writes_the_decimal_number_and_a_newline(value: int) -> None:
    """Any signed 16-bit number prints as its decimal text followed by a newline."""
    assert printed_number(value) == f"{value}\n"


def test_print_int_pinned_values() -> None:
    """The edges: zero, minus one, the biggest, the smallest, and exact tens."""
    assert printed_number(0) == "0\n"
    assert printed_number(-1) == "-1\n"
    assert printed_number(INT_MAX) == "32767\n"
    assert printed_number(INT_MIN) == "-32768\n"
    assert printed_number(-10) == "-10\n"
    assert printed_number(-100) == "-100\n"
    assert printed_number(100) == "100\n"


def test_print_int_sends_character_codes() -> None:
    """305 goes out as the codes for '3', '0', '5' and a newline."""
    final, _ = _run(PRINT_INT, 305, 0)
    assert final.output == (51, 48, 53, 10)


def test_print_text_writes_the_text_and_a_newline() -> None:
    """A .string "Hi" prints Hi and a newline."""
    assert printed_text("Hi") == "Hi\n"
    assert printed_text("Hello, PyCPU!") == "Hello, PyCPU!\n"


def test_print_text_of_an_empty_string_is_just_a_newline() -> None:
    """An empty string prints nothing but the newline."""
    assert printed_text("") == "\n"


def _all_programs() -> list[tuple[tuple[int, ...], int, int]]:
    """Return (words, r1, r2) for a spread of calls to every routine."""
    hi_words, hi_address = _print_text_program("Hi")
    return [
        (MUL, 1234, 567),
        (DIVMOD, -1234, 57),
        (DIVMOD, 99, -7),
        (PRINT_INT, -32768, 0),
        (PRINT_INT, 0, 0),
        (hi_words, hi_address, 0),
    ]


def test_routines_keep_r0_and_r7() -> None:
    """r0 stays 0 and r7 (the frame pointer) is untouched by every routine."""
    for words, a, b in _all_programs():
        final, _ = _run(words, a, b)
        assert final.registers[R0] == 0
        assert final.registers[R7] == 0x1234  # noqa: PLR2004


def test_routines_leave_the_stack_as_they_found_it() -> None:
    """After a routine returns, sp is back where it was before the call."""
    for words, a, b in _all_programs():
        final, _ = _run(words, a, b)
        assert final.sp == RAM


def test_runtime_stack_words_covers_the_deepest_use() -> None:
    """The constant is exactly the deepest stack measured across every routine."""
    hi_words, hi_address = _print_text_program("Hi")
    cases = [
        (words, a, b)
        for words in (MUL, DIVMOD)
        for a, b in [(1, 1), (-7, 2), (7, -2), (-32768, -1), (0, 5)]
    ]
    cases += [(PRINT_INT, value, 0) for value in (0, 7, -7, 12345, -12345, -32768, 32767)]
    cases.append((hi_words, hi_address, 0))
    deepest = max(_run(words, a, b)[1] for words, a, b in cases)
    assert deepest == RUNTIME_STACK_WORDS


def test_a_five_digit_negative_number_is_the_deepest_print() -> None:
    """-12345 needs more stack than 12345, and more than any shorter number."""
    depth = {value: _run(PRINT_INT, value, 0)[1] for value in (7, 45, -7, -45, 12345, -12345)}
    assert depth[-12345] == max(depth.values())
    assert depth[-12345] == RUNTIME_STACK_WORDS


def test_runtime_labels_all_start_with_two_underscores() -> None:
    """Runtime labels never clash with generated ones."""
    labels = assemble(f"halt\n{RUNTIME}", words=RAM).labels
    assert labels
    assert all(name.startswith("__") for name in labels)
