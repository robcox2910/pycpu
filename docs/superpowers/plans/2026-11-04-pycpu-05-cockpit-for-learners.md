# PyCPU Plan 5: The Cockpit for Learners Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Cockpit so a curious 12-year-old can learn from it alone. The new layout is C: the program sits on the left and a magnifying glass on the right, with a trail that works as a ladder. There is one Step button that follows the depth you are looking at, and a "What just happened" sentence after every move. Only the newest change glows, and guided walks are the front door. Nothing ever needs scrolling.

**Architecture:** The machine, translator and gate engine are unchanged. `session.py` gains the four depths and a single `step_at`. A new `explain.py` writes the "What just happened" sentence from the real change, and a new `walks.py` loads TOML walk files and replays them on the real machine. `picture.py` gains a few read-only keys and a part view that reads real wires through named taps on `GateMachine`. `page.html` is rewritten for layout C. Walks are data in `src/pycpu/cockpit/walks/*.toml`, each checked by a test that runs its own "Now you try" solution.

**Tech Stack:** Python 3.14, uv, pytest, Hypothesis, ruff, strict pyright, the stdlib `tomllib`, `fromscratch-pyweb>=0.4.0`, `fromscratch-pynet>=0.2.0`, `fromscratch-pebble>=0.4.1`, plain HTML/CSS/JS with no CDN, and mkdocs-material.

**Spec:** `docs/superpowers/specs/2026-11-04-pycpu-cockpit-for-learners-design.md` (approved 2026-11-04) is the authority for this plan. It builds on `docs/superpowers/specs/2026-11-01-pycpu-design.md`, the Plan 4 contract in `docs/superpowers/plans/2026-11-03-pycpu-04-the-cockpit.md`, and the roadmap's "Notes for Plan 5" in `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`. PyStack integration and the first release become Plan 6.

## Global Constraints

- NAND is the single primitive. Nothing above `simulator.py` computes a logic result in Python, except test helpers, `peek`/`poke`, the fast engine and the output peripheral.
- **Never fake anything.**
  - The glass draws only real values: circuit wires read from the paused gate engine, or the machine's real state.
  - Walks reach a moment by really running the machine there (fast engine, then pause), never by setting state.
  - While playing, the glass says "Pause to look inside the gates".
- **One screen.**
  - At 1280×720 the page never scrolls; panes may scroll inside themselves.
  - Whatever a button changes is visible without scrolling.
  - At 375 px wide, one column is fine, with the glass above the program.
- The Plan 4 HTTP contract stays: existing routes, bodies, errors and picture keys keep working. Extend it, and update a test only where this plan changes the behaviour it pins.
- Routes are plain `def` handlers on the event loop (never `blocking=True`), and play stays a spawned task. The computer is touched from one thread only.
- Front end: one `page.html`, plain JS, no external URLs (it must work offline). Text goes in through `textContent`, never `innerHTML`. Colours are CSS variables with a dark-mode block.
- Siblings are PyPI releases (`fromscratch-<name>>=X.Y.Z`); never `path` or git sources.
- Never use `TYPE_CHECKING` or `from __future__ import annotations`.
- Documentation ranks above every other rule (see the Documentation Standard).
- **Nothing is exposed until the owner is happy to show people.** That means:
  - no GitHub Pages, no push trigger in `docs.yml`, no `series.yml` entry;
  - no PyCPU tag, release or PyPI publish;
  - no links from or integration with other series projects (PyStack included).
- `mkdocs build --strict` passes at every commit.
- Work on branch `plan-5-cockpit-for-learners`, with one PR into `main` at the end, merged when CI is green.
- Conventional commits, ending with the `Co-Authored-By` line.

## Documentation Standard

This is the same as Plan 4, whose wording is binding (`docs/superpowers/plans/2026-11-03-pycpu-04-the-cockpit.md`, "Documentation Standard"):
- Write the doc first.
- Use the section order:
  1. an analogy heading;
  2. a table;
  3. `## Try It`;
  4. `## How It Works`, with an ASCII diagram;
  5. `## Why Does This Matter?`;
  6. `## What's Next`.
- Write for a curious 12-year-old.
- Every exact figure is printed by a block that `tests/test_docs.py` runs (any block with an `# Output:` marker) or is pinned by a test.
- Every new page goes in `mkdocs.yml` and in `KEY_IDEAS`, and the previous page's What's Next links to it.

One addition for this plan: **the page's own words are docs too.** Every step label, "What just happened" sentence and walk sentence is read by a 12-year-old. Each must make sense with no other help, and each is pinned by a test.

## Review Focus

- **A learner presses Step at a depth that cannot move.** Examples: line depth on an assembly program, or any depth once the machine has halted. The page shows a plain sentence and leaves the machine unchanged, never an error dump. Tests in Task 2.
- **Step at a higher depth started part-way through a lower one.** Examples: line depth after some gate steps, or instruction depth mid-beat. The step finishes the lower move first, and the sentence describes everything that ran. Tests in Tasks 2 and 3.
- **A walk opened while playing, mid-instruction, or after the learner loaded their own program.** Play stops, the walk's program loads cleanly, and nothing from before leaks into its first picture. Tests in Task 5.
- **"Now you try" overshoot.** Once the check has passed it stays passed (it is latched), so a learner who keeps pressing Step past `n == 0` to the halt has still done it. Tests in Task 5.
- **An unknown or stale walk link** (`#walk=nonsense`). The server answers 404 with a plain message, and the page falls back to the walk list with one sentence saying the walk was not found. Tests in Tasks 5 and 6.

---

## The Learners' Contract

This section is the contract for Tasks 2–7.

**Depths.** `class Depth(StrEnum)` in `session.py` has `LINE = "line"`, `INSTRUCTION = "instruction"`, `PART = "part"` and `GATE = "gate"`. `Cockpit.step_at(depth: Depth) -> None` maps them to moves:

| Depth | Move |
|---|---|
| LINE | `step_line(into=False)` |
| INSTRUCTION | `step(StepSize.INSTRUCTION)` |
| PART | `step(StepSize.CYCLE)` |
| GATE | `step(StepSize.GATE)` |

A depth that cannot move does not raise. Two cases:
- **LINE on assembly:** the note is `NO_LINES_NOTE = "This program is machine code, so it has no Pebble lines to step. Look closer to step an instruction."` and the machine is unchanged.
- **Any depth on a halted machine:** the note is `FINISHED_NOTE`.

**Loads mark nothing changed.** After any load, `before` is the loaded state. This changes Plan 4's rule, and its test is updated.

**Picture additions** (`machine_picture`):

| Key | Value |
|---|---|
| `steps` | `{"line": "Step one line ▸", "instruction": "Step one instruction ▸", "part": f"Step one {part_name} beat ▸", "gate": "Step one gate ▸"}`. `part_name` is `PART_NAMES[parts["instruction"]]`. |
| `happened` | The "What just happened" sentence for the last move, or `null` before any move and after a load. |
| `walk` | `null`, or the active walk's progress (see Walks). |

`PART_NAMES` lives in `picture.py` and must cover every part in Plan 4's zoom table:

| Part | Name |
|---|---|
| `cpu.alu` | ALU |
| `cpu.write_back` | write-back |
| `cpu.address_mux` | memory address |
| `cpu.next_pc` | next-instruction |
| `cpu.next_sp` | stack pointer |
| `cpu.halt` | halt |
| `cpu` | CPU |

**What just happened** (`explain.py`). The entry point is `describe_move(depth: Depth, start: MachineState, after: MachineState, micro: MicroStep | None, translated: TranslatedProgram | None, ran: int) -> str`. `start` is `instruction_start` before the move. The sentence is built from real values only:
- **INSTRUCTION:** one template per opcode, plus one per ALU function, filled with the real operand and result values. Example: `sub r1, r1, r2` with r1=2 and r2=1 gives exactly `"The ALU took 1 away from 2. The answer, 1, went into r1."`.
- **PART:** fetch gives `"Fetch: the CPU read the word at address {pc}, which says {text}."`. Execute gives the INSTRUCTION sentence for the instruction that just finished.
- **GATE:** a gate step gives `"Gate {id} in the {part words} worked out a {value}."`. `part words` is the deepest scope name of `scope_of(id)` turned into words (`half_adder#1.xor` gives "XOR"). A clock or end step gives the existing no-gate note.
- **LINE:** `"Line {n} ran {k} instructions: {opcode words}."`, plus `" {name} changed from {old} to {new}."` for each visible (not hidden) variable that changed.

**Part view.**
- `GateMachine.taps: dict[str, dict[str, Bus]]` is recorded while the CPU is wired up, so it is read-only after build. It has one entry per part in `PART_NAMES` except `cpu`, naming that part's input and output buses. For the ALU these are `a`, `b`, `result` and `flags`; each other part gets the buses the builder finds meaningful.
- `part_picture(cockpit, path) -> {"path", "name", "inputs": [{"name", "value"}], "outputs": [{"name", "value"}]}`. Each value is the bus read with `simulator.get` on every bit, so it is the real wire value.
- `GET /api/part?path=` answers `part_picture`. An unknown path gets 404. While playing it answers 409 with `BUSY_MESSAGE`, because there are no live wires to read.

**Walks** (`walks.py`). Walk files are `src/pycpu/cockpit/walks/<name>.toml`:

```toml
title = "A line of Pebble is many tiny instructions"
example = "countdown"            # an example name, or `source = """..."""` inline
see_also = "stepping-a-pebble-line"   # the concept page that links here

[[steps]]
say = "This is the countdown. The yellow line runs next."
do = "start"                     # see the action list below
look = "line"                    # line | instruction | part | gate, and the glass shows this depth
show = "pebble.line"             # optional: what to highlight

[try]
task = "Press Step until n is 0."
look = "line"
check = "variable n == 0"
solution = ["step line", "step line", "..."]   # actions a test runs to prove the task can be done
```

- **Actions:**
  - `start` (load the example and pause);
  - `step <depth>`;
  - `run to line <n>`, using the fast engine and pause, like a line step but to a fixed line, capped at `MAX_LINE_INSTRUCTIONS`;
  - `step gate until <scope prefix>`, gate steps until `last_gate.path` starts with the prefix, capped at `MAX_GATE_STEPS`.
- **Checks** (one per walk):
  - `variable <name> == <int>`;
  - `line == <int>`;
  - `register r<i> == <int>`;
  - `output contains "<text>"`;
  - `halted`.
- `class WalkError(ValueError)` is raised for a bad file, action or check. `load_walks() -> tuple[Walk, ...]` reads the folder in `WALK_ORDER`. A walk that fails to load is a test failure, never a page crash.
- **Session state:** `Cockpit.walk: WalkProgress | None`, with `WalkProgress` holding `name`, `step`, `off_script: bool` and `done: bool`.
  - `Cockpit.go_to_walk(name: str, step: int) -> None` stops play, then replays the walk from `start` through `steps[step]`. That makes it deterministic, so Back and "Back to the walk" both use it. `step == len(steps)` means the try stage.
  - Any other move while a walk is active sets `off_script = True`.
  - After every move, while at the try stage, the check is evaluated. Once true, `done` stays true.
- **Picture `walk`:** `{"name", "title", "step", "count", "say", "look", "show", "trying": bool, "task", "done", "off_script"}`.
- **Routes:**
  - `GET /api/walks` answers `[{"name", "title", "see_also"}]` in `WALK_ORDER`.
  - `POST /api/walk {"name", "step"}` answers the picture; an unknown name is 404 and a bad step is 400.
  - `POST /api/walk/leave` clears `walk`.

**`WALK_ORDER`** = `("many-instructions", "where-n-lives", "subtracting-with-gates", "a-call-and-the-stack", "why-the-clock-ticks")`, with these ideas in this order, matching the spec:
1. A line of Pebble is many tiny instructions.
2. Where does `n` live? A box in memory.
3. How the computer subtracts, down to the gates.
4. What a function call does to the stack.
5. Why the clock ticks.

**Links.** Each walk's `see_also` page gets a "See it in the Cockpit" line linking `http://127.0.0.1:8765/#walk=<name>`. The page opens that walk when it loads with `#walk=<name>`.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pycpu/cockpit/session.py` | `Depth`, `step_at`, notes, loads mark nothing changed, walk progress, `go_to_walk` |
| `src/pycpu/cockpit/explain.py` (new) | `describe_move` and its templates |
| `src/pycpu/cockpit/walks.py` (new) | `Walk`, `WalkStep`, `WalkTry`, `WalkProgress`, `WalkError`, `load_walks`, `run_action`, `check_holds` |
| `src/pycpu/cockpit/walks/*.toml` (new) | The five walks |
| `src/pycpu/cpu.py` | `GateMachine.taps` (recorded at build; nothing computed) |
| `src/pycpu/cockpit/picture.py` | `steps`, `happened`, `walk`, `PART_NAMES`, `part_picture` |
| `src/pycpu/cockpit/app.py` | `/api/step` takes `{"depth"}`; `/api/part`, `/api/walks`, `/api/walk`, `/api/walk/leave` |
| `src/pycpu/cockpit/page.html` | Layout C, walks front door, Expert drawer |
| `tests/test_depths.py`, `tests/test_explain.py`, `tests/test_parts_view.py`, `tests/test_walks.py` (new), plus updates to `tests/test_cockpit.py` and `tests/test_docs.py` | Tests |

**New pages**, in "The Cockpit" nav section, which keeps its existing pages:

| Page | Task | Teaches |
|---|---|---|
| `concepts/the-magnifying-glass.md` | 2, grown in 4 | The four depths, the trail as a ladder, one Step that follows depth, part views from real wires |
| `concepts/what-just-happened.md` | 3 | How a sentence is written from the real change, at each depth |
| `concepts/guided-walks.md` | 5 | What a walk is, its file, replaying on the real machine, "Now you try" |

---

### Task 1: Carried tidy-ups and Pebble 0.4.1

**Files:** `pyproject.toml`, `uv.lock`, `tests/test_functions.py`, `tests/test_conformance.py`, `src/pycpu/cockpit/session.py`, `src/pycpu/cockpit/app.py`, `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`

- [ ] **Step 1: Pebble floor.**
  - Confirm `uv run --with fromscratch-pebble==0.4.1 python -c "import pebble"` works.
  - Raise the floor to `fromscratch-pebble>=0.4.1`, then `uv lock`.
  - Remove every `# Pebble v0.4.1:` workaround (grep the marker), keeping and enabling the tests they guarded, including the conditional final return in the conformance corpus and the random generator.
- [ ] **Step 2: Parked minors that touch code this plan rewrites.**
  - `_start_with` reads only the one example file it loads.
  - Fix `session.py`'s 101-column docstring line.
  - Rename the `/api/listing` handler back to `program_listing` by moving its pragma onto its own line.
- [ ] **Step 3: Roadmap.**
  - Rename "Notes for Plan 5" to say PyStack and the release are now Plan 6, and that Plan 5 is the Cockpit for learners (with the spec path).
  - Change "Left for Plan 5" in the definition-of-done table to "Left for Plan 6".
- [ ] **Step 4: Run** `uv run pytest`, then `uv run pytest -m slow --no-cov tests/test_conformance.py`. Expected: PASS, with the previously avoided shapes now in the corpus.
- [ ] **Step 5: Commit.** `git commit -m "chore: Pebble 0.4.1 floor and carried tidy-ups"`

---

### Task 2: Depths and the one Step button

**Files:**
- Create: `docs/concepts/the-magnifying-glass.md`, `tests/test_depths.py`
- Modify: `session.py`, `picture.py`, `app.py`, `mkdocs.yml`, `tests/test_docs.py`, `tests/test_cockpit_session.py` (the load rule)

**Interfaces:**
- Produces: `Depth`, `Cockpit.step_at(depth)`, `NO_LINES_NOTE`, `PART_NAMES`, the picture key `steps`, and `/api/step` accepting `{"depth": "line" | "instruction" | "part" | "gate"}` alongside the existing `size`. A body with both is 400; an unknown depth is 400.

- [ ] **Step 1: Doc first.** Write `the-magnifying-glass.md`.
  - **Analogy:** a magnifying glass over a map. Your finger stays on the town you are visiting (the program on the left), and the glass shows one street, one house or one brick. The trail of where you zoomed is how you get back up.
  - **Table:** the four depths, what the glass shows at each, and what Step does there.
  - **Try It:** at 8 address bits, load `countdown` through `TestClient`. Post one step at each depth, from the top down, and print each picture's `steps` label and `pc`. Then load assembly and print the note a line step gives.
  - **How It Works:** the mapping table, why a deeper step started mid-move finishes first, and that climbing never moves the machine (the trail is in the page).
  - Add it to the nav after A Tour of the Cockpit, with `KEY_IDEAS` `["depth", "magnifying glass", "step"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_depths.py`:
  - Each depth moves exactly as its mapped move does. Check this against a second Cockpit driven with the Plan 4 calls; the pictures must be equal.
  - LINE on assembly leaves the state equal and the note equal to `NO_LINES_NOTE`.
  - Every depth on a halted machine leaves the state equal, with `FINISHED_NOTE`.
  - Line depth after 5 gate steps finishes the instruction and stops on the next line (Review Focus).
  - `steps["part"]` reads "Step one ALU beat ▸" on a `sub`, and "Step one memory address beat ▸" on a `store`.
  - Every `PART_NAMES` key is a real scope, and every value in Plan 4's zoom table has a name.
  - After `load_pebble`, `changed` is empty everywhere (update the Plan 4 test that pinned the old rule).
  - The route accepts `depth` and refuses both keys or an unknown depth with 400. While playing, it answers 409 as before.
- [ ] **Step 3: Run** `uv run pytest tests/test_depths.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** as the contract says. Notes are set in `step_at` before the mapped move is called, so the mapped moves keep their Plan 4 behaviour.
- [ ] **Step 5: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: four depths and one Step that follows them"`

---

### Task 3: What just happened

**Files:**
- Create: `src/pycpu/cockpit/explain.py`, `docs/concepts/what-just-happened.md`, `tests/test_explain.py`
- Modify: `session.py` (store the sentence after each move), `picture.py` (`happened`), `mkdocs.yml`, `tests/test_docs.py`

**Interfaces:**
- Consumes: `Depth`, `step_at`.
- Produces: `describe_move(...) -> str` as the contract says, `Cockpit.happened: str | None` set by `step_at`, run and rewind, and cleared by loads, and the picture key `happened`.

- [ ] **Step 1: Doc first.** Write `what-just-happened.md`.
  - **Analogy:** a sports commentator who only says what really happened on the pitch, never what might have.
  - **Table:** depth → the shape of its sentence.
  - **Try It:** on `countdown`, step to `n = n - 1` at line depth. Step one instruction at a time through the line, printing `happened` each time. Then print one PART sentence and one GATE sentence.
  - **How It Works:** the sentence is built from `start` and `after`, with operand values read from the registers at the instruction's start and the result read after. Show the ALU template table in the file.
  - Add it to the nav after The Magnifying Glass, with `KEY_IDEAS` `["sentence", "what just happened", "real values"]`.
- [ ] **Step 2: Write failing tests** in `tests/test_explain.py`:
  - The exact `sub` sentence from the contract.
  - Every opcode and every ALU function gets a sentence, built from assembled one-instruction programs with known registers. Each sentence contains the real numbers and no `{` braces.
  - A Hypothesis property: for random register values and every ALU function, the number the sentence says went into `rd` equals the real `rd` afterwards.
  - LINE: the countdown's `n = n - 1` line gives `"Line 5 ran 3 instructions: load, subtract, store. n changed from 2 to 1."`. Read the instruction count from the run, and if it is not 3, pin the measured count instead and fix the doc.
  - Hidden variables (`$for_...`) never appear in a sentence.
  - PART fetch and execute sentences on a `sub`.
  - GATE: the gate that A Tour of the Cockpit reaches on `countdown` at 8 bits (gate 41226) gives "Gate 41226 in the XOR worked out a 1.". A clock edge gives the clock note.
  - A deeper step started mid-instruction describes the whole instruction (Review Focus).
  - `happened` is null after a load and set after every move.
- [ ] **Step 3: Run** `uv run pytest tests/test_explain.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement** `explain.py`, with templates in one table per opcode or ALU function. Read `isa.py`'s `AluOp` and `Instruction` fields; never decode a word by hand.
- [ ] **Step 5: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: say what just happened after every move"`

---

### Task 4: Part views from real wires

**Files:**
- Modify: `src/pycpu/cpu.py` (taps), `picture.py` (`part_picture`), `app.py` (`/api/part`), `docs/concepts/the-magnifying-glass.md` (a "Looking at a part" section)
- Test: `tests/test_parts_view.py`

**Interfaces:**
- Produces: `GateMachine.taps`, `part_picture(cockpit, path)`, and `GET /api/part?path=`.

- [ ] **Step 1: Doc first.** Add "Looking at a part" to `the-magnifying-glass.md`.
  - **Try It:** pause the countdown on its `sub`, step one beat into execute, and print `/api/part?path=cpu.alu`'s inputs and outputs (`a` 2, `b` 1, `result` 1).
  - Explain that the values come from the real wires, the same ones the gate view reads.
- [ ] **Step 2: Write failing tests:**
  - Every `PART_NAMES` part except `cpu` has a tap, and every tapped wire is a real wire of the circuit.
  - At an ALU execute, `result` equals the destination register after the instruction finishes. Check over a Hypothesis sample of ALU instructions with random register values.
  - Each value equals reading its bits one by one through `simulator.get`.
  - An unknown path gives 404, and the route while playing gives 409 with `BUSY_MESSAGE`.
  - No tap adds a gate or a wire: the circuit's gate count is unchanged (pin the count before and after).
- [ ] **Step 3: Run** `uv run pytest tests/test_parts_view.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement.** Record taps where `GateMachine` already holds each bus while it builds. Taps only name existing wires.
- [ ] **Step 5: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 6: Commit.** `git commit -m "feat: look at a CPU part's real inputs and outputs"`

---

### Task 5: Guided walks

**Files:**
- Create: `src/pycpu/cockpit/walks.py`, `src/pycpu/cockpit/walks/{many-instructions,where-n-lives,subtracting-with-gates,a-call-and-the-stack,why-the-clock-ticks}.toml`, `docs/concepts/guided-walks.md`, `tests/test_walks.py`
- Modify: `session.py`, `picture.py`, `app.py`, `pyproject.toml` (package data for `walks/*.toml`), `mkdocs.yml`, `tests/test_docs.py`

**Interfaces:**
- Consumes: `Depth`, `step_at`, `happened`, `PART_NAMES`, and the examples.
- Produces: everything under "Walks" in the contract.

- [ ] **Step 1: Doc first.** Write `guided-walks.md`.
  - **Analogy:** a museum audio guide. It tells you where to stand and what to look at, one sentence at a time, then lets you wander.
  - **Table:** walk file field → what it does.
  - **Try It:** list the walks, open `many-instructions`, go through every step printing `say`, then run its solution and print `done`.
  - **How It Works:** replay from `start` makes Back and "Back to the walk" exact; a fast-forward is a real run, not a jump; checks are latched.
  - Add it to the nav after What Just Happened, with `KEY_IDEAS` `["walk", "now you try", "replay"]`.
- [ ] **Step 2: Write the five walk files.**
  - Each walk is 4 to 8 steps of one sentence each, written for a 12-year-old, with one "Now you try".
  - `subtracting-with-gates` uses `step gate until cpu.alu` to reach the ALU's gates.
  - `a-call-and-the-stack` uses the `factorial` example, or an inline two-function program.
  - `why-the-clock-ticks` steps beats and gates around a clock edge, so the clock note appears.
- [ ] **Step 3: Write failing tests** in `tests/test_walks.py`:
  - All five load in `WALK_ORDER`.
  - For every walk, going to every step works, and the picture's `walk.say` equals the file's text.
  - For every walk, the check is false at the try stage before any move, and true after running `solution`.
  - Checks are latched: run the countdown's solution, then step on to the halt, and `done` stays true (Review Focus).
  - Bad files raise `WalkError` naming the file and the problem. Cover an unknown action, an unknown check, a missing `[try]` and a bad example name.
  - `go_to_walk` while playing stops play first. After the learner loads their own program, or mid-instruction, the walk's first picture equals a fresh walk's first picture (Review Focus).
  - Any non-walk move sets `off_script`, and `go_to_walk(name, step)` clears it.
  - The routes:
    - an unknown name is 404, with the message "There is no walk called <name>." (Review Focus);
    - a step out of range is 400;
    - leave clears `walk`.
  - Every walk's `see_also` page exists.
  - Every walk at full size (12 address bits) reaches its last step within 5 s. Mark this test slow.
- [ ] **Step 4: Run** `uv run pytest tests/test_walks.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 5: Implement** as the contract says. Parse actions and checks with small explicit grammars, `str.split` plus `match`, never `eval`.
- [ ] **Step 6: Run** `uv run pytest`, then `uv run pytest -m slow --no-cov tests/test_walks.py`. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "feat: guided walks that replay on the real machine"`

---

### Task 6: The page in layout C

**Files:**
- Modify: `src/pycpu/cockpit/page.html` (rewrite), `docs/concepts/the-cockpit.md` (rewrite the top half for layout C; keep the API reference half accurate), `tests/test_cockpit.py`

**Interfaces:**
- Consumes: every route and picture key above, plus Plan 4's.

- [ ] **Step 1: Doc first.** Rewrite the top of `the-cockpit.md`:
  - an ASCII drawing of layout C:
    - the top bar: Play/Pause, the one Step button, Rewind, the walk or example picker;
    - the "What just happened" line;
    - the left program pane: Pebble with the running line, that line's instructions under it, variables and output;
    - the right glass, with its trail;
    - the Expert drawer;
  - the walks screen it opens on;
  - what glows (only the newest change).

  Remove or rewrite every sentence about layout A, and keep every figure pinned.
- [ ] **Step 2: Write failing tests** (on the page text, as Plan 4 did):
  - The page has the ids the script uses:
    - `walks`, `walk-say`, `walk-next`, `walk-back`, `try-task`, `back-to-walk`;
    - `program`, `glass`, `trail`, `step`, `happened`;
    - `expert`, `play`, `pause`, `examples`, `source`.
  - The Step button's label is drawn from `steps[look]`, with no label literal in the script.
  - The page reads `#walk=` and calls `/api/walk`, and it falls back to the walks list with "Walk not found." when that call fails.
  - The layout CSS:
    - `height: 100vh` on the main grid;
    - `overflow: hidden` on body;
    - every pane has `overflow: auto`;
    - a `@media (max-width: 44rem)` block that puts `#glass` before `#program`.
  - Only `changed` from the latest picture is marked, and `drawChanged` runs once per picture.
  - No `innerHTML` and no external URL.
  - The Expert drawer holds the Plan 4 step sizes (Gate, Cycle, Instruction, Line, Line into, Run with its count).
  - "Pause to look inside the gates" sits inside `#glass`.
- [ ] **Step 3: Run** `uv run pytest tests/test_cockpit.py tests/test_docs.py -v`. Expected: FAIL.
- [ ] **Step 4: Implement the page.**
  - **Behaviour:**
    - On load, show the walks list unless `#walk=` names one.
    - Choosing a walk drives the glass from `walk.look` and `walk.show`.
    - Next calls `/api/walk` with `step + 1`, and Back with `step - 1`.
    - When `off_script`, show "Back to the walk".
    - At the try stage, show `task` and the Step button, and a cheer when `done`.
  - **The glass:**
    - Line depth: the Pebble line and its instructions, large.
    - Instruction depth: the instruction and its fields.
    - Part depth: `/api/part` inputs → part → outputs.
    - Gate depth: Plan 4's gate view.
    - Clicking inside the glass goes one depth down. Each trail crumb climbs back up.
  - **Kept from Plan 4:** the EventSource redraw, the request counter for views, refresh on refusal, and the "show this gate" behaviour (now in the glass).
- [ ] **Step 5: Browser check** with `uv run python -m pycpu` at 1280×720 and at 375 px, light and dark:
  - do every walk end to end, including its "Now you try";
  - leave a walk and come back;
  - press Step at all four depths;
  - climb the trail;
  - Play and Pause;
  - load your own Pebble;
  - open `#walk=nonsense`.

  Expect no page scrolling at 1280×720 and no console errors. If the implementer cannot launch a browser, write "Browser check owed to controller" and list each item; the controller hands it to the owner.
- [ ] **Step 6: Run** `uv run pytest`. Expected: PASS.
- [ ] **Step 7: Commit.** `git commit -m "feat: the Cockpit in layout C, opening on guided walks"`

---

### Task 7: Links, the story and the hand-off to Plan 6

**Files:** the five `see_also` concept pages, `docs/concepts/a-tour-of-the-cockpit.md` and `stepping-a-pebble-line.md` (button names and layout words), `docs/index.md`, `docs/from-scratch.md`, `README.md`, `examples/cockpit_tour.py` (if it names removed buttons), the roadmap, and `tests/test_docs.py`

- [ ] **Step 1: "See it in the Cockpit."**
  - Each `see_also` page gets one line linking `http://127.0.0.1:8765/#walk=<name>`, with a sentence saying to start the Cockpit first with `uv run python -m pycpu`.
  - Add a test: every walk's `see_also` page holds exactly that link.
- [ ] **Step 2: Story.**
  - `index.md`, `from-scratch.md` and the README say the Cockpit opens on guided walks.
  - Every page that describes layout A or the five step buttons as the main controls is updated.
  - Grep for "layout A", "zoom panel" and "Line into", and fix each hit, or keep it where it is only about the Expert drawer.
  - The README Concepts table gets the three new pages.
- [ ] **Step 3: Notes for Plan 6** in the roadmap:
  - the definition-of-done table again, with only PyStack's launcher and `import "cpu"` left;
  - measured timings: each walk's replay at full size, and `/api/part`;
  - the minors parked in this plan's ledger;
  - the owner's go-ahead, which is still needed before anything is exposed.
- [ ] **Step 4: Final verification.**
  - `uv run pytest && uv run pytest -m slow --no-cov && uv run pytest --hypothesis-profile=thorough --no-cov tests/test_explain.py tests/test_parts_view.py`
  - `uv run ruff check . && uv run ruff format --check . && uv run pyright src tests examples && uv run mkdocs build --strict`

  Expected: all pass.
- [ ] **Step 5: Commit.** `git commit -m "docs: link the concept pages to their walks"`. The controller pushes, opens the PR, and merges it once CI is green and the owner's browser check passes. Create no tag.
