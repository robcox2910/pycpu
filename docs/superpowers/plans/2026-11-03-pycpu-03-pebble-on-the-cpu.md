# PyCPU Plan 3: Pebble on the CPU Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run real Pebble programs (integers, variables, `if`, `while`, functions, `print`) on PyCPU, with the same output as the Pebble VM, friendly errors at the edges of the subset, faults reported against the Pebble line, and a map from every machine word back to its Pebble line.

**Architecture:** Pebble's own front end compiles source to stack bytecode (`compile_source`). A translator in `src/pycpu/translator/` checks every instruction against the subset, follows what kind of value sits in each stack slot, and writes PyCPU assembly: Pebble's operand stack becomes the machine stack, variables live in stack frames, and multiply, divide and printing are routines written in assembly. The assembler from Plan 2 turns that into words, and a source map joins each word to its Pebble line.

**Tech Stack:** Python 3.14, uv, pytest, Hypothesis, ruff, strict pyright, `pebble-lang` (pinned git tag, released in Task 1), PyWeb v0.3.1, mkdocs-material.

**Spec:** `docs/superpowers/specs/2026-11-01-pycpu-design.md` (§5 "Pebble subset" and "Route" are the contract). Roadmap and "Notes for Plan 3": `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`. The Instruction Set: `docs/reference/instruction-set.md`.

## Global Constraints

- NAND is the single primitive. Nothing above `simulator.py` computes a logic result in Python, except test helpers, `peek`/`poke`, the fast engine and the output peripheral. The translator only writes assembly text; it never computes a Pebble program's results.
- Multiply, divide, modulo and decimal printing are routines in PyCPU assembly, visible on the machine like everything else (spec §5).
- Integers are 16-bit and wrap on overflow, unlike the Pebble VM; this is taught, not hidden (spec §5).
- Anything outside the subset gets a friendly error naming the unsupported feature, never a crash or wrong output (spec §5).
- Conformance: subset programs print the same on the Pebble VM and on PyCPU for values that stay in 16-bit range; a program that errors on the VM must fault on PyCPU or be refused by the translator (spec §5).
- Pebble is used only through its public API at a pinned tag (spec §7, §8). Sibling pins are git tags, never `path`.
- Fault codes fit in 0–255 (`HALT_CODE_MAX`): `Fault.BAD_ADDRESS = 1`, `Fault.STACK_OVERFLOW = 2`, `Fault.DIVIDE_BY_ZERO = 3`.
- Never use `TYPE_CHECKING` or `from __future__ import annotations`.
- Documentation is as important as code, and ranks above every other rule here. See the Documentation Standard below. A task with weak docs is not done, however good its code is.
- Do not publish PyCPU: GitHub Pages stays off, `docs.yml` stays manual-only, no `series.yml` entry, no PyCPU version tag. `mkdocs build --strict` must pass at every commit. (Task 1 tags a **Pebble** release, which is how siblings ship.)
- Work on branch `plan-3-pebble-on-the-cpu`; one PR into `main` at the end, merged when CI is green.
- Conventional commits ending with the `Co-Authored-By` line.

## Documentation Standard

This project exists to teach. The audience is a curious 12-year-old who has never heard of a logic gate. Read `pyweb/docs/concepts/server-sent-events.md` for the tone and shape to match.

**Write the doc first.** In every task with a concept doc, the doc is written before the code. Its `## Try It` block fails until the code exists, so it is part of the red step, and the doc shapes the API a learner sees.

**Every concept page has these, in this order:**

1. `# Title`, then a `##` heading naming an everyday analogy, opening with that analogy before any jargon.
2. A table mapping the analogy to the real thing, using the actual names in the code.
3. `## Try It`: a complete, copy-paste Python example with its output in a comment. `tests/test_docs.py` runs it.
4. `## How It Works`: the step-by-step, with an ASCII diagram, showing how the thing is *built* from the layer below, not just how to use it. Name the file it lives in.
5. `## Why Does This Matter?`: what would be impossible without it, and a link to the real world.
6. `## What's Next`: a link to the next page, so the docs read as one continuous climb.

**The site must also tell the whole from-scratch story.** A learner landing on `docs/index.md` should understand what the project is, why anyone would build a computer out of nothing, and how to read it. Each page builds only on pages before it, and every new word is explained where it first appears.

**Docstrings:** every public module, class and function has one. Module docstrings open with an analogy, in the style of `pystack/src/pystack/plugins/llm_plugin.py`. Class and function docstrings say what the thing is in plain words before any jargon, and are still imperative and Google-style. Private helpers explain *why* where it is not obvious.

**Tests read as sentences** and double as examples.

**Reviewers check docs as a first-class gate.** For every task, the reviewer reads the docs as if they were the 12-year-old, follows `## Try It`, and rejects the task if a page leans on an unexplained word, skips how the thing is built, or only describes the API. Tests can catch a missing section, not a bad explanation.

**Honesty rule for docs:** the numbers in docs are measured, never invented. Output in `## Try It` is checked by running it. Every exact figure in prose is either printed by a Try It or pinned by a test.

**Every new page** goes in `mkdocs.yml` nav and in `KEY_IDEAS` in `tests/test_docs.py`, and the previous page's `## What's Next` links to it. Pages written out of reading order (below) are slotted into their nav position and the chain is re-linked around them.

## Review Focus

- Programs at the subset's edges (floats, `/`, lists, strings outside `print`, closures, built-ins, booleans stored or printed): a friendly `UnsupportedFeature` naming the feature and the Pebble line, never a crash or wrong output. Hypothesis over a grammar that mixes supported and unsupported constructs, in Task 8.
- 16-bit edges: `-32768`, `32767`, printing `-32768`, `//` and `%` with negative operands (floor, as Pebble), `-32768 // -1` wrapping. Tests in Tasks 2 and 3.
- Deep or endless recursion: `Fault.STACK_OVERFLOW` reported at a Pebble line, and the program and data are never overwritten. Test in Task 6.
- Division by zero inside a function, three calls deep: `Fault.DIVIDE_BY_ZERO` at the same Pebble line the VM's error names. Test in Task 7.
- A function that sometimes returns nothing: fine as a statement, a friendly error when its value is used. Test in Task 6.

---

## The Pebble Subset Contract

This section is the contract for Tasks 4–8. It is written against Pebble v0.2.3's bytecode (facts gathered from `pebble-lang` at that tag; the public names come from Task 1).

**What Pebble gives us.** `compile_source(source) -> Program`; `Program.compiled` is a `CompiledProgram` with `main: CodeObject` and `functions: dict[str, CodeObject]`. A `CodeObject` has `name`, `instructions`, `constants` (one pool per code object), `parameters`, `cell_variables`, `free_variables`. An `Instruction` has `opcode` (`OpCode`, a `StrEnum`), `operand` (`int | str | None`) and `location` (`SourceLocation(line, column)`, 1-based, or `None` for compiler-made instructions). Jump operands are absolute instruction indices in the same code object. Variables are addressed by name. `CALL` carries a function name and no argument count. The optimizer has already folded constant expressions (`print(1 + 2 * 3)` is `LOAD_CONST 7; PRINT`). Pebble's syntax: `let x = 3`, `x = x - 1`, `fn f(a, b) { return a }`, `if c { } else if c { } else { }`, `while c { }`, `print(expr)` (exactly one argument), `#` comments, no semicolons.

**Value kinds.** The translator follows the kind of every operand-stack slot through each code object (an abstract run; stack depths at joins agree because Pebble's compiler guarantees it):

| Kind | Made by | Allowed into |
|---|---|---|
| `INT` | an `int` constant in −32768..32767, a variable, arithmetic, `NEGATE`, a call to a function that always returns a number | everything below that takes a value |
| `BOOL` | `true`/`false`, comparisons, `NOT`, an `and`/`or` with a `BOOL` side | `JUMP_IF_FALSE`, `NOT`, `and`/`or`, `POP` only |
| `TEXT` | a `str` constant | `PRINT` (directly) and `POP` only |
| `NULL` | `LOAD_CONST None`, a call to a function that never returns a number | `RETURN` and `POP` only |
| `MAYBE` | a call to a function that returns a number on some paths only | `POP` only |

`STORE_NAME` and call arguments take `INT`. Arithmetic (`ADD`, `SUBTRACT`, `MULTIPLY`, `FLOOR_DIVIDE`, `MODULO`) takes `INT, INT` and gives `INT`. Comparisons (`LESS_THAN`, `LESS_EQUAL`, `GREATER_THAN`, `GREATER_EQUAL`, `EQUAL`, `NOT_EQUAL`) take `INT, INT` and give `BOOL`. `JUMP_IF_FALSE_OR_POP`/`JUMP_IF_TRUE_OR_POP` (`and`/`or`) keep the operand's value, as Pebble does; the joined kind is `INT` only when both sides are `INT`, else `BOOL`. A word is false when it is 0. A function's return kind is worked out from its `RETURN`s across all functions until nothing changes (recursion included).

**Supported opcodes:** `LOAD_CONST`, `LOAD_NAME` (a parameter or a name this code object stores), `STORE_NAME`, the arithmetic and comparisons above, `NEGATE`, `NOT`, `JUMP`, `JUMP_IF_FALSE`, `JUMP_IF_FALSE_OR_POP`, `JUMP_IF_TRUE_OR_POP`, `POP`, `PRINT`, `CALL` (a user function), `RETURN`, `HALT`, and `CHECK_TYPE` with operand `Int` (no code). Pebble's `for i in range(...)` is lowered by its compiler to these opcodes, so it works if the lowering uses only them; a test pins whichever is true.

**Friendly errors.** `class UnsupportedFeature(PebbleCPUError)` carries `feature`, `line`, `column`, and its message reads `"<feature> are not supported on PyCPU yet at line L, column C"` (or "is not", for a singular feature). The first unsupported thing in source order wins. Feature names:

| Bytecode or kind | Feature named |
|---|---|
| `DIVIDE` | `the / operator (it always makes a decimal number; use // for whole numbers)` |
| a `float` constant | `decimal numbers` |
| `POWER` | `the ** operator` |
| `BIT_AND`, `BIT_OR`, `BIT_XOR`, `BIT_NOT`, `LEFT_SHIFT`, `RIGHT_SHIFT` | `bitwise operators` |
| `BUILD_STRING` | `text with {} inside it` |
| `TEXT` anywhere but `PRINT` | `text outside print` |
| `BUILD_LIST`, `INDEX_GET`, `INDEX_SET`, `SLICE_GET`, `LIST_APPEND`, `UNPACK_SEQUENCE`, `GET_ITER`, `FOR_ITER` | `lists` |
| `BUILD_DICT` | `dictionaries` |
| `GET_FIELD`, `SET_FIELD`, `CALL_INSTANCE_METHOD`, `LOAD_ENUM_VARIANT`, a struct constructor | `structs, classes and enums` |
| `CALL_METHOD` | `methods like .upper()` |
| `MAKE_CLOSURE`, `LOAD_CELL`, `STORE_CELL`, a function name used as a value | `functions used as values` |
| `SETUP_TRY`, `POP_TRY`, `THROW` | `try, catch and throw` |
| `YIELD`, `AWAIT` | `generators and async` |
| `CALL` of a built-in or library function | `the built-in function <name>()` |
| `CHECK_TYPE` other than `Int` | `the <name> type` |
| an `int` constant outside −32768..32767 | `numbers bigger than 32767 or smaller than -32768` |
| `BOOL` stored, passed, returned, printed or used in arithmetic | `true and false outside if and while` |
| `NULL` or `MAYBE` used as a value | `using the result of a function that does not always return a number` |
| `LOAD_NAME` of a name this code object never stores | `variables from outside a function` |
| any other opcode | `the <OPCODE> instruction` |

Pebble's own errors (`pebble.PebbleError`: lexing, parsing, analysis, type checking) pass through unchanged.

**Machine layout.** Generated code keeps no value in a register across a Pebble instruction: `r0` always holds 0 (never written), `r1`–`r6` are scratch, `r7` is the frame pointer. Every code object, `main` included, gets a frame:

```
higher addresses
  arg 0 ... arg N-1   [r7 + 2 + (N-1-i)] for parameter i   (pushed by the caller, left to right)
  return address      [r7 + 1]                              (pushed by CALL)
  old r7              [r7]                                  (pushed by the prologue)
  local 0 ... L-1     [r7 - 1 - j]                          (made by the prologue, zeroed)
  operand stack       grows down from here (PUSH/POP)
lower addresses
```

`off6` limits a function to 29 parameters and 32 locals (else `UnsupportedFeature("more than 29 parameters" / "more than 32 variables in one function")`). The prologue checks that the stack will not reach `__end` (the first word after code and data) with room for the code object's deepest operand stack plus `RUNTIME_STACK_WORDS` for the routines, and otherwise runs `halt 2` (`STACK_OVERFLOW`). A call: the caller's arguments are already on the stack; `call f`; then the caller drops the arguments (`getsp`, `addi`, `setsp`) and pushes `r1`, the result. `RETURN` pops the result into `r1`, `setsp r7`, `pop r7`, `ret`. `FLOOR_DIVIDE` and `MODULO` check the divisor inline (`cmp r2, r0; br ne, ...; halt 3`) before calling the routine, so a divide-by-zero fault sits on the operator's own Pebble line. Program layout from address 0: `main` (ending in `halt 0`), each function, the runtime routines, string data, `__end:`. The stack starts at the top of RAM.

**Source map.** Each machine word belongs to the Pebble line of the Pebble instruction that made it (an instruction with no location takes the last located line before it in the same code object; a prologue takes its code object's first located line). Runtime routines and string data map to `None`. For a fault, the faulting word is `pc - 1` (an execute fault) or `pc` (a fetch fault).

---

## File Structure

| File | Responsibility |
|---|---|
| (pebble-lang) `src/pebble/__init__.py`, its docs and tests | Export the bytecode types; release v0.3.0 |
| `pyproject.toml`, `uv.lock` | Pin `pebble-lang` v0.3.0; declare `pynet` directly |
| `src/pycpu/translator/__init__.py` | Public names: `translate`, `run_pebble`, `TranslatedProgram`, `PebbleRun`, `PebbleCPUError`, `UnsupportedFeature` |
| `src/pycpu/translator/runtime.py` | `RUNTIME` assembly: `__mul`, `__divmod`, `__print_int`, `__print_text`; `RUNTIME_STACK_WORDS` |
| `src/pycpu/translator/subset.py` | Value kinds, the subset check, return kinds, `UnsupportedFeature` |
| `src/pycpu/translator/codegen.py` | Frames, per-opcode assembly, the source map |
| `src/pycpu/translator/program.py` | `translate`, `TranslatedProgram`, `run_pebble`, `PebbleRun` |
| `src/pycpu/bench/app.py`, `page.html` | Load a Pebble program; show its source and current line |
| `tests/test_runtime.py`, `tests/test_translator.py`, `tests/test_functions.py`, `tests/test_pebble_faults.py`, `tests/test_conformance.py`, `tests/pebble_programs/*.pebble` | Tests |
| `examples/run_pebble.py` | Example: run a Pebble program on PyCPU |

**Pages in reading order** (a new nav section "Pebble on the CPU" after "The Computer"; `the-bench.md` moves after it and stays the last concept page):

| Page | Task | Teaches |
|---|---|---|
| `concepts/from-pebble-to-machine-code.md` | 4 | Pebble's compiler makes stack bytecode; the translator turns each instruction into machine code; the Pebble stack becomes the real stack |
| `concepts/variables-in-memory.md` | 4 | Frames, slots, the frame pointer; why a name becomes an address |
| `concepts/why-16-bit-numbers-wrap.md` | 4 | The mileage counter again; where PyCPU and the Pebble VM disagree, and why |
| `concepts/if-and-while-as-jumps.md` | 5 | Conditions, branches and loops as jumps; `and`/`or` short cuts; why booleans stay in conditions |
| `concepts/how-a-function-call-really-works.md` | 6 | Arguments, the frame, the return value, recursion, stack overflow |
| `concepts/multiply-and-divide.md` | 2 | Multiply and divide with only adding and shifting; floor division and remainders |
| `concepts/printing-a-number.md` | 3 | Turning a number into digit characters; the output port |
| `concepts/what-happens-when-things-go-wrong.md` | 7 | Faults, fault codes, and finding the Pebble line |

---

### Task 1: Pebble shares its bytecode, and PyCPU pins it

**Files:**
- In a **fresh clone** of `https://github.com/robcox2910/pebble-lang` in the scratchpad (never the local `/Users/robcox/development/python/pebble-lang`, whose `main` is stale): `src/pebble/__init__.py`, a test, its docs page or README section on the public API
- In PyCPU: `pyproject.toml`, `uv.lock`, `tests/test_dependency_pins.py`

**Interfaces:**
- Produces: `from pebble import compile_source, run_source, PebbleError, Program, CompiledProgram, CodeObject, Instruction, OpCode, SourceLocation` works at tag `v0.3.0`; PyCPU depends on it.

- [ ] **Step 1: In the clone, write a failing test** that each of `CompiledProgram`, `CodeObject`, `Instruction`, `OpCode`, `SourceLocation` is in `pebble.__all__` and is the same object as in its home module, following the repo's test style (read its `CLAUDE.md` and `CONTRIBUTING.md` first).
- [ ] **Step 2: Export them** from `src/pebble/__init__.py`, and document them where Pebble documents its public API (a short, kid-friendly paragraph: "the instructions the compiler makes, for tools that want to read them"). Run Pebble's full checks as its `CLAUDE.md` says.
- [ ] **Step 3: Ship it the series way.** Branch, PR, wait for green CI, merge, then tag `v0.3.0` on `main` (a public API addition bumps the minor version, per Pebble's Releasing section) and push the tag.
- [ ] **Step 4: Pin it in PyCPU.** Add `"pebble-lang"` to dependencies with `pebble-lang = { git = "https://github.com/robcox2910/pebble-lang", tag = "v0.3.0" }`, and declare `pynet` directly at the tag PyWeb v0.3.1 pins (roadmap note). `uv lock`, `uv sync --all-extras`. Extend `tests/test_dependency_pins.py` to assert both pins are git tags.
- [ ] **Step 5: Run** `uv run pytest` and `uv run python -c "from pebble import compile_source, OpCode; print(compile_source('print(1)').compiled.main.instructions[0].opcode)"`. Expected: PASS, then `LOAD_CONST`.
- [ ] **Step 6: Commit** in PyCPU. `git commit -m "chore: pin pebble-lang v0.3.0 and pynet"`

---

### Task 2: Multiply and divide in assembly

**Files:**
- Create: `src/pycpu/translator/__init__.py`, `src/pycpu/translator/runtime.py`, `docs/concepts/multiply-and-divide.md`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Produces: `RUNTIME: str` (assembly, labels below), `RUNTIME_STACK_WORDS: int` (the most stack words any routine uses, counted, with a test). Routines take inputs in `r1`, `r2`, return in `r1` (and `r2`), keep `r0` and `r7`, may change `r1`–`r6`, and end with `ret`:
  - `__mul`: `r1 = (r1 * r2) mod 65536` (shift-and-add).
  - `__divmod`: `r1, r2` as signed 16-bit; returns `r1 = floor(r1 / r2)` and `r2 = r1 - r2 * floor(...)` (Pebble's `//` and `%`), wrapped to 16 bits. Never called with `r2 == 0` (callers check).

- [ ] **Step 1: Write the doc first.** `multiply-and-divide.md` (analogy: long multiplication on paper in binary, where every digit is 0 or 1 so each row is "the number, shifted" or nothing; long division as repeated "does it fit?"). Explain floor division and remainders with negatives on a number line (`-7 // 2` is `-4`, `-7 % 2` is `1`), and why a computer with only adding and shifting can still multiply. Try It: assemble a tiny caller plus `RUNTIME` and run on `FastMachine`, printing a few products and quotients, and how many instructions `__mul` took. Place it in nav after How a Function Call Really Works (re-link as pages land). `KEY_IDEAS`: `["multiply", "shift", "remainder"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_runtime.py` (run the routines on `FastMachine` through a small harness that loads `r1`, `r2`, `call`s the routine and halts):
  - `__mul`: Hypothesis over all 16-bit pairs against `(a * b) & 0xFFFF`; pinned `(300, 300) -> 24464`, `(0xFFFF, 0xFFFF) -> 1`.
  - `__divmod`: Hypothesis over signed pairs with `b != 0` against Python `//` and `%` wrapped to 16 bits; pinned `(-7, 2) -> (-4, 1)`, `(7, -2) -> (-4, -1)`, `(-32768, -1) -> (-32768, 0)`, `(-32768, 1)`, `(32767, -32768)`.
  - `r0` and `r7` unchanged after every routine; `RUNTIME_STACK_WORDS` is at least the deepest stack use measured while running them.
- [ ] **Step 3: Run** `uv run pytest tests/test_runtime.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** the routines in `runtime.py` as one assembly string, commented line by line for learners (the Bench will show it).
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: multiply and divide in assembly"`

---

### Task 3: Printing a number

**Files:**
- Modify: `src/pycpu/translator/runtime.py`
- Create: `docs/concepts/printing-a-number.md`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Produces: `__print_int` (prints `r1` as a signed decimal, then `"\n"`, through `OUTPUT_PORT`) and `__print_text` (prints the 0-terminated text starting at address `r1`, then `"\n"`), both in `RUNTIME`.

- [ ] **Step 1: Write the doc first.** `printing-a-number.md` (analogy: a cash register that only has a slot for single characters, so 305 must be broken into '3', '0', '5' by dividing by ten again and again, which gives the digits backwards). Explain character codes (`'0'` is 48), why the digits come out backwards and how the stack turns them round, and the minus sign. Try It prints a few numbers through `__print_int` and shows the output text and the codes sent to the port. Nav after Multiply and Divide. `KEY_IDEAS`: `["digit", "character", "output port"]`.
- [ ] **Step 2: Write failing tests**: `__print_int` over Hypothesis signed 16-bit values gives `f"{v}\n"`; pinned `0`, `-1`, `32767`, `-32768`; `__print_text` prints `"Hi\n"` for a `.string "Hi"` and `"\n"` for an empty string; `r0`, `r7` unchanged; `RUNTIME_STACK_WORDS` still covers the deepest use.
- [ ] **Step 3: Run** `uv run pytest tests/test_runtime.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** both routines (using `__divmod` by 10, or repeated subtraction; say which and why in the doc).
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: print numbers and text from assembly"`

---

### Task 4: The translator: variables, arithmetic and print

**Files:**
- Create: `src/pycpu/translator/subset.py`, `src/pycpu/translator/codegen.py`, `src/pycpu/translator/program.py`, `docs/concepts/from-pebble-to-machine-code.md`, `docs/concepts/variables-in-memory.md`, `docs/concepts/why-16-bit-numbers-wrap.md`
- Modify: `src/pycpu/translator/__init__.py`, `mkdocs.yml`
- Test: `tests/test_translator.py`

**Interfaces:**
- Consumes: `compile_source` and the bytecode types (Task 1); `RUNTIME` (Tasks 2–3); `assemble`, `Program` (Plan 2); `FastMachine`, `Fault`.
- Produces:
  - `class PebbleCPUError(Exception)`; `class UnsupportedFeature(PebbleCPUError)` with `feature: str`, `line: int | None`, `column: int | None`.
  - `@dataclass(frozen=True) class TranslatedProgram: source: str; assembly: str; program: Program; pebble_lines: tuple[int | None, ...]` (one per machine word) with `line_at(address: int) -> int | None`.
  - `translate(source: str) -> TranslatedProgram` (raises `pebble.PebbleError` or `UnsupportedFeature`).
  - `@dataclass(frozen=True) class PebbleRun: output: str; halted: bool; fault: Fault | None; line: int | None; steps: int`.
  - `run_pebble(source: str, max_steps: int = 1_000_000) -> PebbleRun` (fast engine; `halted` False when `max_steps` ran out).

- [ ] **Step 1: Write the docs first.** `from-pebble-to-machine-code.md` (analogy: a recipe in one language, translated card by card into the cook's number code by a translator who also remembers which card each line came from; Pebble's stack bytecode shown for a one-line program, then the assembly it becomes). `variables-in-memory.md` (analogy: a row of labelled pigeonholes behind the counter; the frame pointer as your hand on the row; a name becomes "two holes below my hand"). `why-16-bit-numbers-wrap.md` (analogy: the mileage counter from Negative Numbers; `print(32767 + 1)` gives `-32768` on PyCPU and `32768` on the Pebble VM; why we teach it rather than hide it; which programs give the same answers). Try Its run real Pebble through `run_pebble` and show `translate(...).assembly` excerpts. Nav: the new "Pebble on the CPU" section, in the reading order above; the-bench.md after it. `KEY_IDEAS`: `["bytecode", "translator", "assembly"]`, `["variable", "frame", "frame pointer"]`, `["wrap", "16-bit", "overflow"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_translator.py`:
  - `run_pebble("print(1)").output == "1\n"`; `let x = 3` / `x = x * 4 - 5` / `print(x)` prints `7`; `print(-7 // 2)` and `print(-7 % 2)` print `-4` and `1`; `print("hello")` prints `hello`; `print(32767 + 1)` prints `-32768`; every run ends `halted` with `fault is None`.
  - `translate` output assembles, starts `main` at address 0, and ends with `__end:`; `pebble_lines` has one entry per word; each word of `print(1)` on line 1 maps to 1, and runtime words map to `None`.
  - Each row of the friendly-error table that applies to straight-line code raises `UnsupportedFeature` with that feature and the right line and column: `print(7 / 2)`, `let x = 1.5`, `print(2 ** 3)`, `print(1 & 2)`, `print("a{1}")`, `let s = "hi"`, `let a = [1]`, `let d = {"a": 1}`, `print(len("ab"))`, `let x = 40000`, `let b = true`, `print(true)`, `print(1 + true)`.
  - A Pebble syntax error raises `pebble.PebbleError` unchanged.
- [ ] **Step 3: Run** `uv run pytest tests/test_translator.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `subset.py` (kinds, checks, errors), `codegen.py` (frames for `main`, per-opcode assembly as in the contract), `program.py`. In this task `CALL` of a user function, jumps and comparisons may raise `UnsupportedFeature("<later task>")`; Tasks 5 and 6 replace that.
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: translate Pebble variables, arithmetic and print"`

---

### Task 5: Conditions and loops

**Files:**
- Modify: `src/pycpu/translator/subset.py`, `src/pycpu/translator/codegen.py`
- Create: `docs/concepts/if-and-while-as-jumps.md`
- Test: `tests/test_translator.py`

**Interfaces:**
- Consumes/produces: Task 4's; adds comparisons, `NOT`, `JUMP`, `JUMP_IF_FALSE`, `JUMP_IF_FALSE_OR_POP`, `JUMP_IF_TRUE_OR_POP` per the contract.

- [ ] **Step 1: Write the doc first.** `if-and-while-as-jumps.md` (analogy: a choose-your-own-adventure book: "if you have the key, turn to page 40"; a loop is "go back to page 12"). Show the bytecode and assembly for an `if`/`else` and a `while`, how a comparison becomes `cmp` plus a flag-reading branch, how `and`/`or` skip the right side, and why `true`/`false` live only inside conditions on a 16-bit machine (a stored `true` would look exactly like `1`). Try It: a countdown with `while` and an `if` inside. `KEY_IDEAS`: `["jump", "condition", "loop"]`.
- [ ] **Step 2: Write failing tests**: every comparison over Hypothesis pairs of signed values matches Python when printed through `if c { print(1) } else { print(0) }`; nested `if`/`else if`/`else`; `while` with a counter; `and`/`or` short-circuit (the right side of `false and (1 // 0 == 0)` never runs: no fault); `not`; `let x = 0 or 5` prints 5 (both `INT`); `let b = 1 < 2` raises `UnsupportedFeature("true and false outside if and while")`; `print(1 == 1)` likewise; `for i in range(3) { print(i) }` either prints `0 1 2` or raises a named `UnsupportedFeature` (pin whichever the lowering gives, and say so in the doc).
- [ ] **Step 3: Run** `uv run pytest tests/test_translator.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** comparisons (`cmp` with `lt`, `le`, `gt`, `ge`, `eq`, `ne` on signed flags), jumps (a label per Pebble instruction index that is a jump target) and the `_OR_POP` jumps.
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: translate conditions and loops into jumps"`

---

### Task 6: Functions

**Files:**
- Modify: `src/pycpu/translator/subset.py`, `src/pycpu/translator/codegen.py`
- Create: `docs/concepts/how-a-function-call-really-works.md`
- Test: `tests/test_functions.py`

**Interfaces:**
- Consumes/produces: Task 4's; adds `CALL` of user functions, `RETURN`, function frames, return kinds and the prologue's stack check per the contract.

- [ ] **Step 1: Write the doc first.** `how-a-function-call-really-works.md` (analogy: leaving your desk to help a friend: you leave the inputs on a tray, a note of where you were, and clear your own corner of the desk; when you come back you pick up the answer from the tray). Draw the frame from the contract with a real call's addresses, show arguments, the saved frame pointer, locals, the result in `r1`, and recursion as a pile of frames; what stack overflow means. Try It: `fn double(n) { return n * 2 }` called in a loop (the program from the Pebble research, printing `6 4 2`) and a recursive factorial up to `7` (`5040`). `KEY_IDEAS`: `["argument", "frame", "recursion"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_functions.py`: the double loop prints `6\n4\n2\n`; factorial of 7 prints 5040; a function with three parameters keeps their order; a function calling another with its own locals keeps both frames intact; a function with no `return` used as a statement works; `print(f())` where `f` never returns raises `UnsupportedFeature("using the result of a function that does not always return a number")`, and likewise for a function that returns on one path only; `fn f() { return g }` with top-level `g` raises "variables from outside a function"; a closure raises "functions used as values"; 30 parameters and 33 locals raise their errors; endless recursion `fn f(n) { return f(n + 1) }` ends with `fault == Fault.STACK_OVERFLOW` and a Pebble line, and every word of code and string data is unchanged afterwards (compare memory below `__end` with the loaded program).
- [ ] **Step 3: Run** `uv run pytest tests/test_functions.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** frames, calls, returns, the return-kind fixed point, and the prologue check.
- [ ] **Step 5: Run** the same tests. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: translate Pebble functions with real stack frames"`

---

### Task 7: When things go wrong

**Files:**
- Modify: `src/pycpu/translator/codegen.py`, `src/pycpu/translator/program.py`
- Create: `docs/concepts/what-happens-when-things-go-wrong.md`
- Test: `tests/test_pebble_faults.py`

**Interfaces:**
- Consumes: Tasks 4–6. Produces: `PebbleRun.fault` and `.line` filled from the halt code and the source map; `PebbleRun.describe() -> str`, a friendly one-line message (for example `"Division by zero at line 3"`, `"The stack ran out of room at line 2"`).

- [ ] **Step 1: Check the VM first.** Run Pebble's VM on division by zero inside a function three calls deep and on endless recursion; record the exact errors and lines in the report (the VM may have no recursion limit, in which case say so).
- [ ] **Step 2: Write the doc first.** `what-happens-when-things-go-wrong.md` (analogy: a referee's whistle: the game stops at once and the referee says what happened and where). Explain the three faults, why the machine stops instead of guessing, how the halt code and the source map lead back to the Pebble line, and the difference from Pebble's VM message. Try It runs a division by zero and prints `describe()`. `KEY_IDEAS`: `["fault", "halt", "source map"]`.
- [ ] **Step 3: Write failing tests**: division by zero (both `//` and `%`), at top level and three calls deep, gives `Fault.DIVIDE_BY_ZERO` and the same line as the VM's `PebbleRuntimeError.line`; stack overflow gives `Fault.STACK_OVERFLOW` with the line of the call or prologue; an endless `while` returns `halted is False` after `max_steps`; a normal finish has `fault is None` and `line is None`; `describe()` for each.
- [ ] **Step 4: Run** `uv run pytest tests/test_pebble_faults.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 5: Implement** the fault-to-line lookup and `describe()`.
- [ ] **Step 6: Run** the same tests. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "feat: report Pebble faults against their source line"`

---

### Task 8: Conformance with the Pebble VM

**Files:**
- Create: `tests/test_conformance.py`, `tests/pebble_programs/*.pebble` (at least 12), `examples/run_pebble.py`
- Modify: `tests/test_examples.py`, `src/pycpu/fast.py` (only if needed for speed)

**Interfaces:**
- Consumes: `run_pebble`, `translate`, `pebble.run_source`, `GateMachine`.

- [ ] **Step 1: Write the corpus.** At least 12 small programs that use every subset feature between them (variables, all operators, negative numbers, `if`/`else if`/`else`, `while`, `and`/`or`/`not`, functions with several parameters, recursion, functions as statements, text printing), plus two that divide by zero.
- [ ] **Step 2: Write the tests.**
  - `test_corpus_matches_the_pebble_vm`: for every file, `run_pebble(src).output == run_source(src)`; for the divide-by-zero files, the VM raises and PyCPU faults with `DIVIDE_BY_ZERO` on the same line.
  - `test_random_programs_match_the_pebble_vm`: Hypothesis builds programs from a small grammar (lets, assignments, arithmetic with small literals, comparisons in `if`/`while` with a bounded counter, prints), evaluates every intermediate value in Python and rejects programs that leave 16-bit range; both engines' output matches. `max_examples=200`, `deadline=None`.
  - `test_unsupported_programs_never_crash`: Hypothesis mixes in unsupported constructs (floats, `/`, lists, strings in variables, closures, built-ins, stored booleans); `translate` either raises `UnsupportedFeature`/`pebble.PebbleError`, or succeeds and the output matches the VM.
  - `test_a_translated_program_runs_the_same_on_gates` (`@pytest.mark.slow`): one short corpus program run to the end on `GateMachine(address_bits=12)` and on `FastMachine`, with equal final state and output.
- [ ] **Step 3: Run, fix, run** `uv run pytest tests/test_conformance.py -v` until PASS. Any difference is a translator or runtime bug: fix it, never loosen the test. If the conformance tests take over 30 s, fix `FastMachine`'s per-step handler table (roadmap note) and record before and after.
- [ ] **Step 4: Add `examples/run_pebble.py`** (runs the double-loop program, printing its output) and its line in `tests/test_examples.py`.
- [ ] **Step 5: Run** `uv run pytest` and `uv run pytest -m slow --no-cov tests/test_conformance.py`. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "test: prove Pebble programs print the same on PyCPU"`

---

### Task 9: The Bench runs Pebble, and the story is updated

**Files:**
- Modify: `src/pycpu/bench/app.py`, `src/pycpu/bench/page.html`, `docs/concepts/the-bench.md`, `docs/concepts/assembly-language.md`, `docs/index.md`, `docs/from-scratch.md`, `README.md`, `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`, `src/pycpu/proof.py`, `scripts/measure_engines.py`, `tests/test_engine_speed.py`
- Test: `tests/test_bench.py`

**Interfaces:**
- Consumes: `translate`, `TranslatedProgram.line_at`, `PebbleRun.describe`.
- Produces: `POST /api/pebble` `{"source": "..."}` loads a translated program (400 with the error's message, line and column on a `PebbleError` or `UnsupportedFeature`); the machine JSON gains `"pebble": {"source": [lines...], "line": n | null} | null` (null for an assembly program); `GET /api/machine` reports the Pebble line of the current instruction.

- [ ] **Step 1: Update `the-bench.md` first:** load a Pebble program, see its source with the current line marked next to the machine code, step by instruction and watch the line change. Try It through `TestClient`.
- [ ] **Step 2: Write failing tests** for `/api/pebble` (success, both error kinds, bad bodies) and the `pebble` key while stepping.
- [ ] **Step 3: Implement** the route and the page's Pebble pane (the first piece of the Cockpit's left pane).
- [ ] **Step 4: Tidy carried items:** move the engine speed limits into `proof.py` and import them from the script and the test (roadmap note); reword `assembly-language.md`'s "Later in this climb we build a compiler" to match the story (the next climb translates Pebble's compiled programs).
- [ ] **Step 5: Update the story.** `index.md`, `from-scratch.md` and the README ladder: Pebble now runs on PyCPU; the Cockpit is still to come. README Concepts table gains the new pages in nav order. Add "Notes for Plan 4" to the roadmap: instructions per Pebble line measured on the corpus, gate steps per Pebble line, what the Cockpit's "step a Pebble line" should do, and anything this plan learned.
- [ ] **Step 6: Check in a real browser**: load a Pebble program, step it, see the line move, zoom to a gate; no console errors.
- [ ] **Step 7: Final verification.** `uv run pytest && uv run pytest -m slow --no-cov && uv run ruff check . && uv run ruff format --check . && uv run pyright src tests examples && uv run mkdocs build --strict`. Expected: all pass.
- [ ] **Step 8: Commit.** `git commit -m "feat: run Pebble programs on the bench"`. The controller pushes, opens the PR and merges on green CI. Create no PyCPU tag.
