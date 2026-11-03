# PyCPU Plan 4: The Cockpit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the Bench into the Cockpit of spec §6 (layout A). It has Pebble source and machine code side by side, registers, memory, the stack and variables with changed values marked, and a zoom panel that drills from anything clicked down to live NAND gates. Its controls are play/pause with live updates over server-sent events, the four step sizes (gate, cycle, instruction, Pebble line, with step over and step into), rewind, and a way to load Pebble programs.

**Architecture:** `src/pycpu/bench/` becomes `src/pycpu/cockpit/` and is split by job. A `Cockpit` session object owns the `Computer`, the loaded program and the state before the last move, and does every move (`session.py`). `picture.py` turns it into the JSON the page draws. `app.py` holds only PyWeb routes, plus an `EventHub` that publishes the picture after every move. Pebble line steps and play run on the fast engine; a pause always lands in the gate engine, which is what the zoom panel reads. The translator gains a per-word frame map, so the Cockpit can show each Pebble variable at its real address.

**Tech Stack:** Python 3.14, uv, pytest, Hypothesis, ruff, strict pyright, `fromscratch-pyweb>=0.4.0` (`App`, `EventHub`, `EventStream`, `ServerEvent`, `TestClient.stream`), `pynet.loop` (`spawn`, `sleep`), `fromscratch-pebble>=0.4.0`, plain HTML/CSS/JS with no CDN, mkdocs-material.

**Spec:** `docs/superpowers/specs/2026-11-01-pycpu-design.md` (§6 "The Cockpit" is the contract; §2 goals 3–5, §4 "Faking it", §5 "Pause" and "Resume"). Roadmap and its "Notes for Plan 4": `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`.

## Global Constraints

- NAND is the single primitive. Nothing above `simulator.py` computes a logic result in Python, except test helpers, `peek`/`poke`, the fast engine and the output peripheral.
- **Never fake the gate view** (spec §4). The zoom panel shows only `circuit_view` of the paused gate engine. While playing, the panel says the machine must be paused to look inside; it never shows stale or made-up values.
- Pause lands just before the next instruction, and the state goes into the gate engine. Resume finishes the current instruction in the gates, then copies to the fast engine (spec §5). Line steps and play go through `Computer.resume`/`Computer.pause`, never around them.
- Live state goes over server-sent events from PyWeb (spec §6). Every route that moves the machine also publishes the new picture.
- The Cockpit's routes are plain `def` handlers on the event loop (never `blocking=True`), and play is a `pynet.loop.spawn`ed task on the same loop. The computer is only ever touched from one thread.
- Front end: one `page.html`, plain JS, no external scripts, fonts or CDNs (it must work offline). Colours as CSS variables with a dark-mode block; usable at 375 px wide.
- Siblings are PyPI releases (`fromscratch-<name>>=X.Y.Z`); never `path` or git sources.
- Never use `TYPE_CHECKING` or `from __future__ import annotations`.
- Documentation is as important as code, and ranks above every other rule here. See the Documentation Standard below. A task with weak docs is not done, however good its code is.
- Do not publish PyCPU: GitHub Pages stays off, `docs.yml` stays manual-only, no `series.yml` entry, no PyCPU version tag. `mkdocs build --strict` must pass at every commit.
- Work on branch `plan-4-the-cockpit`; one PR into `main` at the end, merged when CI is green.
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

**Every new page** goes in `mkdocs.yml` nav and in `KEY_IDEAS` in `tests/test_docs.py`, and the previous page's `## What's Next` links to it.

## Review Focus

- **Buttons pressed while playing.** A step, rewind or run sent during play gets a 409 that says to press pause first, and leaves the machine alone. Pause and loading a program both stop play cleanly. Tests in Task 6.
- **A line step that never reaches a new line.** Examples are a one-line endless loop (`while true { }`), a halted machine, and an assembly program. The step stops at `MAX_LINE_INSTRUCTIONS` with a note, refuses to move a halted machine with a note, and gives a 400 for assembly. It never hangs a request. Tests in Task 5.
- **A line step started part-way through an instruction** (after some gate steps). It finishes that instruction in the gates first and still stops at the next line. A step over a recursive call on the same line stops back in the caller's frame, never inside the callee's prologue. Tests in Task 5.
- **A browser tab that leaves during play, or two tabs open at once.** The subscription is dropped, play carries on to its end or pause, and both tabs get every event. Tests in Task 6.
- **Loading a new program while paused part-way through an instruction, or after a fault.** The changed marks, listing, variables and Pebble pane all describe the new program, and nothing from the old one leaks through. Tests in Tasks 3 and 4.

---

## The Cockpit Contract

This section is the contract for Tasks 2–7.

**The session.** `class Cockpit` (`src/pycpu/cockpit/session.py`) owns:
- `computer: Computer`
- `translated: TranslatedProgram | None` (None for assembly)
- `assembly: str` (the source text shown in the listing)
- `before: MachineState` (the state just before the last move, for changed marks)
- `last_gate: MicroStep | None` (the micro step of the last gate step, else None)
- `note: str | None` (one sentence about the last move, for example why a line step stopped)
- `playing: bool`

Every move sets `before` first, then clears `note` and `last_gate`. A move is a step, line step, rewind, run, play tick or load. Refusals are `class CockpitRefusal(Exception)`, which becomes a 400 with the Bench's usual `error`/`message` body. While playing, a move other than pause or load raises `class CockpitBusy(CockpitRefusal)`, which becomes a 409 with the message `"the computer is running: press pause first"`.

**The picture** (`machine_picture(cockpit) -> dict[str, object]`, in `picture.py`) keeps every key the Bench has today (`paused`, `phase`, `at_boundary`, `registers`, `pc`, `sp`, `flags`, `halted`, `halt_code`, `fault`, `output`, `instruction`, `memory`, `pebble`) and adds these:

| Key | Value |
|---|---|
| `running` | `cockpit.playing` |
| `changed` | `{"registers": [indexes], "pc": bool, "sp": bool, "flags": [names], "memory": [addresses]}`: what differs between `before` and now |
| `stack` | up to 16 cells (`address`, `word`, `text`, `part`) from `sp` upwards, `[]` when `sp` equals the memory size |
| `variables` | `null` for assembly, or when the current word's frame is not ready. Otherwise `{"function": name or null for the top level, "frame_pointer": r7, "names": [{"name", "kind": "parameter" or "variable", "hidden": bool, "address", "word", "value" (signed), "part"}]}` |
| `last_gate` | `null`, or `{"id", "path", "value"}` for the last gate step (`path` from `Circuit.scope_of`) |
| `note` | `cockpit.note` |
| `parts` | `{"registers": ["cpu.registers.r0", ...], "pc": "cpu.pc", "sp": "cpu.sp", "flags": "cpu.flags", "instruction": part_for_instruction(word)}` |

Each `memory`/`stack` cell gains `"part": "ram.word<address>"`.

While playing, the picture is read from the fast engine: `phase` is `"fetch"`, `at_boundary` is true, `instruction` is the word at `pc`, and `variables` and `last_gate` are null.

**Zoom targets** (`part_for_instruction(word: int) -> str`, in `picture.py`), chosen by opcode:

| Opcode | Part |
|---|---|
| ALU, CMP, ADDI | `cpu.alu` |
| LI, LHI | `cpu.write_back` |
| LOAD, STORE | `cpu.address_mux` |
| JMP, BR, CALL, RET | `cpu.next_pc` |
| PUSH, POP, GETSP, SETSP | `cpu.next_sp` |
| HALT | `cpu.halt` |

A test checks that every path in `parts` and every `part` exists (`Circuit.has_scope`).

**Routes** (in `app.py`; existing routes keep their bodies and errors):

| Route | Does |
|---|---|
| `GET /`, `GET /api/machine`, `GET /api/view`, `POST /api/step`, `/api/rewind`, `/api/run`, `/api/program`, `/api/pebble` | As the Bench. `/api/step`'s `size` also takes `"line"` (step over) and `"line_into"` (step into) |
| `GET /api/listing` | The whole loaded program: `{"rows": [{"address", "word", "text", "first", "labels", "pebble_line"}], "pebble": [lines] or null}`. `text` is the source line the word came from (`Program.lines`). `first` is true for the first word of its source line. `labels` lists the label names at this address |
| `GET /api/examples` | `[{"name", "title", "source"}]`, read from `src/pycpu/cockpit/examples/*.pebble` |
| `GET /api/events` | `EventStream` of `ServerEvent(json(picture), event="machine")`, one after every move and every play tick |
| `POST /api/play` | `{"speed": n}`, with n instructions a second from 1 to `MAX_SPEED`. Starts play and answers the picture at once |
| `POST /api/pause` | Stops play and pauses at an instruction boundary. If not playing, answers the picture unchanged |

**Pebble line step** (`Cockpit.step_line(*, into: bool) -> LineStep`). The start is `start_line = line_at(instruction_start.pc)` and `start_fp = instruction_start.registers[7]`. The step calls `computer.resume()`, which finishes a part-done instruction in the gates. Then, on the fast engine, it runs one instruction at a time. Before each instruction it checks the word at `pc` against `translated.frames[pc]` and `line_at(pc)`, and stops there when all of these hold:
- the frame is ready (not None);
- the line is not None;
- `(line != start_line or fp != start_fp)`, where `fp` is the fast engine's `r7`;
- for step over only, `fp >= start_fp` (the same frame or a caller's; the stack grows down).

It also stops when the machine halts, or after `MAX_LINE_INSTRUCTIONS` instructions. Then it calls `computer.pause()`. `LineStep(instructions: int, stopped: str)` has `stopped` set to `"line"`, `"halted"` or `"limit"`, and `note` says it in a sentence. A halted machine does not move: `stopped` is `"halted"`, `instructions` is 0, and the note is `"The program has finished, so there is no next line."`. Runtime routine words have no line and no frame, so they never stop a line step.

**Frame map** (Task 4, in the translator):
- `@dataclass(frozen=True) class Slot: name: str; offset: int; kind: str; hidden: bool`. `offset` is relative to `r7`: parameter i of N is at `2 + (N-1-i)`, variable j is at `-1 - j`. `hidden` is true for compiler-made names that are not Pebble identifiers, such as `$for_...`.
- `@dataclass(frozen=True) class FrameLayout: function: str | None; slots: tuple[Slot, ...]`. `function` is None for the top-level program.
- `TranslatedProgram.frames: tuple[FrameLayout | None, ...]` has one entry per word: the layout of the code whose frame `r7` points at just before that word runs.
- It is None for runtime and data words, for every prologue word (from the function's label through its last zeroing `push r0`), and for the `ret` word of each `RETURN`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pycpu/fast.py` | Build the handler table once; read-only `pc`, `halted` and `register(index)` |
| `src/pycpu/translator/program.py`, `codegen.py`, `subset.py`, `__init__.py` | One size check; the frame map (`Slot`, `FrameLayout`, `frames`); tidy-ups |
| `src/pycpu/cockpit/__init__.py` | Public names: `create_cockpit`, `Cockpit`, `machine_picture` |
| `src/pycpu/cockpit/session.py` | `Cockpit`, `LineStep`, `CockpitRefusal`, `CockpitBusy`, loading, steps, line steps, play ticks |
| `src/pycpu/cockpit/picture.py` | `machine_picture`, `pebble_picture`, `listing`, `part_for_instruction`, changed marks, stack and variables |
| `src/pycpu/cockpit/app.py` | `create_cockpit`: routes, the event hub, the play task |
| `src/pycpu/cockpit/page.html` | Layout A |
| `src/pycpu/cockpit/examples/*.pebble` | Programs the page offers to load; `tour.pebble` uses every subset feature |
| `src/pycpu/__main__.py` | `python -m pycpu` opens the Cockpit with `tour.pebble` loaded |
| (deleted) `src/pycpu/bench/` | Replaced by `cockpit/` |
| `tests/test_cockpit.py` (renamed from `test_bench.py`), `tests/test_cockpit_session.py`, `tests/test_line_steps.py`, `tests/test_live.py`, `tests/test_frames.py`, `tests/test_examples_programs.py` | Tests |

**Pages in reading order.** The nav's "The Bench" entry becomes a section, "The Cockpit", which stays the last concept section before Reference:

| Page | Task | Teaches |
|---|---|---|
| `concepts/the-cockpit.md` (renamed from `the-bench.md`) | 2, grown in 3, 4, 7 | What each pane shows and where it reads it from; the routes; changed marks; zooming from a register, word or instruction to its circuit |
| `concepts/stepping-a-pebble-line.md` | 5 | A line step runs on the fast engine and pauses at the next line; step over and step into; why not on gates (measured) |
| `concepts/watching-it-run.md` | 6 | Play and pause; server-sent events; why the zoom panel needs a pause |
| `concepts/a-tour-of-the-cockpit.md` | 8 | One Pebble line followed all the way down to a single NAND gate |

---

### Task 1: Carried tidy-ups

**Files:**
- Modify: `src/pycpu/fast.py`, `src/pycpu/translator/program.py`, `src/pycpu/translator/subset.py`, `docs/concepts/what-happens-when-things-go-wrong.md`, `pyproject.toml`/`uv.lock` and tests marked `# Pebble v0.4.1:` (only if 0.4.1 is on PyPI)
- Test: `tests/test_fast.py`, `tests/test_translator.py`, `tests/test_functions.py`, `tests/test_docs.py`

**Interfaces:**
- Produces: `FastMachine.pc -> int`, `FastMachine.halted -> bool` (properties), `FastMachine.register(index: int) -> int`. Task 5's line step reads these on every instruction instead of building a `state()`.

- [ ] **Step 1: Write failing tests.**
  - `pc`, `halted` and `register(i)` agree with `state()` after a few steps of a small program.
  - `_handlers` is built once: two `step()` calls use the same dict object, checked by `id()` through a test-only attribute named in the test.
  - `translate` refuses an oversized program through one size check. Assert that the `UnsupportedFeature(TOO_BIG)` path still fires for code too big and for code that fits but leaves no room for main's frame.
  - Every label the translator writes after `__fn_<name>` keeps the property `function_label`'s docstring relies on: an addition never starts with `_` or `x`. Check it over the corpus in `tests/pebble_programs/`.
  - The faults page mentions `"needs more stack room"`.
- [ ] **Step 2: Run** `uv run pytest tests/test_fast.py tests/test_translator.py tests/test_functions.py tests/test_docs.py -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement.**
  - Build the handler table in `__init__`.
  - Add the three readers.
  - In `translate`, compute the size once by using `TranslatedProgram.memory_needed`, and drop the inline sum (Plan 3 ruling 23).
  - Change `subset.py`'s `if first` truthiness check (the one near `first_place`) to `first is None` where None is meant.
  - Add a paragraph and example to the faults page for `"The program needs more stack room than there is"`, saying when it appears (a small Bench, Plan 3 ruling 24).
- [ ] **Step 4: Pebble floor.** Run `uv run --with fromscratch-pebble==0.4.1 python -c "import pebble"`.
  - If 0.4.1 resolves: raise the floor to `fromscratch-pebble>=0.4.1`, `uv lock`, and remove every `# Pebble v0.4.1:` workaround (grep for the marker), keeping the tests they guarded.
  - If it does not resolve: leave the floor, and say so in the report.
- [ ] **Step 5: Run** `uv run pytest`. Expected: PASS. Record the fast engine's instructions per second before and after the handler-table change with `scripts/measure_engines.py`, in the report.
- [ ] **Step 6: Commit.** `git commit -m "refactor: carried tidy-ups before the Cockpit"`

---

### Task 2: The Bench becomes the Cockpit

**Files:**
- Create: `src/pycpu/cockpit/{__init__,session,picture,app}.py`, `src/pycpu/cockpit/page.html` (moved from `bench/`)
- Delete: `src/pycpu/bench/`
- Rename: `tests/test_bench.py` to `tests/test_cockpit.py`, and `docs/concepts/the-bench.md` to `docs/concepts/the-cockpit.md`
- Modify: `src/pycpu/__main__.py`, `mkdocs.yml`, `tests/test_docs.py`, `README.md`, every doc and docstring that says "Bench" or links `the-bench.md`, `pyproject.toml` (package data for `page.html`)
- Test: `tests/test_cockpit_session.py`

**Interfaces:**
- Produces: `Cockpit(address_bits: int = RAM_ADDRESS_BITS)`, which starts with `DEMO_PROGRAM` loaded and paused. Its methods are:
  - `load_assembly(source: str) -> None`
  - `load_pebble(source: str) -> None`
  - `step(size: StepSize, count: int = 1) -> None`
  - `rewind() -> None`
  - `run(instructions: int) -> int`
  
  `CockpitRefusal`, `CockpitBusy`, `machine_picture(cockpit: Cockpit) -> dict[str, object]` and `create_cockpit(address_bits: int = RAM_ADDRESS_BITS, start_example: str | None = None) -> App` are also produced. `start_example` is a file stem in `cockpit/examples/`, used from Task 7. Until then any value other than None raises `ValueError`.

- [ ] **Step 1: Update the doc first.** Rename the page and retitle it "The Cockpit". Its analogy is an aeroplane cockpit: every dial in view at once, and a pilot who can freeze the flight. It says that the Bench has grown into the Cockpit and that its routes work as before, and keeps every Try It working against `create_cockpit`. Move its `KEY_IDEAS` entry, and add `"cockpit"`.
- [ ] **Step 2: Write failing tests.** Move `test_bench.py` to `test_cockpit.py` with only the import and name changes, and keep every assertion. In `test_cockpit_session.py`, check each `Cockpit` method directly at 6 address bits (8 for Pebble):
  - a load refused by the assembler raises `CockpitRefusal` naming the line, and leaves the machine as it was;
  - every move sets `before` to the state just before it;
  - `run` resumes and pauses again.
- [ ] **Step 3: Run** `uv run pytest tests/test_cockpit.py tests/test_cockpit_session.py tests/test_docs.py -v`. Expected: FAIL (no `pycpu.cockpit`).
- [ ] **Step 4: Implement** the move and split. Route handlers only parse the request, call the session and answer; the session holds every rule now in `step_paused`, `load_source` and `load_pebble`. `python -m pycpu` prints `"Building the computer from NAND gates..."` and then `"The Cockpit is open at http://127.0.0.1:8765"`.
- [ ] **Step 5: Run** `uv run pytest && uv run mkdocs build --strict && grep -rn "bench" src docs README.md mkdocs.yml`. Expected: PASS. The grep shows only deliberate history, such as "the Bench grew into the Cockpit", or the word "bench" in plain English.
- [ ] **Step 6: Commit.** `git commit -m "refactor: grow the Bench into the Cockpit session and app"`

---

### Task 3: Changed marks, the stack, the listing and zoom targets

**Files:**
- Modify: `src/pycpu/cockpit/picture.py`, `session.py`, `app.py`, `docs/concepts/the-cockpit.md`
- Test: `tests/test_cockpit.py`

**Interfaces:**
- Consumes: Task 2's `Cockpit`.
- Produces the contract's `changed`, `stack`, `last_gate`, `note`, `parts` and cell `part` keys, plus these:
  - `part_for_instruction(word: int) -> str`
  - `listing(cockpit: Cockpit) -> dict[str, object]`
  - `GET /api/listing`

- [ ] **Step 1: Doc first.** Add sections to `the-cockpit.md`, with Try Its through `TestClient`:
  - "What Just Changed": one instruction step on `DEMO_PROGRAM`, printing `changed`.
  - "The Whole Program": the first rows of `/api/listing` for a Pebble program, with its labels and Pebble lines.
  - "Zooming From Anything": `parts["instruction"]` for an `add`, then `/api/view` of it.
  - "Following a Gate": one gate step, then `last_gate`.
- [ ] **Step 2: Write failing tests.**
  - After `li r1, 5`: `changed == {"registers": [1], "pc": True, "sp": False, "flags": [], "memory": []}`.
  - After a `push`: `sp` and the pushed address are marked.
  - After a rewind: the marks compare against the state before the rewind.
  - Loading a program clears `last_gate` and `note`. Its `changed` compares against the old machine, and the listing is the new program's. Test this after gate steps part-way through an instruction and after a fault (Review Focus).
  - `stack` is `[]` at power-on. After two pushes it holds 2 cells, top first; it is never longer than 16.
  - `part_for_instruction` follows the table for one word of each opcode. Every path in `parts`, every cell `part` and every table entry passes `has_scope` on a real `GateMachine(6)`.
  - `/api/listing` for `DEMO_PROGRAM`: one row per word, `labels` holds `["loop"]` at its address, `set r1, 0xFFFF` has two rows with `first` true then false, and `pebble` is null. For a Pebble program, every row's `pebble_line` equals `line_at(address)`.
  - A gate step sets `last_gate.path == computer.gate.simulator.circuit.scope_of(id)`. An instruction step leaves it null.
- [ ] **Step 3: Run** `uv run pytest tests/test_cockpit.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement.** `changed` compares `before` with the live state field by field. Memory is compared with a tuple scan, which is fine at 4K: say so in a comment, with the measured time from a slow test that pins it under 0.05 s at full size.
- [ ] **Step 5: Run** the same tests and `uv run pytest -m slow --no-cov tests/test_cockpit.py`. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: mark what changed and link every value to its circuit"`

---

### Task 4: Pebble variables at their real addresses

**Files:**
- Modify: `src/pycpu/translator/codegen.py`, `program.py`, `__init__.py`, `src/pycpu/cockpit/picture.py`, `docs/concepts/variables-in-memory.md`, `docs/concepts/the-cockpit.md`
- Test: `tests/test_frames.py`, `tests/test_cockpit.py`

**Interfaces:**
- Produces: `Slot`, `FrameLayout`, `TranslatedProgram.frames` (exported from `pycpu.translator`) and the picture's `variables` key, all as in the contract. Task 5 reads `frames`.

- [ ] **Step 1: Doc first.**
  - Add "Seeing Them in the Cockpit" to `variables-in-memory.md`. Its Try It loads the countdown into a `Cockpit(8)`, takes instruction steps until the Pebble line is the `print` line, and prints each variable's name, address and value.
  - Add a short "Variables" section to `the-cockpit.md` that explains `hidden` names: the compiler's own helpers, such as a `for` loop's end value.
- [ ] **Step 2: Write failing tests** in `tests/test_frames.py`:
  - For `fn add(a, b) { let c = a + b return c }`: the layout is `a` at +3, `b` at +2, `c` at −1, with kinds `parameter`/`variable`.
  - `frames` has one entry per word.
  - It is None on every runtime and data word, every prologue word and every return `ret`, and set everywhere else in a function's code.
  - Property over the corpus, run on `FastMachine`: whenever `frames[pc]` is set and is not the top level, the word at `r7 + 1` is a return address whose previous word is a `call`. Whenever it is the top level, `r7` equals the frame main's prologue made.
  - For a `for i in range(3)` program, the hidden names are marked `hidden`.
  - Picture: at the start of `print(n)` in the countdown, `variables.names` shows `n` with the value printed next. Inside `__print_int` it is null. For assembly it is null. For a negative value, `value` is signed and `word` is the raw word.
- [ ] **Step 3: Run** `uv run pytest tests/test_frames.py tests/test_cockpit.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement.** The code generator records, for each line it writes, which frame (if any) is ready. `translate` maps that through `Program.lines` to words, just as `pebble_lines` is built. Slots come from the parameters and `CheckedCode.variables`, in slot order.
- [ ] **Step 5: Run** the same tests and `uv run pytest`. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: show each Pebble variable at its real address"`

---

### Task 5: Stepping a Pebble line

**Files:**
- Modify: `src/pycpu/cockpit/session.py`, `app.py`
- Create: `docs/concepts/stepping-a-pebble-line.md`
- Test: `tests/test_line_steps.py`

**Interfaces:**
- Consumes: `FastMachine.pc`/`halted`/`register` (Task 1), `TranslatedProgram.frames` (Task 4).
- Produces: `MAX_LINE_INSTRUCTIONS = 10_000`, `@dataclass(frozen=True) class LineStep: instructions: int; stopped: str`, `Cockpit.step_line(*, into: bool) -> LineStep`, and `/api/step` with `size` `"line"` or `"line_into"` (`count` must be 1).

- [ ] **Step 1: Doc first.** `stepping-a-pebble-line.md`.
  - Analogy: reading aloud with a bookmark. "Next line" reads to the next line at normal speed and puts the bookmark there. A footnote is a function: "step over" reads the whole footnote and comes back, and "step into" follows it.
  - Explain that a line is many instructions, and give the roadmap's measured figures for why a line runs on the fast engine and not on the gates (median 22 instructions; about 490,000 gate steps per line at full size; a `print` line about 6.7 million). Then explain the pause into the gates at the next line, frames and `r7` for step over, routines never stopping a step, and the 10,000-instruction limit.
  - Try It: load the countdown into `create_cockpit(address_bits=8)` through `TestClient`. Line-step until halted, printing each line reached and its instruction count. Then do one step into and one step over on a call, using a two-line function program.
  - Nav after The Cockpit. `KEY_IDEAS`: `["line", "step over", "step into"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_line_steps.py` (8 address bits):
  - Countdown: the sequence of lines reached matches the sequence of distinct consecutive lines that `run_pebble`'s instruction trace visits. Compute that trace in the test from `line_at` and `frames` on a separate `FastMachine`.
  - Every stop is at an instruction boundary, paused, with `instruction_start.pc` on a ready, located word.
  - Over versus into: for `fn double(n) {\n return n * 2\n}\nprint(double(3))`, one step into from the `print` line stops on line 2. A step over from the same place stops after the call on a line in main, or halts at the end, with output `6\n`.
  - Recursion on one line (`fn f(n) { if n == 0 { return 0 } return f(n - 1) }` written with `return f(n - 1)` on its own line): a step over from that line stops in the caller's frame (`fp` greater than the start) and never in the callee's prologue (Review Focus).
  - Starting after 50 gate steps part-way through an instruction: the step finishes it and stops at the next line (Review Focus).
  - `while true { }` on one line: `stopped == "limit"`, `instructions == MAX_LINE_INSTRUCTIONS`, and a note mentions 10,000 (Review Focus).
  - Halted: no move, `stopped == "halted"`, and the contract's note.
  - An assembly program: a 400 saying line steps need a Pebble program. `count` of 2: a 400.
  - A division-by-zero program: the line step halts with the fault, and the Pebble pane blames the right line.
- [ ] **Step 3: Run** `uv run pytest tests/test_line_steps.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** per the contract.
- [ ] **Step 5: Run** the same tests. Add one `@pytest.mark.slow` test at full size that a line step on the tour countdown answers in under 1 s through `TestClient`, and record the measured time in the report. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: step a Pebble line, over or into calls"`

---

### Task 6: Play, pause and live updates

**Files:**
- Modify: `src/pycpu/cockpit/session.py`, `app.py`
- Create: `docs/concepts/watching-it-run.md`
- Test: `tests/test_live.py`

**Interfaces:**
- Produces: `MAX_SPEED = 100_000`, `TICK_SECONDS = 0.1`, `Cockpit.start_playing() -> None`, `Cockpit.play_tick(instructions: int) -> bool` (False once halted), `Cockpit.stop_playing() -> None`, the parameter `create_cockpit(..., tick_seconds: float = TICK_SECONDS)`, and the routes `/api/play`, `/api/pause` and `/api/events`.

- [ ] **Step 1: Doc first.** `watching-it-run.md`.
  - Analogy: live radio commentary of a match. The commentator (the server) talks whenever something happens, and nobody has to keep ringing up to ask the score. Pressing pause is the replay camera.
  - Explain that play runs the fast engine in small slices (`speed × tick` instructions, carrying any fraction to the next tick), sends one `machine` event per tick, and pauses into the gates at the end or on Pause.
  - Explain why the zoom panel shows nothing live while playing: the gates are not running then, and showing old values would be faking it.
  - Link PyWeb's server-sent events page by name.
  - Try It: in `TestClient`, `POST /api/play` at speed 50 with `tick_seconds=0.01`, collect 3 events with `client.stream("/api/events", count=3)`, then pause, and print each event's `pc` and `running`.
  - Nav after Stepping a Pebble Line. `KEY_IDEAS`: `["live", "event", "pause"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_live.py`:
  - Every moving route publishes exactly one `machine` event, with the same JSON it answered.
  - Play at speed 20 with tick 0.05 runs 1 instruction per tick, and the events' `pc` values advance.
  - Speed 3 with tick 0.1 carries fractions: 3 instructions over 10 ticks.
  - Play to a halt ends with `running` false, `paused` true and the final output, and publishes one last event.
  - During play, step, rewind and run answer 409 with the contract's message and change nothing (Review Focus).
  - Pause stops play, and the next picture is paused at a boundary.
  - Loading a program stops play first (Review Focus).
  - A second `/api/play` while playing is a 409.
  - Speed 0, `MAX_SPEED + 1` or `true` is a 400.
  - Two subscribers both receive every event. One stream closing early leaves play running to its end and drops the subscriber count by one (Review Focus).
  - While playing, the picture has `variables` and `last_gate` null and `at_boundary` true. `/api/view` still answers, from the gate engine as last paused. The doc says it is the last paused view.
- [ ] **Step 3: Run** `uv run pytest tests/test_live.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement.** `/api/play` checks the body, calls `start_playing` and spawns `_play_loop`. Each pass of the loop calls `play_tick`, publishes the picture and awaits `sleep(tick_seconds)`, until `playing` is false or a tick reports a halt; then it calls `stop_playing`. Each tick runs `computer.run`. `start_playing` calls `resume`, and `stop_playing` calls `pause`, so the gate engine is loaded only at the end.
- [ ] **Step 5: Run** the same tests. Expected: PASS, and no test takes over 2 s.
- [ ] **Step 6: Commit.** `git commit -m "feat: play and pause the Cockpit with live updates"`

---

### Task 7: The Cockpit page and its example programs

**Files:**
- Modify: `src/pycpu/cockpit/page.html` (rewrite), `app.py`, `src/pycpu/__main__.py`, `docs/concepts/the-cockpit.md`
- Create: `src/pycpu/cockpit/examples/` with `tour.pebble`, `countdown.pebble`, `times-table.pebble`, `factorial.pebble`, `greeting.pebble` and `divide-by-zero.pebble`, each starting with a `#` comment line that is its title
- Test: `tests/test_examples_programs.py`, `tests/test_cockpit.py`

**Interfaces:**
- Consumes: every route and picture key above.
- Produces: `GET /api/examples`, `create_cockpit(start_example="tour")`, and `python -m pycpu` loading `tour`.

- [ ] **Step 1: Doc first.** Rewrite the top of `the-cockpit.md` with an ASCII drawing of layout A:
  - top left, Pebble with the running line marked;
  - top right, machine code from `/api/listing` with the current word marked and the running line's words shaded;
  - middle, registers, flags, the stack and variables, with changed values marked;
  - bottom, the zoom panel.

  Name each control: Play/Pause with a speed, the step sizes Gate, Cycle, Instruction, Line and Line into, Rewind, Load (examples or your own). Explain how clicking anything with a `part` opens it in the zoom panel, how clicking a Pebble line shades its machine code, and "show this gate" after a gate step.
- [ ] **Step 2: Write failing tests.**
  - Every example translates, fits 4K (`memory_needed <= RAM_WORDS`) and matches `pebble.run_source` on the VM. The exception is `divide-by-zero`, which faults with `DIVIDE_BY_ZERO` on the VM's line.
  - `tour.pebble` uses every subset feature, which is spec §9's "a program using every subset feature". Its bytecode contains `CALL` of a function that calls itself, `JUMP_IF_FALSE`, `JUMP_IF_FALSE_OR_POP`, `JUMP_IF_TRUE_OR_POP`, `NOT`, `MULTIPLY`, `FLOOR_DIVIDE`, `MODULO`, `NEGATE`, `PRINT` of text and of a number, and a `for` over `range`.
  - `/api/examples` lists them in a fixed order with `tour` first, each with the title from its comment.
  - `create_cockpit(8, start_example="countdown")` starts with that Pebble loaded and paused at its first line. An unknown name raises `ValueError`.
  - The page HTML has the ids the script uses: `pebble`, `listing`, `registers`, `flags`, `stack`, `variables`, `output`, `zoom`, `crumbs`, `parts`, `gates`, `play`, `pause`, `speed`, `examples`, `source`. It loads no external URL (no `http` in `src=`/`href=`). It holds the `@media (prefers-color-scheme: dark)` block.
- [ ] **Step 3: Run** `uv run pytest tests/test_examples_programs.py tests/test_cockpit.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement the page.**
  - Use a CSS grid for layout A that collapses to one column under 44rem.
  - Listen to `/api/events` with `EventSource` and redraw from every `machine` event. Buttons still POST, and draw from their answer too, so the page works if the stream drops.
  - While running, disable the step buttons and show "Pause to look inside the gates" in the zoom panel.
  - Mark changed values with a highlight and an accessible text marker ("changed"), and mark hidden variables in dim text with a title explaining them.
  - Keep the PATHS and LEVELS explanations from the Bench.
- [ ] **Step 5: Check in a real browser** at full size with `uv run python -m pycpu`:
  - play the tour, then pause;
  - line step, both into and over;
  - instruction step;
  - click `r1` and land in `cpu.registers.r1`;
  - click the current instruction and land in its part;
  - take a gate step and use "show this gate";
  - load each example;
  - check at 375 px wide and in dark mode.

  Expect no console errors. Record what was checked in the report.
- [ ] **Step 6: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "feat: the Cockpit page in layout A, with example programs"`

---

### Task 8: The tour, the story, and the hand-off to Plan 5

**Files:**
- Create: `docs/concepts/a-tour-of-the-cockpit.md`
- Modify: `docs/index.md`, `docs/from-scratch.md`, `README.md`, `docs/concepts/watching-it-run.md` (its What's Next), `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`, `examples/` (add `examples/cockpit_tour.py` and its line in `tests/test_examples.py`)
- Test: `tests/test_docs.py`, `tests/test_examples.py`

- [ ] **Step 1: Write `a-tour-of-the-cockpit.md`**, the last concept page.
  - Analogy: following one letter through the post, from the postbox to the doormat.
  - Try It: through `TestClient` at 8 address bits, load `countdown`.
    - Line-step to `n = n - 1`.
    - Instruction-step to that line's `sub`.
    - Read `parts["instruction"]` (`cpu.alu`).
    - Gate-step through the instruction until `last_gate.path` starts with `cpu.alu.adder`.
    - Print that gate's wires from `/api/view`.
    - Line-step on, and print the variable `n`, now changed from 2 to 1.
  - Every printed value is real output. The page tells the whole climb in one breath, linking back to each layer's page.
  - `KEY_IDEAS`: `["tour", "pebble line", "gate"]`.
- [ ] **Step 2: Write `examples/cockpit_tour.py`**, the same walk as a script, and add it to `tests/test_examples.py`.
- [ ] **Step 3: Update the story.**
  - `index.md`, `from-scratch.md` and the README ladder: the Cockpit is here, and `python -m pycpu` opens it with the tour loaded. Plan 5 brings it into PyStack and the first release.
  - The README Concepts table gets the new pages in nav order.
- [ ] **Step 4: Definition-of-done dry run against spec §9.** Write the checklist in the roadmap's new "Notes for Plan 5", with a test or page as evidence for each item. Only PyStack's launcher and `import "cpu"` are left. Also add anything this plan learned: measured line-step and play timings, the size of the `/api/events` picture at 4K, and any minors parked in the ledger.
- [ ] **Step 5: Final verification.** `uv run pytest && uv run pytest -m slow --no-cov && uv run pytest --hypothesis-profile=thorough tests/test_frames.py tests/test_line_steps.py && uv run ruff check . && uv run ruff format --check . && uv run pyright src tests examples && uv run mkdocs build --strict`. Expected: all pass.
- [ ] **Step 6: Commit.** `git commit -m "docs: a tour of the Cockpit, from a Pebble line to a gate"`. The controller pushes, opens the PR and merges on green CI. Create no PyCPU tag.
