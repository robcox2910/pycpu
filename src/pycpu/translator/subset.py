"""The subset check: a customs desk that looks in every suitcase before it boards.

Before a Pebble program is translated, every one of its bytecode instructions walks past
this desk. Most are waved through. A few carry something PyCPU cannot handle yet, such
as a decimal number, a list or a piece of text stored in a variable, and those are
stopped with a polite note that says what the thing is and which Pebble line it is on.

The desk also does a little bookkeeping that the translator needs later. It plays the
program through without running it, keeping track of what *kind* of thing (a number,
true/false, text, nothing) sits in each slot of Pebble's stack, so it knows, for
example, whether a `print` is printing a number or a piece of text. It notes every
variable a piece of code stores, so each one can get a place in memory, and the deepest
the stack ever gets, so the program can check there is room before it starts.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto

from pebble import CodeObject, CompiledProgram, Instruction, OpCode, SourceLocation

INT_MIN = -32768
INT_MAX = 32767
MAX_VARIABLES = 32
WORD_MAX = 0xFFFF

# The feature names the friendly errors use (see the Pebble Subset Contract).
DIVIDE = "the / operator (it always makes a decimal number; use // for whole numbers)"
DECIMALS = "decimal numbers"
POWER = "the ** operator"
BITWISE = "bitwise operators"
TEXT_BRACES = "text with {} inside it"
TEXT_OUTSIDE_PRINT = "text outside print"
LISTS = "lists"
DICTIONARIES = "dictionaries"
STRUCTS = "structs, classes and enums"
METHODS = "methods like .upper()"
FUNCTIONS_AS_VALUES = "functions used as values"
TRY_CATCH = "try, catch and throw"
GENERATORS = "generators and async"
NUMBER_RANGE = "numbers bigger than 32767 or smaller than -32768"
BOOL_OUTSIDE_CONDITIONS = "true and false outside if and while"
NULL_VALUES = "null values"
NULL_USED = "using the result of a function that does not always return a number"
OUTSIDE_VARIABLES = "variables from outside a function"
TOO_MANY_VARIABLES = f"more than {MAX_VARIABLES} variables in one function"
BIG_CHARACTERS = "emoji and other characters too big for one 16-bit word"
ZERO_CHARACTER = "the \\0 character inside text"
TOO_BIG = "programs too big to fit in memory with room for the stack"
# Stand-ins until later tasks teach the translator these.
CONTROL_FLOW_FOR_NOW = "if, while, comparisons and not (coming soon)"
FUNCTIONS_FOR_NOW = "calls to your own functions (coming soon)"

_SINGULAR = frozenset({TEXT_BRACES, TEXT_OUTSIDE_PRINT, NULL_USED})

_OPCODE_FEATURES: dict[str, str] = {
    OpCode.DIVIDE: DIVIDE,
    OpCode.POWER: POWER,
    **dict.fromkeys(
        (
            OpCode.BIT_AND,
            OpCode.BIT_OR,
            OpCode.BIT_XOR,
            OpCode.BIT_NOT,
            OpCode.LEFT_SHIFT,
            OpCode.RIGHT_SHIFT,
        ),
        BITWISE,
    ),
    OpCode.BUILD_STRING: TEXT_BRACES,
    **dict.fromkeys(
        (
            OpCode.BUILD_LIST,
            OpCode.INDEX_GET,
            OpCode.INDEX_SET,
            OpCode.SLICE_GET,
            OpCode.LIST_APPEND,
            OpCode.UNPACK_SEQUENCE,
            OpCode.GET_ITER,
            OpCode.FOR_ITER,
        ),
        LISTS,
    ),
    OpCode.BUILD_DICT: DICTIONARIES,
    **dict.fromkeys(
        (
            OpCode.GET_FIELD,
            OpCode.SET_FIELD,
            OpCode.CALL_INSTANCE_METHOD,
            OpCode.LOAD_ENUM_VARIANT,
        ),
        STRUCTS,
    ),
    OpCode.CALL_METHOD: METHODS,
    **dict.fromkeys(
        (OpCode.MAKE_CLOSURE, OpCode.LOAD_CELL, OpCode.STORE_CELL), FUNCTIONS_AS_VALUES
    ),
    **dict.fromkeys((OpCode.SETUP_TRY, OpCode.POP_TRY, OpCode.THROW), TRY_CATCH),
    **dict.fromkeys((OpCode.YIELD, OpCode.AWAIT), GENERATORS),
    **dict.fromkeys(
        (
            OpCode.JUMP,
            OpCode.JUMP_IF_FALSE,
            OpCode.JUMP_IF_FALSE_OR_POP,
            OpCode.JUMP_IF_TRUE_OR_POP,
            OpCode.LESS_THAN,
            OpCode.LESS_EQUAL,
            OpCode.GREATER_THAN,
            OpCode.GREATER_EQUAL,
            OpCode.EQUAL,
            OpCode.NOT_EQUAL,
            OpCode.NOT,
        ),
        CONTROL_FLOW_FOR_NOW,
    ),
}

ARITHMETIC = frozenset(
    {OpCode.ADD, OpCode.SUBTRACT, OpCode.MULTIPLY, OpCode.FLOOR_DIVIDE, OpCode.MODULO}
)
_SUPPORTED = frozenset(
    {
        OpCode.LOAD_CONST,
        OpCode.LOAD_NAME,
        OpCode.STORE_NAME,
        OpCode.NEGATE,
        OpCode.POP,
        OpCode.PRINT,
        OpCode.CHECK_TYPE,
        OpCode.HALT,
        OpCode.RETURN,
        *ARITHMETIC,
    }
)
# Refused instructions whose effect on the stack we still follow, so the kind check
# can carry on past them (a refused name still pushes one value).
_KEEP_WALKING = frozenset({OpCode.LOAD_NAME, OpCode.CHECK_TYPE})


def builtin_function(name: str) -> str:
    """Return the feature name for calling the built-in or library function `name`."""
    return f"the built-in function {name}()"


class PebbleCPUError(Exception):
    """Say that a Pebble program cannot run on PyCPU. Every translator error is one of these."""


class UnsupportedFeature(PebbleCPUError):  # noqa: N818 - the plan fixes this name; it names a feature
    """Say that a Pebble program uses something PyCPU cannot do yet, and where.

    The message reads like a sentence, for example `lists are not supported on PyCPU
    yet at line 1, column 9`.

    Attributes:
        feature: What the program used, in plain words, such as `decimal numbers`.
        line: The Pebble line it is on (1-based), or None if nobody knows.
        column: The column on that line (1-based), or None if nobody knows.

    """

    def __init__(self, feature: str, line: int | None = None, column: int | None = None) -> None:
        """Remember the feature and its place, and build the message."""
        verb = "is" if feature in _SINGULAR or feature.startswith("the ") else "are"
        place = f" at line {line}, column {column}" if line is not None else ""
        super().__init__(f"{feature} {verb} not supported on PyCPU yet{place}")
        self.feature = feature
        self.line = line
        self.column = column


class Kind(Enum):
    """What kind of thing sits in one slot of Pebble's stack."""

    INT = auto()
    BOOL = auto()
    TEXT = auto()
    NULL = auto()
    MAYBE = auto()


@dataclass(frozen=True)
class CheckedCode:
    """One piece of Pebble code (main or a function) that passed the check.

    Attributes:
        name: `main`, or the function's name.
        code: Pebble's compiled code for it.
        variables: The names it stores, in the order they first appear; each one
            gets a slot in memory.
        prints_text: The positions of its `PRINT` instructions that print text
            rather than a number.
        deepest: The most slots Pebble's stack ever holds while it runs.

    """

    name: str
    code: CodeObject
    variables: tuple[str, ...]
    prints_text: frozenset[int]
    deepest: int


@dataclass(frozen=True)
class CheckedProgram:
    """A whole Pebble program that passed the check: main and its functions."""

    main: CheckedCode
    functions: dict[str, CheckedCode]


@dataclass(frozen=True)
class _Problem:
    """One thing the check found, with the place it was found."""

    feature: str
    location: SourceLocation | None

    def key(self) -> tuple[int, int]:
        """Sort problems by place in the source; ones with no place go last."""
        if self.location is None:
            return (WORD_MAX, WORD_MAX)
        return (self.location.line, self.location.column)


@dataclass(frozen=True)
class _Slot:
    """One slot of Pebble's stack: its kind, and where the value in it was made."""

    kind: Kind
    made_at: SourceLocation | None
    null_literal: bool = False


def located(instructions: Sequence[Instruction]) -> list[SourceLocation | None]:
    """Give each instruction a place in the source, borrowing one if it has none.

    The compiler makes some instructions itself (like the final `HALT`), and those have
    no place. Each borrows the place of the last instruction before it that has one, so
    a fault there is still reported at a sensible line.
    """
    places: list[SourceLocation | None] = []
    last: SourceLocation | None = None
    for instruction in instructions:
        last = instruction.location or last
        places.append(last)
    return places


class _CodeChecker:
    """Check one code object: walk it once, keeping the kind of every stack slot."""

    def __init__(self, name: str, code: CodeObject, program: CompiledProgram) -> None:
        """Get ready to check `code`, which belongs to `program`."""
        self.name = name
        self.code = code
        self.program = program
        self.places = located(code.instructions)
        self.stored = {str(i.operand) for i in code.instructions if i.opcode == OpCode.STORE_NAME}
        self.problems: list[_Problem] = []
        self.stack: list[_Slot] = []
        self.variables: list[str] = []
        self.prints_text: set[int] = set()
        self.deepest = 0

    def check(self) -> CheckedCode:
        """Walk every instruction and return what the translator needs to know."""
        walking = True
        for index, instruction in enumerate(self.code.instructions):
            place = self.places[index]
            feature = self._opcode_problem(instruction)
            if feature is not None:
                self._problem(feature, place)
                # Most refused instructions have a stack effect we do not follow, so
                # stop tracking kinds there and only look for opcode problems.
                walking = walking and instruction.opcode in _KEEP_WALKING
            if walking:
                walking = self._step(index, instruction, place)
        if self.problems:
            first = min(self.problems, key=_Problem.key)
            location = first.location
            raise UnsupportedFeature(
                first.feature,
                location.line if location else None,
                location.column if location else None,
            )
        return CheckedCode(
            self.name,
            self.code,
            tuple(self.variables),
            frozenset(self.prints_text),
            self.deepest,
        )

    def _problem(self, feature: str, place: SourceLocation | None) -> None:
        """Note one problem; the earliest in the source is reported in the end."""
        self.problems.append(_Problem(feature, place))

    def _opcode_problem(self, instruction: Instruction) -> str | None:
        """Return the feature an instruction itself uses that we cannot do, if any."""
        opcode, operand = instruction.opcode, instruction.operand
        if opcode in _OPCODE_FEATURES:
            return _OPCODE_FEATURES[opcode]
        if opcode in (OpCode.CALL, OpCode.LOAD_NAME):
            return self._name_problem(opcode, str(operand))
        if opcode == OpCode.CHECK_TYPE and operand != "Int":
            return f"the {operand} type"
        return None if opcode in _SUPPORTED else f"the {opcode} instruction"

    def _name_problem(self, opcode: str, name: str) -> str | None:
        """Return what is wrong with a call or a name lookup, if anything."""
        is_function = name in self.program.functions
        if opcode == OpCode.CALL:
            if is_function:
                return FUNCTIONS_FOR_NOW
            # Pebble's built-in and library functions are lower case; a capital
            # letter means a struct or class being made, like `Point(1, 2)`.
            return STRUCTS if name[:1].isupper() else builtin_function(name)
        if is_function:
            return FUNCTIONS_AS_VALUES
        if name not in self.stored and name not in self.code.parameters:
            return OUTSIDE_VARIABLES
        return None

    def _pop(self) -> _Slot:
        """Take the top slot off the imagined stack."""
        return self.stack.pop()

    def _push(
        self, kind: Kind, place: SourceLocation | None, *, null_literal: bool = False
    ) -> None:
        """Put a slot on the imagined stack and remember the deepest it has been."""
        self.stack.append(_Slot(kind, place, null_literal))
        self.deepest = max(self.deepest, len(self.stack))

    def _need_number(self, slot: _Slot) -> None:
        """Complain unless a slot holds a number, naming where its value was made."""
        refusals = {
            Kind.BOOL: BOOL_OUTSIDE_CONDITIONS,
            Kind.TEXT: TEXT_OUTSIDE_PRINT,
            Kind.NULL: NULL_USED,
            Kind.MAYBE: NULL_USED,
        }
        if slot.null_literal:
            self._problem(NULL_VALUES, slot.made_at)
        elif slot.kind in refusals:
            self._problem(refusals[slot.kind], slot.made_at)

    def _step(self, index: int, instruction: Instruction, place: SourceLocation | None) -> bool:
        """Play one instruction on the imagined stack; return False to stop walking."""
        opcode = instruction.opcode
        if opcode == OpCode.LOAD_CONST:
            self._load_constant(int(instruction.operand or 0), place)
        elif opcode == OpCode.LOAD_NAME:
            self._push(Kind.INT, place)
        elif opcode == OpCode.STORE_NAME:
            self._need_number(self._pop())
            self._store(str(instruction.operand), place)
        elif opcode in ARITHMETIC:
            right, left = self._pop(), self._pop()
            self._need_number(left)
            self._need_number(right)
            self._push(Kind.INT, place)
        elif opcode == OpCode.NEGATE:
            self._need_number(self._pop())
            self._push(Kind.INT, place)
        elif opcode == OpCode.POP:
            self._pop()
        elif opcode == OpCode.PRINT:
            slot = self._pop()
            if slot.kind is Kind.TEXT:
                self.prints_text.add(index)
            else:
                self._need_number(slot)
        elif opcode == OpCode.RETURN:
            slot = self._pop()
            if slot.kind is not Kind.NULL:
                self._need_number(slot)
        return opcode not in (OpCode.HALT, OpCode.RETURN)

    def _load_constant(self, number: int, place: SourceLocation | None) -> None:
        """Push a constant's kind, complaining about values PyCPU cannot hold."""
        value = self.code.constants[number]
        if isinstance(value, bool):
            self._push(Kind.BOOL, place)
        elif isinstance(value, int):
            if not INT_MIN <= value <= INT_MAX:
                self._problem(NUMBER_RANGE, place)
            self._push(Kind.INT, place)
        elif isinstance(value, float):
            self._problem(DECIMALS, place)
            self._push(Kind.INT, place)
        elif isinstance(value, str):
            if any(ord(char) > WORD_MAX for char in value):
                self._problem(BIG_CHARACTERS, place)
            if "\0" in value:
                self._problem(ZERO_CHARACTER, place)
            self._push(Kind.TEXT, place)
        elif value is None:  # a literal `null`
            self._push(Kind.NULL, place, null_literal=True)
        else:
            self._problem(f"values like {value!r}", place)
            self._push(Kind.INT, place)

    def _store(self, name: str, place: SourceLocation | None) -> None:
        """Give a newly stored name the next slot, if there is one left."""
        if name in self.variables or name in self.code.parameters:
            return
        if len(self.variables) == MAX_VARIABLES:
            self._problem(TOO_MANY_VARIABLES, place)
        self.variables.append(name)


def check_program(compiled: CompiledProgram) -> CheckedProgram:
    """Check a whole compiled Pebble program against the PyCPU subset.

    Every code object is checked, and the problem nearest the top of the source wins.

    Args:
        compiled: What `pebble.compile_source(...).compiled` gives.

    Returns:
        Each code object with its variables, its text prints and its deepest stack.

    Raises:
        UnsupportedFeature: If anything in the program is outside the subset.

    """
    codes = [("main", compiled.main), *compiled.functions.items()]
    problems: list[UnsupportedFeature] = []
    checked: list[CheckedCode] = []
    for name, code in codes:
        try:
            checked.append(_CodeChecker(name, code, compiled).check())
        except UnsupportedFeature as error:
            problems.append(error)
    if problems:
        raise min(problems, key=_error_key)
    return CheckedProgram(checked[0], {code.name: code for code in checked[1:]})


def _error_key(error: UnsupportedFeature) -> tuple[int, int]:
    """Sort errors by place in the source; ones with no place go last."""
    return (
        WORD_MAX if error.line is None else error.line,
        WORD_MAX if error.column is None else error.column,
    )
