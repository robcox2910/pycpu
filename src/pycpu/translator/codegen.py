"""The code generator: a translator who writes a few number cards for every line of a recipe.

Pebble's compiler has already broken the program into tiny bytecode steps such as "put 6
on the stack" or "multiply the top two". This file takes the steps one at a time and
writes the PyCPU assembly that does the same thing, the way a translator turns each line
of a recipe into a few cards the cook can read. On the back of every card it pencils the
Pebble line the card came from, which becomes the source map.

The rules it follows are the same for every step. Pebble's stack is PyCPU's real stack:
"put 6 on the stack" is `push`, "take the top two" is two `pop`s. No value is kept in a
register from one step to the next. `r0` always holds 0, `r1` to `r6` are scratch paper,
and `r7` is the **frame pointer**: it points at the frame, the block of memory that holds
this piece of code's variables, and a variable is always found at the same distance
below it. See the Variables in Memory page for the picture.

Jumps work like page numbers in a choose-your-own-adventure book. Every bytecode
instruction that some jump goes to gets a label named after its position, such as
`__main_7`, and a Pebble jump becomes a `jmp` to that label (see If and While as Jumps).

Each Pebble function gets the same treatment as main, starting at its own label such
as `__fn_double`. A call is "leave the arguments on the stack, `call`, then tidy the
arguments away and push the answer from `r1`" (see How a Function Call Really Works).
"""

from dataclasses import dataclass

from pebble import Instruction, OpCode

from pycpu.translator.runtime import RUNTIME, RUNTIME_STACK_WORDS
from pycpu.translator.subset import (
    COMPARISONS,
    JUMPS,
    CheckedCode,
    CheckedProgram,
    PebbleCPUError,
    located,
)

BYTE_MAX = 255
COLUMN = 24
MAIN_LABEL = "__main"
FUNCTION_PREFIX = "__fn_"
# A `call` pushes one word, the return address, before the called function's prologue
# checks for room. That word lands in the room the caller set aside for the routines.
RETURN_ADDRESS_WORDS = 1
_ASCII_LETTERS_AND_DIGITS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
)
END_LABEL = "__end"
_ALU = {OpCode.ADD: "add", OpCode.SUBTRACT: "sub"}
# Each comparison, the signed branch condition that says "yes", and how to say it.
_BRANCHES: dict[str, tuple[str, str]] = {
    OpCode.LESS_THAN: ("lt", "<"),
    OpCode.LESS_EQUAL: ("le", "<="),
    OpCode.GREATER_THAN: ("gt", ">"),
    OpCode.GREATER_EQUAL: ("ge", ">="),
    OpCode.EQUAL: ("eq", "=="),
    OpCode.NOT_EQUAL: ("ne", "!="),
}


@dataclass(frozen=True)
class Assembly:
    """The assembly text for a whole program, and the Pebble line of each text line.

    Attributes:
        text: The assembly, ready for `pycpu.assembler.assemble`.
        lines: For each line of `text` (the first is index 0), the Pebble line it was
            written for, or None for the runtime routines, the text data and headings.

    """

    text: str
    lines: tuple[int | None, ...]


def frame_words(checked: CheckedCode) -> int:
    """Count the stack words a piece of code may need: old r7, variables, stack, routines.

    The deepest stack already counts the arguments it pushes for a call. On top of
    that, a call to a routine needs `RUNTIME_STACK_WORDS` and a call to a Pebble
    function needs just its return address, so the larger of the two is set aside; the
    called function checks the room for its own frame in its own prologue.
    """
    calls = max(RUNTIME_STACK_WORDS, RETURN_ADDRESS_WORDS)
    return 1 + len(checked.variables) + checked.deepest + calls


def function_label(name: str) -> str:
    """Return the label where the Pebble function `name` starts, such as `__fn_double`.

    A Pebble name may hold letters from any language, but a label may only hold the
    plain letters A to Z, digits and `_`. So plain letters and digits stay, `_` is
    written twice, and any other character becomes `_x`, its number in hex, and `_`
    (`café` becomes `__fn_caf_xe9_`). The other labels of the function add `_` and a
    number or a word to this one. Inside the name, a single `_` is only ever followed
    by `x`, and none of those additions start with `_` or `x`, so no label of one
    function can ever be spelled the same as a label of another.
    """
    pieces = [
        char if char in _ASCII_LETTERS_AND_DIGITS else "__" if char == "_" else f"_x{ord(char):x}_"
        for char in name
    ]
    return FUNCTION_PREFIX + "".join(pieces)


def _quote(text: str) -> str:
    """Write text in double quotes the way the assembler's `.string` reads it back."""
    escapes = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\t": "\\t"}
    return '"' + "".join(escapes.get(char, char) for char in text) + '"'


class _Writer:
    """Collect assembly lines, each tagged with the Pebble line it belongs to."""

    def __init__(self) -> None:
        """Start with no lines and no text."""
        self.lines: list[str] = []
        self.pebble: list[int | None] = []
        self.texts: dict[str, str] = {}

    def raw(self, text: str, line: int | None = None) -> None:
        """Add one or more lines exactly as written."""
        for piece in text.split("\n"):
            self.lines.append(piece)
            self.pebble.append(line)

    def op(self, instruction: str, comment: str, line: int | None) -> None:
        """Add one indented instruction with a comment lined up beside it."""
        # A long instruction still gets one space before its comment.
        self.raw(f"    {instruction:<{COLUMN - 1}} ; {comment}", line)

    def text_label(self, text: str) -> str:
        """Return the label of a piece of text, giving it a new one the first time."""
        return self.texts.setdefault(text, f"__str_{len(self.texts)}")


class _CodeWriter:
    """Write the assembly for one piece of Pebble code: main or one function."""

    def __init__(
        self, writer: _Writer, checked: CheckedCode, label: str, program: CheckedProgram
    ) -> None:
        """Get ready to write `checked`, whose code starts at `label`."""
        self.out = writer
        self.checked = checked
        self.code = checked.code
        self.label = label
        self.program = program
        # Variables sit below r7; parameters above it, where the caller pushed them,
        # the last one nearest: parameter i of N is at [r7 + 2 + (N - 1 - i)].
        count = len(self.code.parameters)
        self.slots = {name: 2 + (count - 1 - i) for i, name in enumerate(self.code.parameters)}
        self.slots.update({name: -1 - j for j, name in enumerate(checked.variables)})
        self.places = located(self.code.instructions)
        first = next((place for place in self.places if place is not None), None)
        self.first_line = first.line if first else None
        # Every instruction some jump goes to gets a label: its "page number".
        self.targets = {int(i.operand or 0) for i in self.code.instructions if i.opcode in JUMPS}

    def write(self) -> None:
        """Write the prologue, then the cards for every bytecode instruction."""
        self._prologue()
        for index, instruction in enumerate(self.code.instructions):
            place = self.places[index]
            line = place.line if place else None
            if index in self.targets:
                self.out.raw(f"{self._page(index)}:", line)
            self.out.raw(f"    ; {self._describe(instruction, line)}", line)
            self._instruction(index, instruction, line)
        end = len(self.code.instructions)
        if end in self.targets:
            # A jump to just past the last instruction: Pebble returns null there.
            place = self.places[-1]
            line = place.line if place else None
            self.out.raw(f"{self._page(end)}:", line)
            self.out.raw("    ; the end of the code: Pebble gives back null here", line)
            self.out.op("push r0", "null is stored as 0", line)
            self._leave(OpCode.RETURN, line)

    def _page(self, index: int) -> str:
        """Return the label of instruction `index`, such as `__main_7`."""
        return f"{self.label}_{index}"

    def _describe(self, instruction: Instruction, line: int | None) -> str:
        """Say which Pebble instruction the next few lines come from, for a reader."""
        operand = instruction.operand
        if instruction.opcode == OpCode.LOAD_CONST:
            value = self.code.constants[int(operand or 0)]
            operand = _quote(value) if isinstance(value, str) else value
        words = f"{instruction.opcode}" if operand is None else f"{instruction.opcode} {operand}"
        return f"line {line}: {words}" if line is not None else words

    def _prologue(self) -> None:
        """Check there is room on the stack, then build the frame and zero the variables."""
        line, out, label = self.first_line, self.out, self.label
        count = len(self.checked.variables)
        need = frame_words(self.checked)
        out.raw(f"{label}:", line)
        out.raw(
            f"    ; make the frame: 1 word for the old r7, {count} for variables, "
            f"{self.checked.deepest} for the stack, {RUNTIME_STACK_WORDS} for the routines",
            line,
        )
        out.op("getsp r1", "r1 = the top of the stack, where the frame starts", line)
        out.op(f"set  r2, {END_LABEL}", "r2 = the first free word after the program", line)
        load = "li  " if need <= BYTE_MAX else "set "
        out.op(f"{load} r3, {need}", f"r3 = the {need} words this code may need", line)
        out.op("add  r2, r2, r3", "r2 = the lowest the stack may start from", line)
        out.op("cmp  r1, r2", "is there room?", line)
        out.op(f"br   geu, {label}_room", "yes: carry on", line)
        out.op("halt 2", "no: STACK_OVERFLOW, before anything is overwritten", line)
        out.raw(f"{label}_room:", line)
        out.op("push r7", "keep the old frame pointer", line)
        out.op("getsp r7", "r7 = the frame pointer: variables sit just below it", line)
        for name in self.checked.variables:
            out.op("push r0", f"{name} = 0, at [r7{self.slots[name]}]", line)

    def _instruction(self, index: int, instruction: Instruction, line: int | None) -> None:
        """Write the cards for one bytecode instruction."""
        out, opcode = self.out, instruction.opcode
        if opcode == OpCode.LOAD_CONST:
            self._load_constant(int(instruction.operand or 0), line)
        elif opcode in (OpCode.LOAD_NAME, OpCode.STORE_NAME):
            self._variable(opcode, str(instruction.operand), line)
        elif opcode in (*_ALU, OpCode.MULTIPLY, OpCode.FLOOR_DIVIDE, OpCode.MODULO):
            self._arithmetic(index, opcode, line)
        elif opcode in COMPARISONS:
            self._compare(index, opcode, line)
        elif opcode == OpCode.NOT:
            self._not(index, line)
        elif opcode in JUMPS:
            self._jump(index, opcode, int(instruction.operand or 0), line)
        elif opcode in (OpCode.NEGATE, OpCode.POP, OpCode.PRINT):
            self._one_value(index, opcode, line)
        elif opcode in (OpCode.HALT, OpCode.RETURN):
            self._leave(opcode, line)
        elif opcode == OpCode.CALL:
            self._call(str(instruction.operand), line)
        elif opcode == OpCode.CHECK_TYPE:
            out.raw("    ; (no code: Pebble has already checked this is a number)", line)
        else:
            # The subset check should have refused it; writing nothing would be wrong code.
            msg = f"translator bug: no code for {opcode}"
            raise PebbleCPUError(msg)

    def _one_value(self, index: int, opcode: OpCode, line: int | None) -> None:
        """Write `NEGATE`, `POP` or `PRINT`, which each take one value off the stack."""
        out = self.out
        if opcode == OpCode.NEGATE:
            out.op("pop  r1", "r1 = the number", line)
            out.op("sub  r1, r0, r1", "r1 = 0 - r1", line)
            out.op("push r1", "the answer goes on the stack", line)
        elif opcode == OpCode.POP:
            out.op("pop  r1", "the value is not needed: throw it away", line)
        else:
            routine = "__print_text" if index in self.checked.prints_text else "__print_int"
            out.op("pop  r1", "r1 = the thing to print", line)
            out.op(f"call {routine}", "print it and a newline", line)

    def _leave(self, opcode: OpCode, line: int | None) -> None:
        """Write `HALT` (stop the machine) or `RETURN` (give a value back to the caller)."""
        out = self.out
        if opcode == OpCode.HALT:
            out.op("halt 0", "the program has finished", line)
            return
        out.op("pop  r1", "r1 = the value to give back", line)
        out.op("setsp r7", "drop the variables and the stack in one go", line)
        out.op("pop  r7", "get the caller's frame pointer back", line)
        out.op("ret", "go back to the caller", line)

    def _call(self, name: str, line: int | None) -> None:
        """Write a call to a Pebble function, whose arguments are already on the stack.

        The function leaves its answer in `r1`. Afterwards the arguments are still on
        the stack, so the stack pointer is moved up past them in one go.
        """
        out = self.out
        count = len(self.program.functions[name].code.parameters)
        where = "leaving the return address on the stack"
        out.op(f"call {function_label(name)}", f"go to {name}, {where}", line)
        if count:
            words = "the argument is" if count == 1 else f"the {count} arguments are"
            plural = "" if count == 1 else "s"
            out.op("getsp r2", "r2 = the top of the stack", line)
            out.op(f"addi r2, {count}", f"step over the {count} argument{plural}", line)
            out.op("setsp r2", f"{words} thrown away", line)
        out.op("push r1", f"the answer {name} gave back goes on the stack", line)

    def _variable(self, opcode: OpCode, name: str, line: int | None) -> None:
        """Write `LOAD_NAME` or `STORE_NAME`: copy between the stack and the name's slot."""
        out, slot = self.out, f"[r7{self.slots[name]:+d}]"
        if opcode == OpCode.LOAD_NAME:
            out.op(f"load r1, {slot}", f"r1 = {name}", line)
            out.op("push r1", "onto the stack", line)
        else:
            out.op("pop  r1", "r1 = the value on top of the stack", line)
            out.op(f"store r1, {slot}", f"{name} = r1", line)

    def _arithmetic(self, index: int, opcode: OpCode, line: int | None) -> None:
        """Write `+`, `-` and `*` here; `//` and `%` need a divide-by-zero check first."""
        out = self.out
        if opcode in (OpCode.FLOOR_DIVIDE, OpCode.MODULO):
            self._divide(index, opcode, line)
            return
        self._two_numbers(line)
        if opcode in _ALU:
            out.op(f"{_ALU[opcode]}  r1, r1, r2", "work it out", line)
        else:
            out.op("call __mul", "r1 = r1 * r2", line)
        out.op("push r1", "the answer goes on the stack", line)

    def _load_constant(self, number: int, line: int | None) -> None:
        """Write the cards that put a number, or the address of a text, on the stack."""
        value = self.code.constants[number]
        if value is None:
            self.out.op("push r0", "null is stored as 0", line)
            return
        if isinstance(value, str):
            label = self.out.text_label(value)
            self.out.op(f"set  r1, {label}", "r1 = the address of the text", line)
        elif isinstance(value, bool):  # before int: in Python, True is also an int
            word = int(value)
            self.out.op(f"li   r1, {word}", f"{str(value).lower()} is {word} (0 means false)", line)
        elif isinstance(value, int):  # the subset check let only these kinds through
            load = "li  " if 0 <= value <= BYTE_MAX else "set "
            self.out.op(f"{load} r1, {value}", f"r1 = {value}", line)
        self.out.op("push r1", "onto the stack", line)

    def _two_numbers(self, line: int | None) -> None:
        """Pop the two numbers an operator works on: the right one is on top."""
        self.out.op("pop  r2", "r2 = the right-hand number", line)
        self.out.op("pop  r1", "r1 = the left-hand number", line)

    def _compare(self, index: int, opcode: OpCode, line: int | None) -> None:
        """Write a comparison: `cmp` lights the flags, a signed branch reads them."""
        out, yes = self.out, f"{self.label}_yes_{index}"
        condition, symbol = _BRANCHES[opcode]
        self._two_numbers(line)
        out.op("li   r3, 1", "r3 = 1 (true), unless we find otherwise", line)
        out.op("cmp  r1, r2", "work out r1 - r2, keeping only the flags", line)
        out.op(f"br   {condition}, {yes}", f"is r1 {symbol} r2? then keep the 1", line)
        out.op("li   r3, 0", "no: r3 = 0 (false)", line)
        out.raw(f"{yes}:", line)
        out.op("push r3", "true or false goes on the stack", line)

    def _not(self, index: int, line: int | None) -> None:
        """Write `not`: 0 (false) becomes 1, and anything else becomes 0."""
        out, yes = self.out, f"{self.label}_yes_{index}"
        out.op("pop  r1", "r1 = the condition", line)
        out.op("li   r3, 1", "r3 = 1 (true), unless we find otherwise", line)
        out.op("cmp  r1, r0", "is the condition 0 (false)?", line)
        out.op(f"br   eq, {yes}", "yes: not false is true, keep the 1", line)
        out.op("li   r3, 0", "no: not true is false", line)
        out.raw(f"{yes}:", line)
        out.op("push r3", "true or false goes on the stack", line)

    def _jump(self, index: int, opcode: OpCode, target: int, line: int | None) -> None:
        """Write a jump to instruction `target`.

        A `br` only reaches 255 words forwards or 256 back, and a loop can be longer, so
        a jump that depends on a condition branches *over* a `jmp`, which reaches anywhere.
        """
        out, page, go_on = self.out, self._page(target), f"{self.label}_go_on_{index}"
        if opcode == OpCode.JUMP:
            out.op(f"jmp  {page}", f"go to instruction {target}", line)
            return
        if opcode == OpCode.JUMP_IF_FALSE:
            out.op("pop  r1", "r1 = the condition", line)
            out.op("cmp  r1, r0", "is it 0 (false)?", line)
            out.op(f"br   ne, {go_on}", "no, it is true: carry on", line)
            out.op(f"jmp  {page}", f"yes, false: go to instruction {target}", line)
        else:
            # `and` stops at a false left side, `or` at a true one; either way that
            # value is the answer, so it goes back on the stack before the jump.
            decides = "false" if opcode == OpCode.JUMP_IF_FALSE_OR_POP else "true"
            other = "eq" if decides == "true" else "ne"
            out.op("pop  r1", "r1 = the left-hand side", line)
            out.op("cmp  r1, r0", "is it 0 (false)?", line)
            out.op(f"br   {other}, {go_on}", "the right-hand side decides: work it out", line)
            out.op("push r1", f"it is {decides}, so it is the answer: keep it", line)
            out.op(f"jmp  {page}", f"and skip to instruction {target}", line)
        out.raw(f"{go_on}:", line)

    def _divide(self, index: int, opcode: str, line: int | None) -> None:
        """Write `//` or `%`: check the divisor is not 0, then call `__divmod`."""
        out, ok = self.out, f"{self.label}_divisor_ok_{index}"
        self._two_numbers(line)
        out.op("cmp  r2, r0", "is the divisor 0?", line)
        out.op(f"br   ne, {ok}", "no: go ahead and divide", line)
        out.op("halt 3", "yes: DIVIDE_BY_ZERO", line)
        out.raw(f"{ok}:", line)
        out.op("call __divmod", "r1 = r1 // r2, r2 = r1 % r2", line)
        keep = "r1" if opcode == OpCode.FLOOR_DIVIDE else "r2"
        out.op(f"push {keep}", "the answer goes on the stack", line)


def generate(program: CheckedProgram) -> Assembly:
    """Write the assembly for a checked Pebble program.

    The layout from address 0 is: main (ending in `halt 0`), each function, the runtime
    routines, the text data, then the label `__end`, the first word the stack must
    never reach.

    Args:
        program: A program that passed `check_program`.

    Returns:
        The assembly text and the Pebble line of each of its lines.

    """
    out = _Writer()
    out.raw("; ==== main: the Pebble program's own code ====")
    _CodeWriter(out, program.main, MAIN_LABEL, program).write()
    for name, checked in program.functions.items():
        parameters = ", ".join(checked.code.parameters)
        out.raw(f"; ==== function {name}({parameters}): its own frame, like main's ====")
        _CodeWriter(out, checked, function_label(name), program).write()
    out.raw("; ==== runtime: the ready-made routines for multiply, divide and print ====")
    out.raw(RUNTIME.strip("\n"))
    out.raw("; ==== text: every piece of text, one character per word, ending in 0 ====")
    for text, label in out.texts.items():
        out.raw(f"{label}: .string {_quote(text)}")
    out.raw(f"; ==== the end of the program: the stack must never grow down to {END_LABEL} ====")
    out.raw(f"{END_LABEL}:")
    return Assembly("\n".join(out.lines) + "\n", tuple(out.pebble))
