"""Conformance: a Pebble program must print the same on PyCPU as on Pebble's own VM.

Think of two pianos playing from the same sheet of music: a grand piano in a
concert hall (Pebble's VM, written in Python) and a home-made one built from
string and wood (PyCPU, built from NAND gates). If they ever play a different
note, the home-made one has a fault, and we fix the piano, never the music.

Four kinds of check live here:

- the corpus: every small program in `tests/pebble_programs/` prints the same on
  both machines, and the two that divide by zero stop on the same line;
- random programs: Hypothesis writes programs from a small grammar (lets,
  assignments, arithmetic with small numbers, `if`/`else if`/`else`, counted
  `while` and `for` loops, `and`/`or`/`not`, functions and prints) and both
  machines must agree on every one;
- unsupported programs: the same programs with things PyCPU cannot do mixed in
  (decimals, `/`, lists, text in variables, closures, built-ins, stored
  booleans and more); the translator must refuse them politely, or run them and
  agree with the VM, and never crash;
- one gate run (slow): the shortest corpus program on the real gate-built
  computer and on the fast engine, which must end in exactly the same state.

Two honest limits. Integers on PyCPU are 16 bits and wrap, while Pebble's are
unbounded, so random programs are worked out in Python first (here, in the test,
never in the translator) and any program with a value outside -32768..32767 is
thrown away. And Pebble v0.4.0's VM has a known bug: a function whose last
statement is an `if` containing `return` crashes the VM with an `IndexError`
when the condition is false (PyCPU correctly returns null). The fix is merged
for Pebble v0.4.1; until it is released, the corpus avoids that shape and every
generated function ends with an unconditional `return`.
"""

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import pebble
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pycpu.cpu import GateMachine
from pycpu.fast import FastMachine
from pycpu.isa import Fault
from pycpu.translator import PebbleRun, UnsupportedFeature, run_pebble, translate

PROGRAMS = Path(__file__).parent / "pebble_programs"
CORPUS = sorted(PROGRAMS.glob("*.pebble"))
DIVIDE_BY_ZERO_PROGRAMS = ("divide_by_zero.pebble", "modulo_by_zero_in_function.pebble")
CORPUS_MIN = 12

SMALLEST = -32768
BIGGEST = 32767
LITERAL_MAX = 9
SMALL_LITERAL = 2
LOOP_MAX = 3
RANGE_SPAN = 4
EXPRESSION_DEPTH = 2
BLOCK_DEPTH = 2
BLOCK_MAX = 4
PROGRAM_MIN = 3
PROGRAM_MAX = 7
FUNCTION_MAX = 2
PARAMETER_MAX = 3
RANDOM_EXAMPLES = 200

GATE_ADDRESS_BITS = 12
GATE_STEP_LIMIT = 1_500
GATE_TIMEOUT_SECONDS = 600


def assert_same_behaviour(source: str) -> PebbleRun:
    """Run `source` on both machines and check they behave the same.

    If the VM finishes, PyCPU must finish with no fault and the same output. If the
    VM stops with an error, PyCPU must stop with a fault on the same line, having
    printed the same text before it stopped.
    """
    printed = io.StringIO()
    run = run_pebble(source)
    vm_error: pebble.PebbleError | None = None
    try:
        pebble.run_source(source, output=printed)
    except pebble.PebbleError as error:
        vm_error = error
    assert run.output == printed.getvalue()
    if vm_error is None:
        assert run.halted
        assert run.fault is None, run.describe()
    else:
        assert run.fault is not None, f"the VM failed ({vm_error}) but PyCPU did not"
        assert run.line == vm_error.line
    return run


# ---------------------------------------------------------------------------
# The corpus
# ---------------------------------------------------------------------------


def test_the_corpus_is_big_enough() -> None:
    """There are at least 12 programs, the two divide-by-zero ones among them."""
    names = {path.name for path in CORPUS}
    assert len(names) >= CORPUS_MIN + len(DIVIDE_BY_ZERO_PROGRAMS)
    assert set(DIVIDE_BY_ZERO_PROGRAMS) <= names


@pytest.mark.parametrize("path", CORPUS, ids=[path.stem for path in CORPUS])
def test_corpus_matches_the_pebble_vm(path: Path) -> None:
    """Each corpus program prints the same on PyCPU and the VM, or fails on the same line."""
    run = assert_same_behaviour(path.read_text())
    if path.name in DIVIDE_BY_ZERO_PROGRAMS:
        assert run.fault is Fault.DIVIDE_BY_ZERO
    else:
        assert run.fault is None


# ---------------------------------------------------------------------------
# A tiny grammar of Pebble programs, with a Python model of what they do
# ---------------------------------------------------------------------------


class OutOfRangeError(Exception):
    """A value left 16-bit range, so PyCPU would wrap where the VM does not."""


class DivideByZeroError(Exception):
    """The program divides by zero here, so both machines must stop on this line."""


def _checked(value: int) -> int:
    """Return `value`, or raise `OutOfRangeError` if it does not fit in 16 bits."""
    if not SMALLEST <= value <= BIGGEST:
        raise OutOfRangeError
    return value


@dataclass(frozen=True)
class Num:
    """A small number written in the program, like `7` or `(-3)`."""

    value: int


@dataclass(frozen=True)
class Var:
    """A variable read, like `v0`."""

    name: str


@dataclass(frozen=True)
class Neg:
    """A minus sign in front of an expression, like `-(v0)`."""

    operand: Expr


@dataclass(frozen=True)
class Bin:
    """Two expressions joined by `+`, `-`, `*`, `//` or `%`."""

    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Call:
    """A call to one of the program's own functions, used for its answer."""

    name: str
    args: tuple[Expr, ...]


type Expr = Num | Var | Neg | Bin | Call


@dataclass(frozen=True)
class Cmp:
    """A comparison such as `v0 < 3`, which makes true or false."""

    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Logic:
    """`and` or `or` between two conditions."""

    op: str
    left: Cond
    right: Cond


@dataclass(frozen=True)
class Not:
    """`not` in front of a condition."""

    operand: Cond


@dataclass(frozen=True)
class Truth:
    """The words `true` or `false`, used directly as a condition."""

    value: bool


type Cond = Cmp | Logic | Not | Truth


@dataclass(frozen=True)
class Let:
    """`let name = expr`: make a new variable."""

    name: str
    value: Expr


@dataclass(frozen=True)
class Assign:
    """`name = expr`: change a variable."""

    name: str
    value: Expr


@dataclass(frozen=True)
class Print:
    """`print(expr)`: print a number."""

    value: Expr


@dataclass(frozen=True)
class PrintText:
    """`print("...")`: print some text."""

    text: str


@dataclass(frozen=True)
class If:
    """`if`, any number of `else if`s, and maybe an `else`."""

    branches: tuple[tuple[Cond, tuple[Stmt, ...]], ...]
    otherwise: tuple[Stmt, ...] | None


@dataclass(frozen=True)
class While:
    """A `while` loop held to at most `limit` passes by its own counter.

    It reads `let counter = 0`, then `while counter < limit and cond { ... }`,
    with `counter = counter + 1` as the body's last line.
    """

    counter: str
    limit: int
    cond: Cond | None
    body: tuple[Stmt, ...]


@dataclass(frozen=True)
class For:
    """`for name in range(start, stop) { ... }`."""

    name: str
    start: int
    stop: int
    body: tuple[Stmt, ...]


@dataclass(frozen=True)
class CallStmt:
    """A call used as a statement, for what it prints; its answer is thrown away."""

    call: Call


@dataclass(frozen=True)
class Raw:
    """Lines of Pebble the model does not follow (used for unsupported constructs)."""

    text: str


type Stmt = Let | Assign | Print | PrintText | If | While | For | CallStmt | Raw


@dataclass(frozen=True)
class Function:
    """`fn name(params) { body; return result }`, always ending in a plain `return`."""

    name: str
    params: tuple[str, ...]
    body: tuple[Stmt, ...]
    result: Expr


@dataclass(frozen=True)
class Script:
    """A whole program: its functions, then its top-level statements."""

    functions: tuple[Function, ...]
    main: tuple[Stmt, ...]


# --- Writing a program out as Pebble text -----------------------------------


def render_expr(expr: Expr) -> str:
    """Write an expression with brackets everywhere, so no precedence can surprise us."""
    match expr:
        case Num(value):
            return f"({value})" if value < 0 else str(value)
        case Var(name):
            return name
        case Neg(operand):
            return f"-({render_expr(operand)})"
        case Bin(op, left, right):
            return f"({render_expr(left)} {op} {render_expr(right)})"
        case Call(name, args):
            return f"{name}({', '.join(render_expr(arg) for arg in args)})"


def render_cond(cond: Cond) -> str:
    """Write a condition, bracketed like `render_expr`."""
    match cond:
        case Cmp(op, left, right):
            return f"({render_expr(left)} {op} {render_expr(right)})"
        case Logic(op, left, right):
            return f"({render_cond(left)} {op} {render_cond(right)})"
        case Not(operand):
            return f"(not {render_cond(operand)})"
        case Truth(value):
            return "true" if value else "false"


def render_block(stmts: Sequence[Stmt], indent: str) -> list[str]:
    """Write statements as lines, each starting with `indent`."""
    lines: list[str] = []
    for stmt in stmts:
        lines.extend(render_stmt(stmt, indent))
    return lines


def render_line(stmt: Let | Assign | Print | PrintText | CallStmt) -> str:
    """Write a one-line statement, without its indent."""
    match stmt:
        case Let(name, value):
            return f"let {name} = {render_expr(value)}"
        case Assign(name, value):
            return f"{name} = {render_expr(value)}"
        case Print(value):
            return f"print({render_expr(value)})"
        case PrintText(text):
            return f'print("{text}")'
        case CallStmt(call):
            return render_expr(call)


def render_stmt(stmt: Stmt, indent: str) -> list[str]:
    """Write one statement as one or more lines."""
    inner = indent + "    "
    match stmt:
        case If(branches, otherwise):
            lines: list[str] = []
            for number, (cond, body) in enumerate(branches):
                opener = "if" if number == 0 else "} else if"
                lines.append(f"{indent}{opener} {render_cond(cond)} {{")
                lines.extend(render_block(body, inner))
            if otherwise is not None:
                lines.append(f"{indent}}} else {{")
                lines.extend(render_block(otherwise, inner))
            lines.append(f"{indent}}}")
            return lines
        case While(counter, limit, cond, body):
            test = f"{counter} < {limit}"
            if cond is not None:
                test = f"{test} and {render_cond(cond)}"
            return [
                f"{indent}let {counter} = 0",
                f"{indent}while {test} {{",
                *render_block(body, inner),
                f"{inner}{counter} = {counter} + 1",
                f"{indent}}}",
            ]
        case For(name, start, stop, body):
            return [
                f"{indent}for {name} in range({start}, {stop}) {{",
                *render_block(body, inner),
                f"{indent}}}",
            ]
        case Raw(text):
            return [indent + line for line in text.splitlines()]
        case _:
            return [indent + render_line(stmt)]


def render(script: Script) -> str:
    """Write a whole program as Pebble source."""
    lines: list[str] = []
    for function in script.functions:
        lines.append(f"fn {function.name}({', '.join(function.params)}) {{")
        lines.extend(render_block(function.body, "    "))
        lines.append(f"    return {render_expr(function.result)}")
        lines.append("}")
    lines.extend(render_block(script.main, ""))
    return "\n".join(lines)


# --- Working a program out in Python, only to check its range ----------------


class Model:
    """Follow a generated program in Python, raising if any value leaves 16-bit range.

    This is a test helper. It never feeds the translator; it only decides which
    random programs are fair to compare, because a wrapping PyCPU and a never-
    wrapping VM are allowed to differ outside 16-bit range.
    """

    def __init__(self, script: Script) -> None:
        """Remember the program's functions by name."""
        self.functions = {function.name: function for function in script.functions}

    def expr(self, expr: Expr, env: dict[str, int]) -> int:
        """Work out an expression, checking every value along the way."""
        match expr:
            case Num(value):
                return _checked(value)
            case Var(name):
                return env[name]
            case Neg(operand):
                return _checked(-self.expr(operand, env))
            case Bin(op, left, right):
                return _checked(self._arith(op, self.expr(left, env), self.expr(right, env)))
            case Call(name, args):
                return self.call(name, [self.expr(arg, env) for arg in args])

    @staticmethod
    def _arith(op: str, a: int, b: int) -> int:
        """Do one arithmetic step the way Pebble does (`//` and `%` round down)."""
        if op in {"//", "%"} and b == 0:
            raise DivideByZeroError
        operations: dict[str, Callable[[int, int], int]] = {
            "+": lambda x, y: x + y,
            "-": lambda x, y: x - y,
            "*": lambda x, y: x * y,
            "//": lambda x, y: x // y,
            "%": lambda x, y: x % y,
        }
        return operations[op](a, b)

    def cond(self, cond: Cond, env: dict[str, int]) -> bool:
        """Work out a condition, skipping the right side of `and`/`or` when Pebble does."""
        match cond:
            case Cmp(op, left, right):
                a, b = self.expr(left, env), self.expr(right, env)
                comparisons: dict[str, Callable[[int, int], bool]] = {
                    "<": lambda x, y: x < y,
                    "<=": lambda x, y: x <= y,
                    ">": lambda x, y: x > y,
                    ">=": lambda x, y: x >= y,
                    "==": lambda x, y: x == y,
                    "!=": lambda x, y: x != y,
                }
                return comparisons[op](a, b)
            case Logic("and", left, right):
                return self.cond(left, env) and self.cond(right, env)
            case Logic(_, left, right):
                return self.cond(left, env) or self.cond(right, env)
            case Not(operand):
                return not self.cond(operand, env)
            case Truth(value):
                return value

    def call(self, name: str, args: list[int]) -> int:
        """Run a function in a fresh set of variables and return its answer."""
        function = self.functions[name]
        env = dict(zip(function.params, args, strict=True))
        self.block(function.body, env)
        return self.expr(function.result, env)

    def block(self, stmts: Sequence[Stmt], env: dict[str, int]) -> None:
        """Run statements in order."""
        for stmt in stmts:
            self.stmt(stmt, env)

    def stmt(self, stmt: Stmt, env: dict[str, int]) -> None:
        """Run one statement."""
        match stmt:
            case Let(name, value) | Assign(name, value):
                env[name] = self.expr(value, env)
            case Print(value):
                self.expr(value, env)
            case If(branches, otherwise):
                for cond, body in branches:
                    if self.cond(cond, env):
                        self.block(body, env)
                        return
                if otherwise is not None:
                    self.block(otherwise, env)
            case While(counter, limit, cond, body):
                env[counter] = 0
                while env[counter] < limit and (cond is None or self.cond(cond, env)):
                    self.block(body, env)
                    env[counter] += 1
            case For(name, start, stop, body):
                for value in range(start, stop):
                    env[name] = value
                    self.block(body, env)
            case CallStmt(call):
                self.expr(call, env)
            case PrintText() | Raw():
                pass

    def run(self, script: Script) -> None:
        """Run the whole program's top level."""
        self.block(script.main, {})


def fair_to_compare(script: Script) -> bool:
    """Say whether every value the program makes stays in 16-bit range.

    A program that divides by zero is fair: it stops there on both machines, so
    whatever would have come after never happens.
    """
    try:
        Model(script).run(script)
    except OutOfRangeError:
        return False
    except DivideByZeroError:
        return True
    return True


# --- Drawing random programs --------------------------------------------------


@dataclass
class Names:
    """Hand out fresh names, so no two `let`s in a program share one."""

    count: int = 0

    def fresh(self, prefix: str) -> str:
        """Return a name never handed out before, like `v3`."""
        self.count += 1
        return f"{prefix}{self.count}"


@dataclass(frozen=True)
class Scope:
    """What a piece of a program can see: variables to read, variables to change, functions."""

    readable: tuple[str, ...]
    writable: tuple[str, ...]
    functions: tuple[tuple[str, int], ...]

    def with_var(self, name: str, *, writable: bool = True) -> Scope:
        """Return this scope with one more variable in it."""
        return Scope(
            (*self.readable, name),
            (*self.writable, name) if writable else self.writable,
            self.functions,
        )


ARITHMETIC = ("+", "-", "*", "//", "%")
COMPARISONS = ("<", "<=", ">", ">=", "==", "!=")
WORDS = ("hello", "ok", "Lift off!", "x = 1", "tab\\there", "")


def draw_leaf(draw: st.DrawFn, scope: Scope) -> Expr:
    """Draw a number or, more often, a variable.

    Variables matter: Pebble's compiler works out sums of plain numbers itself, so
    an expression of numbers alone reaches PyCPU as one finished number. Numbers
    near zero are drawn most often, so two sides of a comparison are often equal
    and the `<` versus `<=` edge really gets tested.
    """
    numbers = st.integers(-SMALL_LITERAL, SMALL_LITERAL) | st.integers(-LITERAL_MAX, LITERAL_MAX)
    if scope.readable and draw(st.integers(0, 2)) != 1:
        return Var(draw(st.sampled_from(scope.readable)))
    return Num(draw(numbers))


def draw_expr(draw: st.DrawFn, scope: Scope, depth: int = EXPRESSION_DEPTH) -> Expr:
    """Draw an expression of at most `depth` levels."""
    if depth == 0:
        return draw_leaf(draw, scope)
    kind = draw(st.sampled_from(("bin", "leaf", "call", "bin", "neg")))
    if kind == "neg":
        return Neg(draw_expr(draw, scope, depth - 1))
    if kind == "bin":
        op = draw(st.sampled_from(ARITHMETIC))
        left = draw_expr(draw, scope, depth - 1)
        if op in {"//", "%"} and draw(st.integers(0, 3)) != 1:
            # Most of the time the divisor is a number that is not zero, or most programs
            # would stop at their first division and never reach the rest.
            nonzero = st.integers(-LITERAL_MAX, LITERAL_MAX).filter(bool)
            return Bin(op, left, Num(draw(nonzero)))
        return Bin(op, left, draw_expr(draw, scope, depth - 1))
    if kind == "call" and scope.functions:
        return draw_call(draw, scope, depth)
    return draw_leaf(draw, scope)


def draw_call(draw: st.DrawFn, scope: Scope, depth: int = EXPRESSION_DEPTH) -> Call:
    """Draw a call to one of the functions in scope, with the right number of arguments."""
    name, arity = draw(st.sampled_from(scope.functions))
    return Call(name, tuple(draw_expr(draw, scope, depth - 1) for _ in range(arity)))


def draw_cond(draw: st.DrawFn, scope: Scope, depth: int = 1) -> Cond:
    """Draw a condition: a comparison, `true`/`false`, or `and`/`or`/`not` of those."""
    kind = draw(st.sampled_from(("cmp", "cmp", "cmp", "and", "or", "not", "truth")))
    if kind == "truth":
        return Truth(draw(st.booleans()))
    if depth > 0 and kind in {"and", "or"}:
        return Logic(kind, draw_cond(draw, scope, depth - 1), draw_cond(draw, scope, depth - 1))
    if depth > 0 and kind == "not":
        return Not(draw_cond(draw, scope, depth - 1))
    op = draw(st.sampled_from(COMPARISONS))
    return Cmp(op, draw_leaf(draw, scope), draw_expr(draw, scope, 1))


def draw_block(
    draw: st.DrawFn, scope: Scope, names: Names, depth: int, size: int = BLOCK_MAX, least: int = 1
) -> tuple[Stmt, ...]:
    """Draw `least` to `size` statements; a `let` makes its name visible to the rest of the block."""
    stmts: list[Stmt] = []
    for _ in range(draw(st.integers(least, size))):
        stmt, scope = draw_stmt(draw, scope, names, depth)
        stmts.append(stmt)
    return tuple(stmts)


def draw_stmt(draw: st.DrawFn, scope: Scope, names: Names, depth: int) -> tuple[Stmt, Scope]:
    """Draw one statement and return it with the scope that follows it.

    Only a `let` changes the scope: the variable it makes can be used afterwards.
    """
    # Hypothesis leans towards the first choice in a list, so the richer kinds come first.
    kinds = ["if", "while", "for"] if depth > 0 else []
    if scope.writable:
        kinds += ["assign", "assign"]
    kinds += ["let", "print", "print", "text"]
    if scope.functions:
        kinds.append("call")
    kind = draw(st.sampled_from(kinds))
    if kind == "let":
        name = names.fresh("v")
        return Let(name, draw_expr(draw, scope)), scope.with_var(name)
    if kind in {"if", "while", "for"}:
        return draw_compound(draw, kind, scope, names, depth), scope
    return draw_simple(draw, kind, scope), scope


def draw_simple(draw: st.DrawFn, kind: str, scope: Scope) -> Stmt:
    """Draw a one-line statement of the given kind: an assignment, a print or a call."""
    if kind == "assign":
        return Assign(draw(st.sampled_from(scope.writable)), draw_expr(draw, scope))
    if kind == "print":
        return Print(draw_expr(draw, scope))
    if kind == "text":
        return PrintText(draw(st.sampled_from(WORDS)))
    return CallStmt(draw_call(draw, scope))


def draw_compound(draw: st.DrawFn, kind: str, scope: Scope, names: Names, depth: int) -> Stmt:
    """Draw an `if`, a counted `while` or a `for`, with blocks one level shallower."""
    if kind == "if":
        count = draw(st.integers(1, 3))
        branches = tuple(
            (draw_cond(draw, scope), draw_block(draw, scope, names, depth - 1, 2))
            for _ in range(count)
        )
        otherwise = draw_block(draw, scope, names, depth - 1, 2) if draw(st.booleans()) else None
        return If(branches, otherwise)
    if kind == "while":
        counter = names.fresh("c")
        # The counter can be read inside the loop but never changed, so the loop must end.
        inner = scope.with_var(counter, writable=False)
        cond = draw_cond(draw, inner) if draw(st.booleans()) else None
        body = draw_block(draw, inner, names, depth - 1, 3)
        return While(counter, draw(st.integers(1, LOOP_MAX)), cond, body)
    name = names.fresh("i")
    start = draw(st.integers(-LITERAL_MAX, LITERAL_MAX))
    stop = start + draw(st.integers(0, RANGE_SPAN))
    body = draw_block(draw, scope.with_var(name, writable=False), names, depth - 1, 3)
    return For(name, start, stop, body)


@st.composite
def scripts(draw: st.DrawFn) -> Script:
    """Draw a whole program: up to two functions, then the top level."""
    names = Names()
    functions: list[Function] = []
    known: tuple[tuple[str, int], ...] = ()
    for _ in range(draw(st.integers(0, FUNCTION_MAX))):
        name = names.fresh("f")
        params = tuple(names.fresh("p") for _ in range(draw(st.integers(1, PARAMETER_MAX))))
        # A function sees only its own parameters and the functions defined above it.
        scope = Scope(params, params, known)
        body = draw_block(draw, scope, names, 1, 3)
        functions.append(Function(name, params, body, draw_expr(draw, scope)))
        known = (*known, (name, len(params)))
    main = draw_block(draw, Scope((), (), known), names, BLOCK_DEPTH, PROGRAM_MAX, PROGRAM_MIN)
    # Print every top-level variable at the end, so a wrong turn anywhere shows up.
    finale = tuple(Print(Var(stmt.name)) for stmt in main if isinstance(stmt, Let))
    return Script(tuple(functions), main + finale)


fair_scripts = scripts().filter(fair_to_compare)


@given(fair_scripts)
@settings(max_examples=RANDOM_EXAMPLES, deadline=None)
def test_random_programs_match_the_pebble_vm(script: Script) -> None:
    """A random program in the subset prints the same on PyCPU as on the VM."""
    assert_same_behaviour(render(script))


# ---------------------------------------------------------------------------
# Unsupported constructs mixed in
# ---------------------------------------------------------------------------


def unsupported_snippets(a: int, b: int, big: int, tag: int) -> list[str]:
    """List a few lines for each thing outside PyCPU's subset (or right on its edge).

    `a` and `b` are small numbers, `big` is near the 16-bit edge and `tag` makes
    names unique. Each snippet makes its own names and leaves the rest of the
    program's variables alone, so the model can skip it.
    """
    return [
        f"let d{tag} = {abs(a)}.5\nprint(d{tag})",
        f"print({abs(a)}.25 + {b})",
        f"let q{tag} = {a}\nprint(q{tag} / 2)",
        f"print({a} / {b or 1})",
        f"let l{tag} = [{a}, {b}]\nprint(l{tag}[0])",
        f'let s{tag} = "pebble"\nprint(s{tag})',
        f'let n{tag} = {a}\nprint("n is {{n{tag}}}")',
        f'let m{tag} = {{"k": {a}}}\nprint(m{tag}["k"])',
        (
            f"fn outer{tag}() {{\n    let k = {a}\n    fn inner() {{\n        return k\n    }}\n"
            f"    return inner()\n}}\nprint(outer{tag}())"
        ),
        f"fn g{tag}(n) {{\n    return n\n}}\nlet h{tag} = g{tag}\nprint(h{tag}({a}))",
        f'print(len("{"x" * abs(a)}"))',
        f"print(abs({a}))",
        f"let t{tag} = true\nif t{tag} {{\n    print({a})\n}}",
        f"let t{tag} = {a} < {b}\nif t{tag} {{\n    print(1)\n}}",
        f"print({a} == {b})",
        "print(true)",
        f"let w{tag} = {a}\nprint(w{tag} ** 2)",
        f"print({a} ** {abs(b) % 4})",
        f"let w{tag} = {a}\nprint(w{tag} & {b})",
        f"print({big})",
        f"print({big} - {abs(a)})",
        f"print({a} * 4000)",
        f"try {{\n    print({a})\n}} catch e {{\n    print({b})\n}}",
        f'print("abc".upper())\nprint({a})',
        f"for k{tag} in range(0, {abs(a) + 1}, 2) {{\n    print(k{tag})\n}}",
        f"fn z{tag}() {{\n    print({a})\n}}\nprint(z{tag}())",
        f"fn y{tag}() {{\n    print({a})\n}}\ny{tag}()",
        f"let e{tag} = {a}\nprint(e{tag} // 0)",
        f"print({a} % 0)",
    ]


SNIPPET_COUNT = len(unsupported_snippets(0, 0, 0, 0))


@st.composite
def snippets(draw: st.DrawFn) -> str:
    """Draw one unsupported snippet with random numbers in it."""
    a = draw(st.integers(-LITERAL_MAX, LITERAL_MAX))
    b = draw(st.integers(-LITERAL_MAX, LITERAL_MAX))
    big = draw(st.integers(BIGGEST - LITERAL_MAX, BIGGEST + LITERAL_MAX))
    tag = draw(st.integers(0, 99))
    return unsupported_snippets(a, b, big, tag)[draw(st.integers(0, SNIPPET_COUNT - 1))]


@st.composite
def mixed_scripts(draw: st.DrawFn) -> Script:
    """Draw a fair random program and slip one or two unsupported snippets into its top level."""
    script = draw(fair_scripts)
    main = list(script.main)
    for _ in range(draw(st.integers(1, 2))):
        position = draw(st.integers(0, len(main)))
        main.insert(position, Raw(draw(snippets())))
    return Script(script.functions, tuple(main))


def assert_refused_or_same(source: str) -> None:
    """Check `source` is refused with a friendly error, or runs exactly as on the VM."""
    refusal: UnsupportedFeature | None = None
    try:
        translate(source)
    except UnsupportedFeature as error:
        refusal = error
    except pebble.PebbleError:
        return  # Pebble's own checks found a mistake; it is passed through unchanged
    if refusal is None:
        assert_same_behaviour(source)
    else:
        assert refusal.feature
        assert "not supported on PyCPU yet" in str(refusal)


@given(mixed_scripts())
@settings(max_examples=RANDOM_EXAMPLES, deadline=None)
def test_unsupported_programs_never_crash(script: Script) -> None:
    """The translator refuses politely, or runs the program and agrees with the VM."""
    assert_refused_or_same(render(script))


@pytest.mark.parametrize("index", range(SNIPPET_COUNT))
@pytest.mark.parametrize(("a", "b", "big"), [(3, -2, BIGGEST), (-7, 0, BIGGEST + 1)])
def test_every_unsupported_snippet_is_refused_or_agrees(
    index: int, a: int, b: int, big: int
) -> None:
    """Hypothesis favours some snippets, so each one is also tried on its own, between prints."""
    snippet = unsupported_snippets(a, b, big, 0)[index]
    assert_refused_or_same(f"print(1)\n{snippet}\nprint(2)")


# ---------------------------------------------------------------------------
# One program on the real gates
# ---------------------------------------------------------------------------


def _shortest_corpus_program() -> tuple[str, int]:
    """Find the corpus program that finishes cleanly in the fewest steps."""
    finished = [
        (run.steps, path.read_text())
        for path in CORPUS
        if (run := run_pebble(path.read_text())).fault is None
    ]
    steps, source = min(finished)
    return source, steps


@pytest.mark.slow
@pytest.mark.timeout(GATE_TIMEOUT_SECONDS)
def test_a_translated_program_runs_the_same_on_gates() -> None:
    """The shortest corpus program ends in exactly the same state on gates as on the fast engine."""
    source, steps = _shortest_corpus_program()
    assert steps <= GATE_STEP_LIMIT
    words = translate(source).program.words
    fast = FastMachine()
    fast.load_program(words)
    gate = GateMachine(address_bits=GATE_ADDRESS_BITS)
    gate.load_program(words)
    assert fast.run(GATE_STEP_LIMIT) == gate.run(GATE_STEP_LIMIT) == steps
    finished = gate.state()
    assert finished.halted
    assert finished.halt_code == 0
    assert finished == fast.state()
    assert finished.output_text == pebble.run_source(source)
