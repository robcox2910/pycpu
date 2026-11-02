# PyCPU Plan 1: Gates to Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the repo, the real gate-level simulator, and every layer up to 4K-word RAM, and prove that RAM is workable in Python.

**Architecture:** A `Circuit` stores NAND gates as compact arrays (a netlist) with named hierarchical scopes, so the UI can draw exactly what runs. A `Simulator` evaluates it event by event, so cost follows activity rather than circuit size. All logic, arithmetic and memory are Python functions that wire NANDs together; none compute results directly.

**Tech Stack:** Python 3.14, uv, hatchling + hatch-vcs, pytest, Hypothesis, ruff, strict pyright, PyWeb v0.3.1 (Bench page), standard library `array`.

**Spec:** `docs/superpowers/specs/2026-11-01-pycpu-design.md`. Roadmap: `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`.

## Global Constraints

- NAND is the single primitive. Nothing above `simulator.py` may compute a logic result in Python except test helpers and `peek`/`poke`.
- The gate view must show the real circuit's real values. Never fake it.
- RAM is 4K words of 16 bits, every bit real gates. If the proof fails, shrink the RAM; never add a behavioural store.
- 16-bit words. Buses are tuples of wires, least significant bit first.
- Never use `TYPE_CHECKING` or `from __future__ import annotations`.
- Documentation is as important as code, and ranks above every other rule here. See the Documentation Standard below. A task with weak docs is not done, however good its code is.
- `src` layout, line length 100, ruff rules and strict pyright copied from `pyweb/pyproject.toml`; sibling pins are git tags, never `path`.
- Do not create any version tag. First release is Plan 5.
- Do not publish yet: no GitHub Pages, no entry in `series.yml`, no `series sync` until Plan 5. `mkdocs build --strict` must pass from Task 1 onward.
- Conventional commits; all changes after the initial scaffold go by PR into protected `main`.

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

**Honesty rule for docs:** the numbers in docs are measured, never invented. Output in `## Try It` is checked by running it.

## Review Focus

- A circuit with a feedback loop that never settles (a NOT gate fed its own output): expect `OscillationError` naming the scope, never a hang. Test in Task 2.
- Power-on: expect the same state on every build and run, so a replay or rewind in Plan 2 cannot diverge. Test in Task 6.
- ALU at the edges (`0xFFFF + 1`, `0x7FFF + 1`, `0x8000 - 1`): expect exact wrap and correct carry and overflow, because Pebble's signed comparisons depend on them. Test in Task 5.
- RAM boundaries and neighbours: addresses 0 and the last address work, and a write never disturbs any other word. Test in Task 7.
- Bench asked for a scope that does not exist: expect a 404 with a friendly message, not a server error. Test in Task 9.

---

## File Structure

| File | Responsibility |
|---|---|
| `src/pycpu/circuit.py` | `Circuit`, `Wire`, `Bus`, scopes, state-bit registry; the netlist |
| `src/pycpu/simulator.py` | `Simulator`, `OscillationError`, `tick` |
| `src/pycpu/logic.py` | Gates and buses built from NAND |
| `src/pycpu/arithmetic.py` | Adders, `AluOp`, `alu` |
| `src/pycpu/memory.py` | Latch, flip-flop, `Register`, `Ram`, RAM size constants |
| `src/pycpu/view.py` | `circuit_view`: what one scope looks like right now |
| `src/pycpu/bench/app.py` | PyWeb Bench page and its API |
| `scripts/prove_ram.py` | The 4K proof, printing measurements |
| `tests/test_<module>.py`, `tests/test_smoke.py` | Tests |
| `tests/test_docs.py`, `tests/test_docstrings.py` | Docs guards: required sections, nav, runnable examples, docstrings |
| `mkdocs.yml`, `docs/index.md`, `docs/from-scratch.md` | The site and the whole story |
| `docs/concepts/*.md` | One page per idea, in climbing order (below) |

**Pages in reading order, and the task that writes each:**

| Page | Task | Teaches |
|---|---|---|
| `index.md` | 1 | What this project is, the ladder of layers, how to read it |
| `from-scratch.md` | 1 | Why build a computer from nothing; credit to Petzold's *Code*; how PyCPU sits under the rest of the series |
| `concepts/bits-and-binary.md` | 2 | On and off, bits, counting in binary, hex |
| `concepts/switches-and-nand.md` | 2 | Why NAND is the one brick, and what a wire and gate are |
| `concepts/simulating-a-circuit.md` | 2 | How Python pretends to be electricity; events; "settling"; oscillation |
| `concepts/gates.md` | 3 | NOT, AND, OR, XOR, each built from NAND, with truth tables |
| `concepts/choosing-and-decoding.md` | 3 | Mux and decoder: the railway points of a computer |
| `concepts/looking-inside.md` | 4 | Named parts, and how the zoom shows the real circuit |
| `concepts/adding.md` | 5 | Half adder, full adder, ripple carry |
| `concepts/negative-numbers.md` | 5 | Two's complement, subtraction, overflow |
| `concepts/the-alu.md` | 5 | One machine for every sum, and its flags |
| `concepts/remembering.md` | 6 | Feedback: how a loop of gates can remember |
| `concepts/the-clock.md` | 6 | The drumbeat, flip-flops, and why there are two clock wires |
| `concepts/registers.md` | 6 | A row of flip-flops; building a counter |
| `concepts/ram.md` | 7 | Addresses, word lines, reading and writing |
| `concepts/how-big-is-our-memory.md` | 8 | The proof, with real measured numbers, and why memory is hard to simulate |
| `concepts/the-bench.md` | 9 | Using the Bench to see all of this working |

---

### Task 1: Scaffold the repository

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.pre-commit-config.yaml`, `CLAUDE.md`, `README.md`, `LICENSE`, `.github/workflows/ci.yml`, `.github/workflows/docs.yml`, `mkdocs.yml`, `docs/index.md`, `docs/from-scratch.md`, `src/pycpu/__init__.py`, `src/pycpu/py.typed`, `tests/test_smoke.py`, `tests/test_dependency_pins.py`, `tests/test_docs.py`, `tests/test_docstrings.py`, `uv.lock`

**Interfaces:**
- Produces: importable `pycpu` package, green CI, a site that builds strictly, and doc guards every later task relies on:
  - `tests/test_docs.py` has `KEY_IDEAS: dict[str, list[str]]`, mapping a page path to words it must contain. Later tasks add a line per page.

The series runbook says to start a repo as a copy of an existing project (`robcox2910.github.io/README.md`, "Add a project"). Copy from `/Users/robcox/development/python/pyweb`, the nearest current example.

- [ ] **Step 1: Create the repo.** `git init` in `/Users/robcox/development/python/pycpu` on `main`; commit the existing `docs/` first.

- [ ] **Step 2: Copy the series standard from `pyweb`:** `.gitignore`, `.pre-commit-config.yaml`, `LICENSE`, `.github/workflows/ci.yml` (it calls the shared `python-ci.yml@v1`), and `CLAUDE.md`, keeping its `standard` marked block and replacing its project notes with ones for PyCPU.

- [ ] **Step 3: Copy `.github/workflows/docs.yml`, changing only its trigger** to `workflow_dispatch` alone, so nothing deploys until Plan 5. Add a comment saying so; `series sync` restores the standard file then.

- [ ] **Step 4: Write `pyproject.toml`** adapted from `pyweb/pyproject.toml`: name `pycpu`, description "An educational computer simulated from NAND gates in Python", `requires-python >=3.14`, dependencies `["pyweb"]`, dev extras as pyweb plus `hypothesis>=6.100`, docs extra `mkdocs-material>=9.5`, source `pyweb = { git = "https://github.com/robcox2910/pyweb", tag = "v0.3.1" }`. Pytest addopts: `-m "not slow" --cov=src/pycpu --cov-report=term-missing --cov-fail-under=90`, marker `slow`, default `timeout = 60`. Add `"scripts/*.py" = ["T201"]` to per-file ignores. Omit `src/pycpu/_version.py` from coverage and ruff.

- [ ] **Step 5: Write `mkdocs.yml`** from `pyweb/mkdocs.yml`: set `site_name: PyCPU`, `site_url`, `repo_url`, `repo_name`, keep the `theme` block and `exclude_docs: superpowers/`, and drop the `series-nav` block for now (the sync adds it). Nav: Home, From Scratch, then a section per climbing stage, listing pages in the order of the table above.

- [ ] **Step 6: Write the doc guards first** in `tests/test_docs.py`, using `pathlib`, `re`, `yaml`-free text matching on `mkdocs.yml`:
  - `test_every_concept_page_has_every_required_section`, parametrised over `docs/concepts/*.md`: contains `## Try It`, `## How It Works`, `## Why Does This Matter?`, `## What's Next`, in that order, and a Markdown table before `## Try It`.
  - `test_every_page_is_in_the_nav`: each page's path appears in `mkdocs.yml`.
  - `test_try_it_examples_run`, parametrised over concept pages: extract each ```` ```python ```` block under `## Try It`, `exec` it in a fresh namespace, capture stdout, and when a block has `# Output:` comment lines, assert the output matches them exactly.
  - `test_key_ideas_appear`, parametrised over `KEY_IDEAS`, case-insensitive.
  - `test_site_builds_strictly`: runs `mkdocs build --strict -d <tmp_path>` via `subprocess`, expects exit 0.

  In `tests/test_docstrings.py`: `test_every_public_name_has_a_docstring`, walking `src/pycpu/**/*.py` with `ast` to assert modules, public classes and public functions all have docstrings; and `test_every_module_docstring_has_a_body`, asserting module docstrings are at least 3 lines long, so a one-line label cannot pass.

- [ ] **Step 7: Write `docs/index.md`.** Title "What Is a Computer, Really?". Follow the sibling style: an opening analogy (a giant machine made of nothing but tiny switches, built like Lego), a picture of the ladder of layers from NAND to Pebble, what the learner will be able to do by the end, the Cockpit as the destination, and a "start here" link. Mark stages that do not exist yet as "coming later in the climb". Make no claim the code cannot yet back up.

- [ ] **Step 8: Write `docs/from-scratch.md`.** Title "Why Build a Computer From Nothing?". Cover: what "from scratch" means here (no hidden magic; every layer made only from the one below); the single rule that everything is made of NAND; why simulate instead of solder; credit to Charles Petzold's *Code* as the inspiration; the "no faking" promise and what it means; where PyCPU sits in the series (beneath Pebble, PyOS and the rest, with links); how to read the docs and try things. Add both pages to `KEY_IDEAS`: `index.md: ["nand", "pebble", "cockpit"]`, `from-scratch.md: ["petzold", "nand", "faking", "pebble"]`.

- [ ] **Step 9: Write `README.md`:** what PyCPU is, in kid-friendly words, the ladder, quick start, and a link to `docs/`.

- [ ] **Step 10: Write remaining tests.** `test_smoke.py` imports `pycpu`; `test_dependency_pins.py` asserts no `path` key under `[tool.uv.sources]`, using `tomllib`. Give `src/pycpu/__init__.py` a module docstring that introduces the project with an analogy.

- [ ] **Step 11: Verify.** Run `uv sync --all-extras && uv run pytest && uv run ruff check . && uv run pyright src tests`. Expected: all pass. If coverage blocks an empty package, confirm the module docstring import counts before relaxing anything.

- [ ] **Step 12: Commit, then publish the repo.**

```bash
git add -A && git commit -m "chore: scaffold pycpu"
gh repo create robcox2910/pycpu --public --source . --push
```

Then protect `main`, matching a sibling's settings (`gh api repos/robcox2910/pyllm/branches/main/protection`). All later tasks use feature branches.

---

### Task 2: Netlist and event-driven simulator

**Files:**
- Create: `src/pycpu/circuit.py`, `src/pycpu/simulator.py`, `docs/concepts/bits-and-binary.md`, `docs/concepts/switches-and-nand.md`, `docs/concepts/simulating-a-circuit.md`
- Modify: `tests/test_docs.py`, `mkdocs.yml`
- Test: `tests/test_simulator.py`

**Docs first.** Write the three pages before Step 1. Analogies: a light switch and counting on fingers (`bits-and-binary`, ideas `bit`, `binary`, `hex`); two switches in a row controlling a lamp that goes off only when both are pressed (`switches-and-nand`, ideas `nand`, `wire`, `gate`, `truth table`); dominoes falling only where something changed, with a ring of dominoes that never stops for oscillation (`simulating-a-circuit`, ideas `event`, `settle`, `oscillat`, `netlist`). Add all three to `KEY_IDEAS`.

**Interfaces:**
- Produces:
  - `type Wire = int`; `type Bus = tuple[Wire, ...]`
  - `Circuit()` with constants `.low: Wire`, `.high: Wire`; `.input(name: str) -> Wire`; `.bus_input(name: str, width: int) -> Bus`; `.nand(a: Wire, b: Wire) -> Wire`; `.gate_count: int`; `.wire_count: int`
  - `Circuit.wire_placeholder() -> Wire` and `.nand_into(a: Wire, b: Wire, out: Wire) -> None`, for feedback loops
  - `Simulator(circuit: Circuit, max_events: int = 10_000_000)`; `.set(wire: Wire, value: int) -> None`; `.get(wire: Wire) -> int`; `.set_bus(bus: Bus, value: int) -> None`; `.get_bus(bus: Bus) -> int`; `.settle() -> int` returning gate evaluations; `.events_total: int`
  - `OscillationError(Exception)`

Storage: `array("i")` for gate inputs and outputs, `bytearray` for wire values. Build fanout as a compressed array when the `Simulator` is constructed, not a list per wire, because Task 8 has around half a million gates.

**Evaluation rule (the tests do not fully determine this, and it matters):** use a FIFO queue of gate indices with an in-queue flag. Pop a gate, compute NAND from current wire values, and if its output changes, write it immediately and enqueue its fanout. Immediate writes break the symmetry of a NAND latch, which would oscillate forever under simultaneous update. The constructor enqueues all gates in index order and settles, so power-on is deterministic.

- [ ] **Step 1: Write failing tests**

```python
def test_nand_truth_table():
    c = Circuit()
    a, b = c.input("a"), c.input("b")
    out = c.nand(a, b)
    sim = Simulator(c)
    for x, y, want in [(0, 0, 1), (0, 1, 1), (1, 0, 1), (1, 1, 0)]:
        sim.set(a, x); sim.set(b, y); sim.settle()
        assert sim.get(out) == want

def test_unchanged_input_costs_no_evaluations():
    c = Circuit(); a = c.input("a"); c.nand(a, a)
    sim = Simulator(c); sim.settle()
    sim.set(a, 0)
    assert sim.settle() == 0

def test_only_affected_gates_are_evaluated():
    c = Circuit(); a, b = c.input("a"), c.input("b")
    c.nand(a, a)
    for _ in range(1000):
        c.nand(b, b)
    sim = Simulator(c); sim.settle()
    sim.set(a, 1)
    assert sim.settle() == 1

def test_set_bus_round_trips_least_significant_bit_first():
    c = Circuit(); bus = c.bus_input("x", 16)
    sim = Simulator(c); sim.set_bus(bus, 0xBEEF)
    assert sim.get_bus(bus) == 0xBEEF and sim.get(bus[0]) == 1

def test_never_settling_loop_raises_oscillation_error():
    c = Circuit(); x = c.wire_placeholder(); c.nand_into(x, x, x)
    with pytest.raises(OscillationError):
        Simulator(c, max_events=1000)

def test_constant_wires():
    c = Circuit(); sim = Simulator(c)
    assert (sim.get(c.low), sim.get(c.high)) == (0, 1)
```

- [ ] **Step 2: Run** `uv run pytest tests/test_simulator.py -v`. Expected: FAIL, modules missing.

- [ ] **Step 3: Implement** `circuit.py` and `simulator.py` to the interfaces and evaluation rule above. `set` on a non-input wire raises `ValueError`.

- [ ] **Step 4: Run** the same command. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat: add netlist and event-driven simulator"`

---

### Task 3: Logic gates from NAND

**Files:**
- Create: `src/pycpu/logic.py`, `docs/concepts/gates.md`, `docs/concepts/choosing-and-decoding.md`
- Modify: `tests/test_docs.py`, `mkdocs.yml`
- Test: `tests/test_logic.py`

**Docs first.** Write both pages before Step 1. `gates.md` builds each gate from NAND with a wiring diagram and truth table (analogy: light switches wired so one lamp answers a yes-or-no question; ideas `nand`, `truth table`, `xor`). `choosing-and-decoding.md` covers mux and decoder (analogy: railway points, and a hotel receptionist's panel with one button per room; ideas `mux`, `decoder`). Add both to `KEY_IDEAS`.

**Interfaces:**
- Consumes: `Circuit`, `Wire`, `Bus`, `Simulator`.
- Produces: `not_(c, a)`, `and_(c, a, b)`, `or_(c, a, b)`, `xor(c, a, b)`, `mux(c, select, when_0, when_1)` each returning `Wire`; `not_bus(c, a)`, `and_bus`, `or_bus`, `xor_bus`, `mux_bus(c, select, when_0, when_1)` each returning `Bus`; `or_many(c, wires: Sequence[Wire]) -> Wire`; `is_zero(c, a: Bus) -> Wire`; `decoder(c, select: Bus) -> Bus` (one output high per value of `select`, width `2 ** len(select)`).

- [ ] **Step 1: Write failing tests.** Parametrised truth tables for all five single-bit gates. Hypothesis over 16-bit ints for each bus function against the Python equivalent. `decoder` for a 3-bit select has exactly the selected line high. `or_many` over 0, 1 and 7 wires (0 wires gives `c.low`). Add:

```python
def test_bus_width_mismatch_is_rejected():
    c = Circuit()
    with pytest.raises(ValueError, match="width"):
        and_bus(c, c.bus_input("a", 16), c.bus_input("b", 8))

def test_gates_are_built_only_from_nand():
    c = Circuit(); xor(c, c.input("a"), c.input("b"))
    assert c.gate_count == 4
```

- [ ] **Step 2: Run** `uv run pytest tests/test_logic.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement** `logic.py` using only `c.nand`. `xor` uses the classic 4-NAND form. `or_many` builds a balanced tree, so one changed input travels only `log n` gates.

- [ ] **Step 4: Run** `uv run pytest tests/test_logic.py tests/test_docs.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat: add logic gates built from NAND"`

---

### Task 4: Named scopes and the circuit view

**Files:**
- Modify: `src/pycpu/circuit.py`, `src/pycpu/logic.py`, `tests/test_docs.py`, `mkdocs.yml`
- Create: `src/pycpu/view.py`, `docs/concepts/looking-inside.md`
- Test: `tests/test_view.py`

**Docs first.** Write `looking-inside.md` before Step 1 (analogy: a street map that lets you zoom from country to town to house; ideas `scope`, `zoom`, `real`, `faking`). It must explain why the view reads the same values the simulator is using, and so cannot lie. Add it to `KEY_IDEAS`.

**Interfaces:**
- Consumes: `Circuit`, `Simulator`, `logic`.
- Produces:
  - `Circuit.scope(name: str) -> ContextManager[None]`: gates and child scopes created inside belong to it; paths are dotted, e.g. `"alu.adder.bit1"`.
  - `Circuit.children(path: str) -> list[str]`; `Circuit.gates_in(path: str) -> list[int]` (direct gates only); `Circuit.has_scope(path: str) -> bool`. `""` is the root.
  - `view.circuit_view(sim: Simulator, path: str) -> dict[str, object]` with keys `path`, `children` (list of `{"name", "gate_count"}`), `gates` (list of `{"id", "a", "b", "out", "value_a", "value_b", "value_out"}`). Raises `KeyError` for an unknown path.

Store scope as an `array("i")` of scope IDs per gate plus a table of scope paths, so 500,000 gates add only 4 bytes each. Decorate every function in `logic.py` so its gates live in a child scope named after it, numbered when repeated under one parent (`xor`, `xor#1`). Task 3's gate counts must not change.

- [ ] **Step 1: Write failing tests**

```python
def test_gates_land_in_their_scope():
    c = Circuit(); a, b = c.input("a"), c.input("b")
    with c.scope("half"):
        xor(c, a, b)
    assert c.children("") == ["half"]
    assert c.children("half") == ["xor"]
    assert len(c.gates_in("half.xor")) == 4

def test_view_reports_real_live_values():
    c = Circuit(); a, b = c.input("a"), c.input("b")
    with c.scope("one"):
        out = c.nand(a, b)
    sim = Simulator(c); sim.set(a, 1); sim.set(b, 1); sim.settle()
    gate = circuit_view(sim, "one")["gates"][0]
    assert (gate["value_a"], gate["value_b"], gate["value_out"]) == (1, 1, 0)
    assert gate["out"] == out

def test_unknown_scope_raises_key_error():
    with pytest.raises(KeyError):
        circuit_view(Simulator(Circuit()), "nope")
```

- [ ] **Step 2: Run** `uv run pytest tests/test_view.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement** scopes, the `logic.py` decorator and `view.py`.

- [ ] **Step 4: Run** `uv run pytest tests/test_view.py tests/test_logic.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat: add named scopes and live circuit view"`

---

### Task 5: Adders and the ALU

**Files:**
- Create: `src/pycpu/arithmetic.py`, `docs/concepts/adding.md`, `docs/concepts/negative-numbers.md`, `docs/concepts/the-alu.md`
- Modify: `tests/test_docs.py`, `mkdocs.yml`
- Test: `tests/test_arithmetic.py`

**Docs first.** Write all three pages before Step 1. `adding.md` (analogy: column addition and carrying the one; ideas `half adder`, `full adder`, `carry`, `ripple`). `negative-numbers.md` (analogy: a car's mileage counter rolling backwards past zero; ideas `two's complement`, `overflow`, `wrap`, and that adding is enough to subtract). `the-alu.md` (analogy: a kitchen multi-tool with a dial; ideas `alu`, `flag`, `zero`, `carry`, `overflow`). Add all three to `KEY_IDEAS`.

**Interfaces:**
- Consumes: `logic`, `Circuit.scope`.
- Produces:
  - `half_adder(c, a, b) -> tuple[Wire, Wire]` (sum, carry); `full_adder(c, a, b, carry_in) -> tuple[Wire, Wire]`
  - `ripple_adder(c, a: Bus, b: Bus, carry_in: Wire) -> tuple[Bus, Wire]`, with bits in scopes `bit0`, `bit1`, ...
  - `class AluOp(IntEnum)`: `ADD=0, SUB=1, AND=2, OR=3, XOR=4, SHL=5, SHR=6, PASS_B=7`
  - `@dataclass(frozen=True) class AluOutput`: `result: Bus; zero: Wire; negative: Wire; carry: Wire; overflow: Wire`
  - `alu(c, a: Bus, b: Bus, op: Bus) -> AluOutput` with `op` 3 bits wide, built in scope `alu` with the adder in `alu.adder`.

Semantics: `SUB` is `a + NOT b + 1`, so `carry` is 1 when no borrow occurred. `SHL`/`SHR` shift `a` by one, shifting in 0, with the bit shifted out in `carry`. `AND/OR/XOR/PASS_B` give `carry=0`, `overflow=0`. `overflow` is meaningful only for `ADD` and `SUB` and means the signed result does not fit. `SHR` is logical.

- [ ] **Step 1: Write failing tests.** Hypothesis over `(a, b)` 16-bit and every `AluOp`, against a plain Python model in the test file checking result and all four flags. Pinned cases:

```python
@pytest.mark.parametrize(("op", "a", "b", "result", "carry", "overflow"), [
    (AluOp.ADD, 0xFFFF, 1, 0x0000, 1, 0),
    (AluOp.ADD, 0x7FFF, 1, 0x8000, 0, 1),
    (AluOp.SUB, 0x8000, 1, 0x7FFF, 1, 1),
    (AluOp.SUB, 0, 1, 0xFFFF, 0, 0),
    (AluOp.SHL, 0x8000, 0, 0x0000, 1, 0),
    (AluOp.SHR, 0x0001, 0, 0x0000, 1, 0),
])
def test_alu_edge_cases(op, a, b, result, carry, overflow): ...
```

Also assert `zero` for `SUB a a`, and that `c.children("alu.adder")` contains `bit0` to `bit15`.

- [ ] **Step 2: Run** `uv run pytest tests/test_arithmetic.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement** `arithmetic.py`. Select the operation result with a mux tree on the three `op` bits, and feed the adder `b` or `NOT b` from `op`, so only one adder exists.

- [ ] **Step 4: Run** `uv run pytest tests/test_arithmetic.py tests/test_docs.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat: add adders and ALU"`

---

### Task 6: Clock, flip-flop and register

**Files:**
- Create: `src/pycpu/memory.py`, `docs/concepts/remembering.md`, `docs/concepts/the-clock.md`, `docs/concepts/registers.md`
- Modify: `src/pycpu/circuit.py`, `src/pycpu/simulator.py`, `tests/test_docs.py`, `mkdocs.yml`
- Test: `tests/test_memory.py`

**Docs first.** Write all three pages before Step 1. `remembering.md` (analogy: two friends each repeating to the other what they heard, so the message stays alive with nobody holding it; ideas `feedback`, `latch`, `remember`). `the-clock.md` (analogy: a rowing crew's drummer, and a two-beat "everyone write, then everyone step" routine; ideas `clock`, `flip-flop`, `rising edge`, and why there are two clock wires). `registers.md` (analogy: a row of labelled sticky notes, and a tally counter; ideas `register`, `load`, `counter`). Add all three to `KEY_IDEAS`.

**Interfaces:**
- Consumes: `Circuit.wire_placeholder`, `nand_into`, `logic`.
- Produces:
  - `@dataclass(frozen=True) class Clock`: `clk: Wire; write: Wire`, and `make_clock(c: Circuit) -> Clock`
  - `Simulator.tick(clock: Clock) -> None`: pulse `write` up then down, settling each time, then pulse `clk` up then down, settling each time.
  - `Circuit.state_pair(name: str, q: Wire, qn: Wire) -> None`, registering a storage cell for fast loading.
  - `Simulator.poke_pairs(pairs: Sequence[tuple[Wire, Wire]], value: int) -> None`: writes `q=value`, `qn=1-value` and enqueues their fanout, without settling.
  - `d_latch(c, data: Wire, enable: Wire) -> tuple[Wire, Wire]` (q, qn)
  - `d_flip_flop(c, data: Wire, clk: Wire) -> Wire`: rising-edge, master-slave
  - `class Register`, built by `Register(c, width: int, data: Bus, load: Wire, clock: Clock, name: str)`, with `.q: Bus`, `.peek(sim) -> int`, `.poke(sim, value: int) -> None`.

**Why two clock wires (a decision the implementer cannot infer):** Registers change on `clk`; RAM writes on the `write` pulse. `write` always pulses first, while all registers still hold this cycle's address and data, and is low again before `clk` rises. A single clock would race, because the address can change while a RAM cell is still open. Early computers used two-phase clocks for the same reason.

- [ ] **Step 1: Write failing tests.** Include:

```python
def test_latch_follows_while_enabled_then_holds(): ...
def test_flip_flop_changes_only_on_rising_edge(): ...

def test_register_holds_without_load_and_loads_with_it():
    # poke 0x1234; tick with load=0 keeps it; tick with load=1, data=0xBEEF gives 0xBEEF
    ...

def test_poke_survives_many_ticks():
    # poke 0xCAFE, tick 10 times with load=0, peek == 0xCAFE
    ...

def test_a_counter_built_from_register_and_adder_counts():
    # Register fed by ripple_adder(q, 1): 300 ticks wraps correctly mod 2**width for width 8
    ...

def test_power_on_state_is_identical_across_builds():
    def build():
        c = Circuit(); clock = make_clock(c); data = c.bus_input("d", 16)
        reg = Register(c, 16, data, c.input("load"), clock, "r")
        return Simulator(c), reg
    (one, reg_one), (two, reg_two) = build(), build()
    assert reg_one.peek(one) == reg_two.peek(two)
```

The last test may pass on first run. Keep it as a regression guard.

- [ ] **Step 2: Run** `uv run pytest tests/test_memory.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement** `make_clock`, `tick`, `state_pair`, `poke_pairs`, `d_latch` (4 NANDs in an enable-plus-cross-coupled form), `d_flip_flop` (two `d_latch`es on inverted and true `clk`) and `Register` (each bit is a flip-flop behind a `mux(load, q, d)`). `Register.poke` pokes both master and slave pairs of every bit, then settles.

- [ ] **Step 4: Run** `uv run pytest tests/test_memory.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat: add two-phase clock, flip-flop and register"`

---

### Task 7: RAM

**Files:**
- Modify: `src/pycpu/memory.py`, `tests/test_docs.py`, `mkdocs.yml`
- Create: `docs/concepts/ram.md`
- Test: `tests/test_ram.py`

**Docs first.** Write `ram.md` before Step 1 (analogy: a wall of numbered lockers, with a corridor light for each row and a light for each column, so one locker lights up where they cross; ideas `address`, `word line`, `read`, `write`). Add it to `KEY_IDEAS`.

**Interfaces:**
- Consumes: `d_latch`, `decoder`, `or_many`, `Clock`, `state_pair`.
- Produces:
  - Constants `RAM_ADDRESS_BITS = 12`, `RAM_WORDS = 1 << RAM_ADDRESS_BITS`, `WORD_BITS = 16`
  - `class Ram`, built by `Ram(c, address: Bus, data: Bus, write_enable: Wire, clock: Clock, name: str = "ram")`, with `.out: Bus`, `.peek(sim, address: int) -> int`, `.poke(sim, address: int, value: int) -> None`, `.load(sim, words: Sequence[int]) -> None`. Size comes from `len(address)`, so tests can use small RAMs.

**Circuit shape (it decides whether Task 8 can pass):** split the address into high and low halves, decode each, and form each word line with an `and_` of one row and one column line. A cell latches when `word_line AND write_pulse`, where `write_pulse` is `write_enable AND clock.write`. Each output bit is `or_many` over `nand`-gated `word_line AND q` for that bit. Do not use a binary mux tree: a low address bit would then fan out to thousands of gates, and each read would cost tens of thousands of evaluations. With word lines an address change disturbs about 2 × 16 cell gates plus their `log n` paths.

Scopes: `ram.word<N>.bit<M>`. Put row/column decoders in `ram.decoder`. `Ram.load` pokes all pairs then settles once.

- [ ] **Step 1: Write failing tests** with a 4-bit address (16 words) unless stated:

```python
def test_write_then_read_back(): ...
def test_write_enable_low_changes_nothing(): ...

@given(writes=st.lists(st.tuples(st.integers(0, 15), st.integers(0, 0xFFFF)), max_size=20))
def test_ram_behaves_like_a_list(writes):
    # After each write through gates (not poke), every one of the 16 addresses reads
    # the same as a plain Python list given the same writes.
    ...

def test_first_and_last_address(): ...      # 0 and 15, 8-bit address also 0 and 255
def test_poked_words_read_back_through_the_gates(): ...
def test_changing_address_touches_few_gates():
    # 8-bit address: after settling, changing the address costs under 300 evaluations.
    ...
```

Use `@settings(max_examples=25)` so the property test fits the 60-second timeout, and build one circuit per module via a helper, resetting with `load`.

- [ ] **Step 2: Run** `uv run pytest tests/test_ram.py -v`. Expected: FAIL.

- [ ] **Step 3: Implement** `Ram` to the shape above.

- [ ] **Step 4: Run** `uv run pytest tests/test_ram.py tests/test_docs.py -v`. Expected: PASS.

- [ ] **Step 5: Commit.** `git commit -m "feat: add word-line RAM built from gates"`

---

### Task 8: Prove 4K words works

This is the spec's gate. Plans 2 onward depend on its result.

**Files:**
- Create: `scripts/prove_ram.py`, `tests/test_ram_proof.py`
- Create: `docs/concepts/how-big-is-our-memory.md`
- Modify: `tests/test_docs.py`, `mkdocs.yml`, `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`, possibly `src/pycpu/memory.py`

**Interfaces:**
- Consumes: `Ram`, `Simulator`, `RAM_ADDRESS_BITS`, `RAM_WORDS`.
- Produces: `prove_ram.measure(address_bits: int) -> dict[str, float]` with keys `gates`, `build_seconds`, `memory_mib`, `load_seconds`, `read_seconds`, `write_seconds`. A confirmed `RAM_ADDRESS_BITS`.

Thresholds, for a 16-bit CPU that later adds its own gates. Build may later be run once per Bench start. Load is the pause cost. An instruction performs about three memory accesses, so the read and write limits keep a gate-stepped replay interactive.

| Measure | Limit |
|---|---|
| `build_seconds` (circuit + simulator) | under 30 |
| `memory_mib` (peak via `resource.getrusage`) | under 1024 |
| `load_seconds` (all words poked, settled) | under 5 |
| `read_seconds`, `write_seconds` (median of 100 random) | under 0.1 |

- [ ] **Step 1: Write the slow test** in `tests/test_ram_proof.py`: marked `@pytest.mark.slow` and `@pytest.mark.timeout(600)`, it loads scripts via `importlib`, calls `measure(RAM_ADDRESS_BITS)`, and asserts all four limits. A fast, unmarked test calls `measure(6)` and asserts every key is present and positive.

- [ ] **Step 2: Implement `scripts/prove_ram.py`** printing a table, with `main()` taking an optional `--address-bits`.

- [ ] **Step 3: Run** `uv run python scripts/prove_ram.py` and `uv run pytest -m slow tests/test_ram_proof.py -v --no-cov`. Record real numbers. Do not edit the limits.

- [ ] **Step 4: Act on the result.**
  - All limits met: go to Step 5.
  - Limit missed: first make the engine faster using profiling, keeping behaviour identical. If that fails, reduce `RAM_ADDRESS_BITS` by one and repeat. Never go below 10 (1K words), and never add a behavioural store. If 10 fails, **stop and report to the owner**.
  - If the size changed, tell the owner the new size in the Task 8 report.

- [ ] **Step 5: Record the result.** Write `docs/concepts/how-big-is-our-memory.md` from the real measurements (analogy: counting how many lockers you can fit in the school, and how long it takes to walk the corridors; ideas `gates`, `4k`, `measured`). It explains how many gates one word costs, why simulating memory is the hard part, and why we chose real gates over a shortcut. Its `## Try It` calls `measure(6)` and prints only the gate count, since timings vary per machine. This page is written last because it reports results; every number in it comes from Step 3. Add it to `KEY_IDEAS`, and add the final size and numbers to a "Proof result" section in the roadmap.

- [ ] **Step 6: Run** `uv run pytest`. Expected: PASS.

- [ ] **Step 7: Commit.** `git commit -m "test: prove RAM size is workable and record results"`

---

### Task 9: The Bench page

The Bench is the first form of the Cockpit's zoom panel. It is a local page for looking inside any part built so far, with no CPU yet.

**Files:**
- Create: `src/pycpu/bench/__init__.py`, `src/pycpu/bench/app.py`, `src/pycpu/bench/page.html`, `src/pycpu/__main__.py`, `docs/concepts/the-bench.md`
- Modify: `tests/test_docs.py`, `mkdocs.yml`, `docs/index.md`, `README.md`
- Test: `tests/test_bench.py`

**Docs first.** Write `the-bench.md` before Step 2 (analogy: an electronics workbench with the lid off; ideas `bench`, `alu`, `gate`). Its `## How It Works` is a guided tour: add 3 and 1, then zoom down and find the exact gate that carried the one. Add it to `KEY_IDEAS`. The page itself labels each level with a one-line plain-words explanation and a link to its concept page, because the Bench is a teaching tool, not just a debugger. After the browser check, update `docs/index.md` and `README.md` to reflect what now exists.

**Interfaces:**
- Consumes: `alu`, `AluOp`, `Circuit`, `Simulator`, `circuit_view`; PyWeb's `pyweb.app.App`, `pyweb.response.html_response`, `json_response`, `not_found`, `pyweb.testing.TestClient`, `pyweb.server` for serving.
- Produces: `create_bench() -> App`; `python -m pycpu` serves it on port 8765 and prints the URL.

Routes:
- `GET /` serves `page.html`.
- `GET /api/view?path=<scope>` returns `circuit_view` as JSON, or a 404 via `not_found("No part called <path>")`.
- `POST /api/inputs` with `{"a": int, "b": int, "op": int}` sets the ALU's inputs, settles, and returns `{"result", "zero", "negative", "carry", "overflow"}`. Out-of-range values return 400.

The page has inputs for A, B and op, and a drill-down list of scopes with a breadcrumb trail. Each gate shows inputs and output, with wires carrying a 1 highlighted. Use plain HTML, CSS and JavaScript with no external libraries or build step.

- [ ] **Step 1: Confirm the API.** Read `pyweb/src/pyweb/testing.py`, `pyweb/src/pyweb/server.py` and one PyWeb test to confirm how `TestClient` is built and awaited, and how an `App` is served. Pin those names in the tests below.

- [ ] **Step 2: Write failing tests** in `tests/test_bench.py`:
  - `POST /api/inputs` with `a=0x7FFF, b=1, op=0` returns `result == 0x8000`, `overflow == 1`.
  - `GET /api/view?path=alu.adder.bit0` returns 200, and after inputs `a=1, b=1` its child scopes' gate values report real wires: at least one `value_out` differs from the same view after `a=0, b=0`.
  - `GET /api/view?path=alu.nope` returns 404 and the body contains `No part called alu.nope`.
  - `POST /api/inputs` with `a=70000` returns 400.

- [ ] **Step 3: Run** `uv run pytest tests/test_bench.py -v`. Expected: FAIL.

- [ ] **Step 4: Implement** `bench/app.py`, `page.html` and `__main__.py`. Add `src/pycpu/bench/page.html` to the wheel via `force-include`, as pyllm does for data files, and read it with `importlib.resources`.

- [ ] **Step 5: Run** `uv run pytest tests/test_bench.py -v`. Expected: PASS.

- [ ] **Step 6: Check in a real browser.** Run `uv run python -m pycpu`, open the page, set `a=3, b=1, op=0`, and drill down from `alu` to a gate in `alu.adder.bit1`. Expected: the result is 4, and gate values change when the inputs change.

- [ ] **Step 7: Final verification.** Run `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run pyright src tests`. Expected: all pass.

- [ ] **Step 8: Commit and open the PR.** `git commit -m "feat: add bench page for looking inside the circuit"`. Merge once CI is green. Create no tag.
