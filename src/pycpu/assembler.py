"""The assembler: a helper who turns a recipe written in words into the cook's number cards.

Writing `0xE2FF` by hand is miserable, so people write `addi r1, -1` and let a
helper translate. The helper also keeps sticky-tab bookmarks (labels): write
`loop:` once, say `br ne, loop` anywhere, and the helper works out which card
number the tab is on. This file is that helper, and its mirror image, the
disassembler, who reads a number card back out as the words you would have written.

The assembler reads the text twice. Pass 1 only counts how many words each line
becomes, so it knows where every label sits. Pass 2 writes the words, using
`encode` from `isa.py`, which is still the only place that knows what a number means.
Every mistake becomes an `AssemblyError` that says which line and what would be right.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from pycpu.arithmetic import AluOp
from pycpu.isa import (
    ADDR12_BITS,
    IMM8_BITS,
    OFF6_BITS,
    OFF9_BITS,
    WORD_MASK,
    Condition,
    Instruction,
    Opcode,
    decode,
    encode,
)
from pycpu.memory import RAM_WORDS, WORD_BITS
from pycpu.state import REGISTER_COUNT

SIGNED_WORD_MIN = -(1 << (WORD_BITS - 1))
BYTE_MAX = (1 << IMM8_BITS) - 1
IMM8_SIGNED_MIN = -(1 << (IMM8_BITS - 1))
IMM8_SIGNED_MAX = (1 << (IMM8_BITS - 1)) - 1
OFF6_MIN = -(1 << (OFF6_BITS - 1))
OFF6_MAX = (1 << (OFF6_BITS - 1)) - 1
OFF9_MIN = -(1 << (OFF9_BITS - 1))
OFF9_MAX = (1 << (OFF9_BITS - 1)) - 1
MIN_CHAR_LITERAL = 3
MIN_QUOTED = 2
MAX_DIGITS = 20
MAX_ADDRESS = (1 << WORD_BITS) - 1
ADDR12_MAX = (1 << ADDR12_BITS) - 1

_NAME = r"[A-Za-z_][A-Za-z0-9_]*"
_REGISTER_NAMES = ", ".join(f"r{n}" for n in range(REGISTER_COUNT - 1))
_REGISTER_LIST = f"{_REGISTER_NAMES} and r{REGISTER_COUNT - 1}"
_ESCAPES = {"n": "\n", "t": "\t", "0": "\0", "\\": "\\", '"': '"', "'": "'"}

# The ALU mnemonics and the operands each one takes (all but `mov` and the shifts take three).
_ALU_NAMES = {
    "add": AluOp.ADD,
    "sub": AluOp.SUB,
    "and": AluOp.AND,
    "or": AluOp.OR,
    "xor": AluOp.XOR,
}
_SHIFT_NAMES = {"shl": AluOp.SHL, "shr": AluOp.SHR}

# Every instruction word's shape: the operand kinds, and an example for error messages.
_SHAPES: dict[str, tuple[tuple[str, ...], str]] = {
    **dict.fromkeys(_ALU_NAMES, (("reg", "reg", "reg"), "{} r3, r1, r2")),
    **dict.fromkeys(_SHIFT_NAMES, (("reg", "reg"), "{} r3, r1")),
    "mov": (("reg", "reg"), "mov r3, r2"),
    "cmp": (("reg", "reg"), "cmp r1, r2"),
    "li": (("reg", "num"), "li r1, 5"),
    "lhi": (("reg", "num"), "lhi r1, 18"),
    "set": (("reg", "val"), "set r1, 1000"),
    "load": (("reg", "mem"), "load r1, [r2+1]"),
    "store": (("reg", "mem"), "store r1, [r2+1]"),
    "jmp": (("val",), "jmp start"),
    "call": (("val",), "call start"),
    "br": (("cond", "val"), "br ne, loop"),
    "ret": ((), "ret"),
    "push": (("reg",), "push r1"),
    "pop": (("reg",), "pop r1"),
    "getsp": (("reg",), "getsp r1"),
    "setsp": (("reg",), "setsp r1"),
    "addi": (("reg", "num"), "addi r1, -1"),
}
_SIMPLE_OPCODES = {
    "cmp": Opcode.CMP,
    "li": Opcode.LI,
    "lhi": Opcode.LHI,
    "load": Opcode.LOAD,
    "store": Opcode.STORE,
    "jmp": Opcode.JMP,
    "call": Opcode.CALL,
    "ret": Opcode.RET,
    "push": Opcode.PUSH,
    "pop": Opcode.POP,
    "getsp": Opcode.GETSP,
    "setsp": Opcode.SETSP,
    "addi": Opcode.ADDI,
}
_DIRECTIVES = (".word", ".string")


class AssemblyError(ValueError):
    """Say that the assembly text has a mistake, naming the line and how to fix it.

    The message always starts `line N:`, so a learner can find the spot at once.

    Attributes:
        line: The 1-based line number of the mistake.

    """

    def __init__(self, line: int, problem: str) -> None:
        """Remember the line and build the `line N: ...` message."""
        super().__init__(f"line {line}: {problem}")
        self.line = line


@dataclass(frozen=True)
class Program:
    """The finished stack of number cards, plus the bookmarks and where each came from.

    Attributes:
        words: The machine code, one 16-bit word per address, starting at address 0.
        labels: Each label's name, mapped to the address it marks.
        lines: For each word, the 1-based source line it came from.

    """

    words: tuple[int, ...]
    labels: dict[str, int]
    lines: tuple[int, ...]


@dataclass(frozen=True)
class _Item:
    """One source line after pass 1: what it says, where it sits, how many words it takes."""

    line: int
    address: int
    name: str
    operands: tuple[str, ...]
    size: int


def _strip_comment(text: str, line: int) -> str:
    """Cut off a `;` comment, but not a `;` inside quotes; refuse an unclosed quote."""
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            if char == "\\":
                index += 1
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
        elif char == ";":
            return text[:index]
        index += 1
    if quote:
        kind = "string" if quote == '"' else "character"
        raise AssemblyError(
            line,
            f"a {kind} starting with {quote} never ends: add a closing quote ({quote}) on the same line",
        )
    return text


def _split_operands(text: str) -> list[str]:
    """Split on commas that are not inside quotes. The quotes were already checked."""
    parts: list[str] = []
    current = ""
    quote = ""
    index = 0
    while index < len(text):
        char = text[index]
        if quote:
            current += char
            if char == "\\" and index + 1 < len(text):
                index += 1
                current += text[index]
            elif char == quote:
                quote = ""
        elif char in "\"'":
            quote = char
            current += char
        elif char == ",":
            parts.append(current.strip())
            current = ""
        else:
            current += char
        index += 1
    parts.append(current.strip())
    return parts if text.strip() else []


def _unescape(body: str, line: int) -> str:
    """Turn the inside of a quoted text into characters, understanding backslash escapes."""
    out = ""
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\":
            index += 1
            escape = body[index] if index < len(body) else ""
            if escape not in _ESCAPES:
                raise AssemblyError(
                    line,
                    f"I do not know the escape \\{escape}: use \\n, \\t, \\0, \\\\, \\\" or \\'",
                )
            char = _ESCAPES[escape]
        out += char
        index += 1
    return out


def _check_letters(text: str, line: int) -> None:
    """Refuse a character that does not fit in one 16-bit word."""
    for char in text:
        if ord(char) > WORD_MASK:
            raise AssemblyError(
                line, f"the character {char!r} is too big to fit in one 16-bit word"
            )


def _register(text: str, line: int) -> int:
    """Read `r0` to `r7` (any case) as a register number."""
    match = re.fullmatch(r"[rR]([0-9]+)", text)
    if match and int(match.group(1)) < REGISTER_COUNT and len(match.group(1)) == 1:
        return int(match.group(1))
    if match:
        raise AssemblyError(line, f"{text} is not a register. The registers are {_REGISTER_LIST}.")
    raise AssemblyError(
        line,
        f"I expected a register like r1 here, but found {text!r}. The registers are {_REGISTER_LIST}.",
    )


def _number(text: str, line: int) -> int:
    """Read a decimal, `-` decimal, `0x` hex or `'A'` character as a number."""
    if re.fullmatch(r"-?[0-9]+", text, flags=re.ASCII):
        sign, digits = (-1, text[1:]) if text[0] == "-" else (1, text)
        return sign * _decimal(digits, 10, line)
    if re.fullmatch(r"-?0[xX][0-9a-fA-F]+", text):
        sign, digits = (-1, text[1:]) if text[0] == "-" else (1, text)
        return sign * _decimal(digits[2:], 16, line)
    if len(text) >= MIN_CHAR_LITERAL and text[0] == text[-1] == "'":
        letters = _unescape(text[1:-1], line)
        if len(letters) != 1:
            raise AssemblyError(line, f"{text} should hold exactly one letter, like 'A'")
        _check_letters(letters, line)
        return ord(letters)
    raise AssemblyError(
        line,
        f"{text!r} is not a number. Write it like 12, -3, 0x1F or a letter in quotes like 'A'.",
    )


def _decimal(digits: str, base: int, line: int) -> int:
    """Convert digits, refusing absurdly long ones before Python is asked to convert them."""
    if len(digits.lstrip("0")) > MAX_DIGITS:
        raise AssemblyError(
            line, f"that number has more than {MAX_DIGITS} digits, which is far too big for a word"
        )
    return int(digits, base)


def _within(value: int, low: int, high: int, what: str, line: int) -> int:
    """Return `value` if it is from `low` to `high`, else explain the allowed range."""
    if not low <= value <= high:
        raise AssemblyError(
            line, f"{value} does not fit in {what}: use a number from {low} to {high}"
        )
    return value


def _memory(text: str, line: int) -> tuple[int, int]:
    """Read `[ra]`, `[ra+n]` or `[ra-n]` into (register, offset)."""
    if not (text.startswith("[") and text.endswith("]")):
        raise AssemblyError(
            line,
            f"I expected a memory spot in square brackets like [r2], [r2+3] or [r2-1], but found {text!r}",
        )
    inside = text[1:-1].strip()
    cut = min((i for i in (inside.find("+"), inside.find("-")) if i > 0), default=-1)
    if cut < 0:
        return _register(inside, line), 0
    offset_text = inside[cut + 1 :].strip()
    if not offset_text or offset_text[0] in "+-":
        raise AssemblyError(
            line, f"I expected a plain number after {inside[cut]} in {text}, like [r2+3]"
        )
    offset = _number(offset_text, line) * (1 if inside[cut] == "+" else -1)
    offset = _within(offset, OFF6_MIN, OFF6_MAX, "a memory offset", line)
    return _register(inside[:cut].strip(), line), offset


def _parse_line(text: str) -> tuple[list[str], str, list[str]]:
    """Split a tidy line into (labels, name, operands). The name is lower case; it may be empty."""
    labels: list[str] = []
    while match := re.match(r"\s*([^\s:]+)\s*:", text):
        labels.append(match.group(1))
        text = text[match.end() :]
    text = text.strip()
    parts = re.split(r"\s+", text, maxsplit=1)
    name, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    return labels, name.lower(), _split_operands(rest.strip())


def _size(name: str, operands: list[str], line: int) -> int:
    """Count the words a line will become, for pass 1."""
    if name == "set":
        return 2
    if name == ".word":
        return max(len(operands), 1)
    if name == ".string":
        return len(_string_text(operands, line)) + 1
    if name in _SHAPES or name == "halt":
        return 1
    raise AssemblyError(
        line,
        f"I do not know the instruction {name!r}. Check the spelling against the Instruction Set page.",
    )


def _string_text(operands: list[str], line: int) -> str:
    """Read the one quoted text that `.string` needs."""
    if len(operands) != 1 or not (
        len(operands[0]) >= MIN_QUOTED and operands[0][0] == operands[0][-1] == '"'
    ):
        raise AssemblyError(
            line, '.string needs one piece of text in double quotes, like .string "Hi"'
        )
    letters = _unescape(operands[0][1:-1], line)
    _check_letters(letters, line)
    return letters


def _pass_one(source: str, words: int) -> tuple[list[_Item], dict[str, int]]:
    """Walk the text once, finding where every label is and how big every line is."""
    items: list[_Item] = []
    labels: dict[str, int] = {}
    address = 0
    for number, raw in enumerate(source.split("\n"), start=1):
        code = _strip_comment(raw, number)
        found, name, operands = _parse_line(code)
        for label in found:
            _define(label, address, labels, number)
        if not name:
            continue
        size = _size(name, operands, number)
        if address + size > words:
            raise AssemblyError(
                number,
                f"the program is too long: it must fit in {words} words of memory, and this line goes past the end",
            )
        items.append(_Item(number, address, name, tuple(operands), size))
        address += size
    return items, labels


def _define(label: str, address: int, labels: dict[str, int], line: int) -> None:
    """Record a label, refusing bad names, register names, and repeats."""
    if not re.fullmatch(_NAME, label, flags=re.ASCII):
        raise AssemblyError(
            line,
            f"{label!r} is not a good label name: use letters, digits and _, and do not start with a digit",
        )
    if re.fullmatch(r"[rR][0-7]", label):
        raise AssemblyError(
            line, f"{label} is a register name, so it cannot also be a label: pick another name"
        )
    if label in labels:
        raise AssemblyError(
            line, f"the label {label} is already used: every label needs its own name"
        )
    labels[label] = address


def _value(text: str, labels: dict[str, int], line: int) -> int:
    """Read a label or a number (an address, or a value for `set` and `.word`)."""
    if re.fullmatch(_NAME, text, flags=re.ASCII):
        if text not in labels:
            raise AssemblyError(
                line,
                f"I do not know a label called {text}: write {text}: on the line it should mark",
            )
        return labels[text]
    return _number(text, line)


def _condition(text: str, line: int) -> Condition:
    """Read a branch condition name such as `eq` or `NE`."""
    try:
        return Condition[text.upper()]
    except KeyError:
        names = ", ".join(c.name.lower() for c in Condition)
        raise AssemblyError(
            line, f"{text!r} is not a branch condition. Use one of: {names}"
        ) from None


def _expand(item: _Item, labels: dict[str, int]) -> list[int]:
    """Turn one source line into its machine words (pass 2)."""
    line, name, ops = item.line, item.name, list(item.operands)
    if name == ".string":
        return [*(ord(c) for c in _string_text(ops, line)), 0]
    if name == ".word":
        if not ops or not all(ops):
            raise AssemblyError(line, ".word needs a number or a label, like .word 7")
        return [
            _within(_value(op, labels, line), SIGNED_WORD_MIN, WORD_MASK, "a 16-bit word", line)
            & WORD_MASK
            for op in ops
        ]
    if name == "halt":
        if len(ops) > 1 or (ops and not ops[0]):
            raise AssemblyError(line, "halt takes at most one number, like halt or halt 3")
        code = _within(_number(ops[0], line), 0, BYTE_MAX, "a halt code", line) if ops else 0
        return [encode(Opcode.HALT, imm=code)]
    shape, example = _SHAPES[name]
    if len(ops) != len(shape) or not all(ops):
        raise AssemblyError(
            line,
            f"{name} needs {len(shape)} thing{'s' if len(shape) != 1 else ''} after it, "
            f"like {example.format(name)}, but I found {len(ops) if all(ops) else 'a missing one'}",
        )
    return [_encode(item, shape, labels)] if name != "set" else _encode_set(ops, labels, line)


def _encode_set(ops: list[str], labels: dict[str, int], line: int) -> list[int]:
    """Expand `set rd, value` into `li` (low byte) then `lhi` (high byte)."""
    rd = _register(ops[0], line)
    value = _within(_value(ops[1], labels, line), SIGNED_WORD_MIN, WORD_MASK, "a 16-bit word", line)
    value &= WORD_MASK
    return [
        encode(Opcode.LI, rd=rd, imm=value & BYTE_MAX),
        encode(Opcode.LHI, rd=rd, imm=value >> IMM8_BITS),
    ]


def _encode(item: _Item, shape: tuple[str, ...], labels: dict[str, int]) -> int:
    """Encode one ordinary instruction whose operand count is already right."""
    line, name, ops = item.line, item.name, item.operands
    reads: dict[str, Callable[[str], int]] = {
        "reg": lambda t: _register(t, line),
        "num": lambda t: _number(t, line),
        "val": lambda t: _value(t, labels, line),
        "cond": lambda t: _condition(t, line),
    }
    if "mem" in shape:
        register, base = _register(ops[0], line), _memory(ops[1], line)
        return encode(_SIMPLE_OPCODES[name], rd=register, ra=base[0], imm=base[1])
    values = [reads[kind](op) for kind, op in zip(shape, ops, strict=True)]
    first = values[0] if values else 0
    match name:
        case _ if name in _ALU_NAMES:
            word = encode(Opcode.ALU, rd=first, ra=values[1], rb=values[2], fn=_ALU_NAMES[name])
        case _ if name in _SHIFT_NAMES:
            word = encode(Opcode.ALU, rd=first, ra=values[1], fn=_SHIFT_NAMES[name])
        case "mov":
            word = encode(Opcode.ALU, rd=first, rb=values[1], fn=AluOp.PASS_B)
        case "cmp":
            word = encode(Opcode.CMP, ra=first, rb=values[1])
        case "br":
            word = encode(Opcode.BR, rd=first, imm=_branch_offset(values[1], item.address, line))
        case "jmp" | "call":
            word = encode(
                _SIMPLE_OPCODES[name], imm=_within(first, 0, ADDR12_MAX, "a jump address", line)
            )
        case "li" | "lhi":
            word = encode(
                _SIMPLE_OPCODES[name], rd=first, imm=_within(values[1], 0, BYTE_MAX, "8 bits", line)
            )
        case "addi":
            imm = _within(values[1], IMM8_SIGNED_MIN, IMM8_SIGNED_MAX, "addi", line)
            word = encode(Opcode.ADDI, rd=first, imm=imm)
        case _:
            word = encode(_SIMPLE_OPCODES[name], rd=first)
    return word


def _branch_offset(target: int, address: int, line: int) -> int:
    """Work out how far a `br` at `address` must hop to reach `target`."""
    if not 0 <= target <= MAX_ADDRESS:
        raise AssemblyError(
            line, f"{target} is not an address: use a number from 0 to {MAX_ADDRESS}"
        )
    distance = ((target - (address + 1) + (1 << (WORD_BITS - 1))) & WORD_MASK) - (
        1 << (WORD_BITS - 1)
    )
    if not OFF9_MIN <= distance <= OFF9_MAX:
        raise AssemblyError(
            line,
            f"that target is {distance} words from the next instruction, which is too far for br: "
            f"branch over a jmp instead (br reaches {OFF9_MIN} to {OFF9_MAX})",
        )
    return distance


def assemble(source: str, words: int = RAM_WORDS) -> Program:
    """Turn assembly text into machine code.

    Pass 1 finds every label; pass 2 writes the words. See the module docstring
    and the Assembly Language page for the syntax.

    Args:
        source: The assembly text, one instruction per line.
        words: How many words of memory the program must fit in.

    Returns:
        The words, the labels and the source line of every word.

    Raises:
        AssemblyError: On any mistake in the text; the message starts `line N:`.

    """
    items, labels = _pass_one(source, words)
    machine_words: list[int] = []
    lines: list[int] = []
    for item in items:
        expanded = _expand(item, labels)
        machine_words.extend(expanded)
        lines.extend([item.line] * len(expanded))
    return Program(tuple(machine_words), labels, tuple(lines))


def _memory_text(register: int, offset: int) -> str:
    """Write a memory operand the way the assembler reads it."""
    sign = "" if offset == 0 else f"{'+' if offset > 0 else '-'}{abs(offset)}"
    return f"[r{register}{sign}]"


def disassemble(word: int, address: int) -> str:
    """Turn one machine word back into assembly text the assembler accepts.

    The text is always in the same neat shape (lower case, `[r2-1]`). A `br`
    shows its absolute target, so this needs the `address` the word sits at.
    Labels and comments cannot come back: the word never held them.

    Args:
        word: The 16-bit machine word.
        address: Where the word sits in memory.

    """
    i: Instruction = decode(word)
    rd, ra, rb = f"r{i.rd}", f"r{i.ra}", f"r{i.rb}"
    text: str
    names = {**{v: k for k, v in _ALU_NAMES.items()}, **{v: k for k, v in _SHIFT_NAMES.items()}}
    match i.opcode:
        case Opcode.ALU if i.fn == AluOp.PASS_B:
            text = f"mov {rd}, {rb}"
        case Opcode.ALU if i.fn in _SHIFT_NAMES.values():
            text = f"{names[AluOp(i.fn)]} {rd}, {ra}"
        case Opcode.ALU:
            text = f"{names[AluOp(i.fn)]} {rd}, {ra}, {rb}"
        case Opcode.CMP:
            text = f"cmp {ra}, {rb}"
        case Opcode.LOAD | Opcode.STORE:
            text = f"{i.opcode.name.lower()} {rd}, {_memory_text(i.ra, i.imm)}"
        case Opcode.BR:
            target = (address + 1 + i.imm) & WORD_MASK
            return f"br {Condition(i.rd).name.lower()}, {target}"
        case Opcode.RET:
            text = "ret"
        case Opcode.JMP | Opcode.CALL:
            text = f"{i.opcode.name.lower()} {i.imm}"
        case Opcode.HALT:
            text = "halt" if i.imm == 0 else f"halt {i.imm}"
        case Opcode.PUSH | Opcode.POP | Opcode.GETSP | Opcode.SETSP:
            text = f"{i.opcode.name.lower()} {rd}"
        case _:
            text = f"{i.opcode.name.lower()} {rd}, {i.imm}"
    return text
