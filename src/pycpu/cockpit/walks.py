"""Guided walks: short tours of the real machine, one sentence at a time.

Think of a museum audio guide. It tells you where to stand and what to look at, one
sentence at a time, and when the tour is over it lets you wander on your own. A walk
is the Cockpit's audio guide. Each one is a small TOML file in `walks/`: a program,
a list of steps (a move to make, a sentence to say, a depth for the glass to look at)
and a last "Now you try" task with a check the server can test on the real machine.

This module only reads and checks those files. It turns each action and each check
into a small value with an explicit grammar (`str.split` and `match`, never `eval`),
so a typo in a file is a `WalkError` naming the file and the problem. The moves
themselves are made by the session (`Cockpit.go_to_walk` and `Cockpit.act`), which
replays a walk from its `start` on the real machine, and never sets any state by hand.
"""

import tomllib
from dataclasses import dataclass
from functools import cache
from importlib import resources

from pycpu.cockpit.explain import Depth
from pycpu.state import WORD_BITS, MachineState
from pycpu.translator import FRAME_POINTER, TranslatedProgram

# The five walks, in the order the page lists them, matching the ideas in the spec.
WALK_ORDER = (
    "many-instructions",
    "where-n-lives",
    "subtracting-with-gates",
    "a-call-and-the-stack",
    "why-the-clock-ticks",
)

# What a step may highlight on the page: a key (or a key inside a key) of the picture.
SHOW_TARGETS = (
    "pebble.line",
    "variables",
    "registers",
    "memory",
    "stack",
    "output",
    "instruction",
    "flags",
    "last_gate",
    "happened",
)

_SIGN_BIT = 1 << (WORD_BITS - 1)
_WALK_KEYS = frozenset({"title", "example", "source", "see_also", "steps", "try"})
_STEP_KEYS = frozenset({"say", "do", "look", "show"})
_TRY_KEYS = frozenset({"task", "look", "check", "solution", "show", "step"})
TRY_STEP_KINDS = ("into",)  # the kinds of Step a try may ask the page to offer
_DEPTHS = ", ".join(d.value for d in Depth)


class WalkError(ValueError):
    """Say that a walk file, or one action or check in it, is not right, and why."""


@dataclass(frozen=True)
class Start:
    """Load the walk's program and pause at its start."""


@dataclass(frozen=True)
class StepAt:
    """Press Step once at `depth`, exactly as the learner's Step button does."""

    depth: Depth


@dataclass(frozen=True)
class StepLineInto:
    """Press Step into once at line depth: a line step that follows a call into a function."""


@dataclass(frozen=True)
class RunToLine:
    """Run on the fast engine until Pebble line `line` is about to start, then pause."""

    line: int


@dataclass(frozen=True)
class RunInstructions:
    """Press Run for `count` instructions: the fast engine runs them, then pauses."""

    count: int


@dataclass(frozen=True)
class StepGateUntil:
    """Take gate steps until a gate inside the part `prefix` (a scope path) works."""

    prefix: str


type Action = Start | StepAt | StepLineInto | RunToLine | RunInstructions | StepGateUntil


@dataclass(frozen=True)
class VariableIs:
    """Pass when the Pebble variable `name` of the running code holds `value`."""

    name: str
    value: int


@dataclass(frozen=True)
class LineIs:
    """Pass when Pebble line `line` is the one running."""

    line: int


@dataclass(frozen=True)
class RegisterIs:
    """Pass when register `r<index>` holds `value`."""

    index: int
    value: int


@dataclass(frozen=True)
class OutputContains:
    """Pass when the screen shows `text` somewhere."""

    text: str


@dataclass(frozen=True)
class Halted:
    """Pass once the program has stopped."""


type Check = VariableIs | LineIs | RegisterIs | OutputContains | Halted


@dataclass(frozen=True)
class WalkStep:
    """One step of a walk: the move to make, the sentence to say, and where to look.

    Attributes:
        say: The one sentence the page shows for this step.
        action: The move that takes the machine to this step, from the step before.
        look: The depth the glass shows.
        show: What the page highlights (one of `SHOW_TARGETS`), or None.

    """

    say: str
    action: Action
    look: Depth
    show: str | None


@dataclass(frozen=True)
class WalkTry:
    """A walk's "Now you try": a task, the check that says it is done, and a solution.

    Attributes:
        task: The one sentence that tells the learner what to do.
        look: The depth the glass shows while trying.
        check: The test, on the real machine, that the task is done.
        solution: Moves that do the task, so a test can prove it can be done.
        show: What the page highlights while trying, or None.
        step: `"into"` when the page should offer Step into (a line step that
            follows calls) for this task, else None for the plain Step.

    """

    task: str
    look: Depth
    check: Check
    solution: tuple[Action, ...]
    show: str | None
    step: str | None = None


@dataclass(frozen=True)
class Walk:
    """One guided walk, read from its file.

    Attributes:
        name: The file's name without `.toml`, such as `"many-instructions"`.
        title: The walk's title, the idea it teaches.
        source: The Pebble program it runs (an example's text, or its own).
        see_also: The concept page (without `.md`) that explains the same idea.
        steps: Its steps; the first is always `start`.
        trial: Its "Now you try".

    """

    name: str
    title: str
    source: str
    see_also: str
    steps: tuple[WalkStep, ...]
    trial: WalkTry


def _whole(text: str, what: str) -> int:
    """Read `text` as a whole number (it may start with a minus), or raise a `WalkError`."""
    digits = text.removeprefix("-")
    if not digits.isdigit():
        msg = f"{what} must be a whole number, not {text!r}"
        raise WalkError(msg)
    return int(text)


def _depth(text: object, where: str) -> Depth:
    """Read `text` as a depth, or raise a `WalkError` listing the depths."""
    if text not in tuple(Depth):
        msg = f"{where} must be one of {_DEPTHS}, not {text!r}"
        raise WalkError(msg)
    return Depth(str(text))


def parse_action(text: str) -> Action:
    """Read one action, such as `"step line"` or `"run to line 5"`.

    The actions are `start`, `step <depth>`, `step line into`, `run to line <n>`,
    `run <n> instructions` and `step gate until <scope prefix>`.

    Raises:
        WalkError: If the text is none of those.

    """
    match text.split():
        case ["start"]:
            return Start()
        case ["step", "line", "into"]:
            return StepLineInto()
        case ["step", "gate", "until", prefix]:
            return StepGateUntil(prefix)
        case ["step", depth]:
            return StepAt(_depth(depth, "the depth in a step"))
        case ["run", "to", "line", line]:
            number = _whole(line, "the line in run to line")
            if number < 1:
                msg = f"run to line needs a line from 1 up, not {number}"
                raise WalkError(msg)
            return RunToLine(number)
        case ["run", count, "instructions" | "instruction"]:
            number = _whole(count, "the count in run")
            if number < 1:
                msg = f"run needs at least 1 instruction, not {number}"
                raise WalkError(msg)
            return RunInstructions(number)
        case _:
            msg = f"unknown action {text!r}"
            raise WalkError(msg)


def parse_check(text: str) -> Check:
    """Read one check, such as `"variable n == 0"` or `'output contains "120"'`.

    The checks are `variable <name> == <int>`, `line == <int>`,
    `register r<i> == <int>`, `output contains "<text>"` and `halted`.

    Raises:
        WalkError: If the text is none of those.

    """
    match text.split(maxsplit=2):
        case ["halted"]:
            return Halted()
        case ["output", "contains", quoted] if len(quoted) >= 2 and quoted[0] == quoted[-1] == '"':  # noqa: PLR2004
            return OutputContains(quoted[1:-1])
        case _:
            pass
    match text.split():
        case ["variable", name, "==", value] if name.isidentifier():
            return VariableIs(name, _whole(value, "the value in a variable check"))
        case ["line", "==", value]:
            return LineIs(_whole(value, "the line in a line check"))
        case ["register", register, "==", value] if (
            register.startswith("r") and register[1:].isdigit()
        ):
            return RegisterIs(int(register[1:]), _whole(value, "the value in a register check"))
        case _:
            msg = f"unknown check {text!r}"
            raise WalkError(msg)


def _signed(word: int) -> int:
    """Read a 16-bit word as a signed number, the way Pebble's code means it (65535 is -1)."""
    return word - (_SIGN_BIT << 1) if word & _SIGN_BIT else word


def _variable(
    name: str, translated: TranslatedProgram, start: MachineState, now: MachineState
) -> int | None:
    """Read the variable `name` of the running code, as the variables pane shows it.

    The frame is the one of the instruction that started in `start`, and `r7` in
    `start` says where it sits, exactly as `picture.variables_picture` finds it.
    """
    if not 0 <= start.pc < len(translated.frames):
        return None
    layout = translated.frames[start.pc]
    if layout is None:
        return None
    for slot in layout.slots:
        address = start.registers[FRAME_POINTER] + slot.offset
        if slot.name == name and not slot.hidden and 0 <= address < len(now.memory):
            return _signed(now.memory[address])
    return None


def passes(
    check: Check, now: MachineState, start: MachineState, translated: TranslatedProgram | None
) -> bool:
    """Say whether `check` holds for the machine right now.

    Args:
        check: The check to test.
        now: The machine's state now.
        start: The state at the start of the current instruction, which says which
            line is running and which frame the variables are in.
        translated: The Pebble program, or None for assembly (no lines, no variables).

    """
    match check:
        case Halted():
            return now.halted
        case OutputContains(text):
            return text in now.output_text
        case RegisterIs(index, value):
            return 0 <= index < len(now.registers) and now.registers[index] == value
        case LineIs(line):
            return (
                translated is not None and not now.halted and translated.line_at(start.pc) == line
            )
        case VariableIs(name, value):
            if translated is None or now.halted:
                return False
            return _variable(name, translated, start, now) == value


def example_source(name: str) -> str | None:
    """Read the example program called `name` from `examples/`, or None if there is none."""
    path = resources.files("pycpu.cockpit").joinpath("examples").joinpath(f"{name}.pebble")
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _text(table: dict[str, object], key: str, where: str) -> str:
    """Return `table[key]` as non-empty text, or raise a `WalkError` saying it is missing."""
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{where} needs {key} as some text"
        raise WalkError(msg)
    return value.strip()


def _show(table: dict[str, object], where: str) -> str | None:
    """Return the optional `show` of a step or try, checking it is a known target."""
    show = table.get("show")
    if show is None:
        return None
    if show not in SHOW_TARGETS:
        msg = f"{where} has show {show!r}, which is not one of {', '.join(SHOW_TARGETS)}"
        raise WalkError(msg)
    return str(show)


def _unknown_keys(table: dict[str, object], allowed: frozenset[str], where: str) -> None:
    """Refuse keys a walk file has no use for, so a misspelt key is not silently ignored."""
    extra = sorted(set(table) - allowed)
    if extra:
        msg = f"{where} has unknown keys: {', '.join(extra)}"
        raise WalkError(msg)


def _source(data: dict[str, object]) -> str:
    """Return the walk's program: the named example's text, or its own `source`."""
    example, source = data.get("example"), data.get("source")
    if (example is None) == (source is None):
        msg = "the walk needs an example or a source, and not both"
        raise WalkError(msg)
    if source is not None:
        if not isinstance(source, str) or not source.strip():
            msg = "source must be the Pebble program's text"
            raise WalkError(msg)
        return source
    text = example_source(example) if isinstance(example, str) else None
    if text is None:
        msg = f"there is no example called {example!r}"
        raise WalkError(msg)
    return text


def _steps(data: dict[str, object]) -> tuple[WalkStep, ...]:
    """Read the `[[steps]]` tables; the first must be `start`."""
    raw = data.get("steps")
    if not isinstance(raw, list) or not raw:
        msg = "the walk needs at least one [[steps]]"
        raise WalkError(msg)
    steps: list[WalkStep] = []
    for number, table in enumerate(raw, start=1):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        where = f"step {number}"
        if not isinstance(table, dict):
            msg = f"{where} must be a table"
            raise WalkError(msg)
        step: dict[str, object] = table  # pyright: ignore[reportUnknownVariableType]
        _unknown_keys(step, _STEP_KEYS, where)
        action = parse_action(_text(step, "do", where))
        steps.append(
            WalkStep(
                say=_text(step, "say", where),
                action=action,
                look=_depth(step.get("look"), f"{where}'s look"),
                show=_show(step, where),
            )
        )
    if steps[0].action != Start():
        msg = "the first step must do start, so every replay begins with a clean load"
        raise WalkError(msg)
    return tuple(steps)


def _trial(data: dict[str, object]) -> WalkTry:
    """Read the `[try]` table: the task, its look, its check and its solution."""
    table = data.get("try")
    if not isinstance(table, dict):
        msg = "the walk needs a [try] table"
        raise WalkError(msg)
    trial: dict[str, object] = table  # pyright: ignore[reportUnknownVariableType]
    _unknown_keys(trial, _TRY_KEYS, "[try]")
    solution = trial.get("solution")
    if not isinstance(solution, list) or not solution:
        msg = "[try] needs a solution: a list of actions that do the task"
        raise WalkError(msg)
    actions: list[Action] = []
    for item in solution:  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(item, str):
            msg = "[try]'s solution must be a list of actions, as text"
            raise WalkError(msg)
        actions.append(parse_action(item))
    return WalkTry(
        task=_text(trial, "task", "[try]"),
        look=_depth(trial.get("look"), "[try]'s look"),
        check=parse_check(_text(trial, "check", "[try]")),
        solution=tuple(actions),
        show=_show(trial, "[try]"),
        step=_step_kind(trial),
    )


def _step_kind(trial: dict[str, object]) -> str | None:
    """Return the try's optional `step` kind, which only `"into"` (at line depth) may be."""
    kind = trial.get("step")
    if kind is None:
        return None
    if kind not in TRY_STEP_KINDS or trial.get("look") != Depth.LINE.value:
        msg = f'[try]\'s step may only be "into", with look = "line", not {kind!r}'
        raise WalkError(msg)
    return str(kind)


def parse_walk(name: str, text: str) -> Walk:
    """Read one walk file's text.

    Args:
        name: The walk's name, used in every error so the file is easy to find.
        text: The TOML text of `walks/<name>.toml`.

    Raises:
        WalkError: Naming the file and the first problem found in it.

    """
    try:
        data: dict[str, object] = tomllib.loads(text)
        _unknown_keys(data, _WALK_KEYS, "the walk")
        return Walk(
            name=name,
            title=_text(data, "title", "the walk"),
            source=_source(data),
            see_also=_text(data, "see_also", "the walk"),
            steps=_steps(data),
            trial=_trial(data),
        )
    except (WalkError, tomllib.TOMLDecodeError) as error:
        msg = f"{name}.toml: {error}"
        raise WalkError(msg) from None


def load_walk(name: str) -> Walk:
    """Read the walk called `name` from `walks/<name>.toml`.

    Raises:
        WalkError: If there is no such file, or the file is not right.

    """
    path = resources.files("pycpu.cockpit").joinpath("walks").joinpath(f"{name}.toml")
    if not path.is_file():
        msg = f"{name}.toml: there is no walk file called that"
        raise WalkError(msg)
    return parse_walk(name, path.read_text(encoding="utf-8"))


@cache
def load_walks() -> tuple[Walk, ...]:
    """Read every walk in `WALK_ORDER`; the files never change while the Cockpit runs.

    Raises:
        WalkError: If any walk file is missing or not right.

    """
    return tuple(load_walk(name) for name in WALK_ORDER)


def walk_named(name: str) -> Walk | None:
    """Return the walk called `name`, or None if there is no walk called that."""
    return next((walk for walk in load_walks() if walk.name == name), None)
