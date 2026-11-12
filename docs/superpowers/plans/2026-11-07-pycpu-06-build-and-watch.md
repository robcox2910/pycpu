# Build It, Then Watch It: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to carry out this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Join PyCPU's two halves. The Cockpit shows the real code that built each part, walks point back to their concept pages, a "Build It Yourself" page runs through the docs from NAND to Pebble, and the story leads with building.

**Architecture:**
- The gate machine records which Python function built each part, next to the taps it already records.
- A new `src/pycpu/cockpit/code.py` reads that function's live source with `inspect`, cut down to the part's `with c.scope(...)` block, and `/api/part` returns it as `built_by`.
- The page draws it in the glass.
- Registers and RAM get taps and part views.
- The docs gain one page and a reordered story.

**Tech stack:** Python 3.13, PyWeb (`fromscratch-pyweb`), `inspect`, a single-file HTML page, MkDocs, pytest with Hypothesis, ruff, and pyright in strict mode.

**Spec:** `docs/superpowers/specs/2026-11-07-pycpu-build-and-watch-design.md`

## Global Constraints

- No change to what the machine computes. At 6 address bits there are still 15,525 gates and 15,529 wires (`tests/test_parts_view.py` pins both). Taps and builder records make no gate and no wire.
- Never fake the gate view. The code panel shows the live source of the function that built the circuit. It is never a copy kept in a file or a string.
- Nothing is exposed:
  - no Pages, no tag, no `series.yml`, no PyPI;
  - no links from other projects;
  - links only point at `http://127.0.0.1:8765` (the Cockpit) or `http://127.0.0.1:8000` (`uv run mkdocs serve`).
- The page stays one self-contained HTML file: no `innerHTML` with server text, and no external URLs. It never scrolls at 1280×720, and works in dark mode and at 375 px.
- Docs come first, for a curious 12-year-old. Every figure is printed or pinned. Plan 1's Documentation Standard and Plan 4's additions apply: a new page goes in `mkdocs.yml` and `KEY_IDEAS`, with sections in order (`## Try It`, `## How It Works`, `## Why Does This Matter?`, `## What's Next`).
- Never use `TYPE_CHECKING` or `from __future__ import annotations`. Use uv for everything.
- PyStack and the release are Plan 7.

## Review Focus

1. **Wrong block shown.** A builder method that builds two parts, such as `_build_write_back` (write-back and the stack pointer), must show only the viewed part's `with c.scope(...)` block. Showing the whole method is acceptable only when the part's scope opens outside it, and a test names each case.
2. **Source missing.** If `inspect` can't find a source (for example when run from a zip), `built_by.code` is None and the page says "The code isn't available here." It never errors.
3. **Long code at 375 px and at 1280×720.** The panel scrolls inside itself. The page never scrolls.
4. **Registers or RAM viewed while playing.** These answer 409 like the other parts, with `BUSY_MESSAGE`.
5. **The build path's names go stale.** Every function, page and test file that "Build It Yourself" names must exist, checked by import and path.

---

### Task 1: Part views for the registers and the RAM

**Files:**
- Modify: `src/pycpu/cpu.py` (taps in `_build_datapath` for `cpu.registers`; a `ram` tap after `Ram(...)` in `__init__`)
- Modify: `src/pycpu/cockpit/picture.py` (`PART_NAMES`)
- Modify: `docs/concepts/the-magnifying-glass.md` (the parts table)
- Test: `tests/test_parts_view.py`

**Interfaces:**
- Produces:
  - `GateMachine.taps["cpu.registers"]`, with inputs `write`, `write_select`, `data`, `read_a` and `read_b`, and outputs `a` and `b`;
  - `GateMachine.taps["ram"]`, with inputs `address`, `data` and `write`, and output `out`;
  - `PART_NAMES["cpu.registers"] = "registers"` and `PART_NAMES["ram"] = "RAM"`.

Steps:
- [ ] **Step 1: Write the failing tests.**
  - Make one `cockpit_client` at 6 bits running the countdown, and pause it after `li r1, 5` executes.
  - `GET /api/part?path=cpu.registers` gives a 200 with names `["write", "write_select", "data", "read_a", "read_b"]` and outputs `["a", "b"]`. Every value equals the register file's real wires as read by `simulator.get`, and the `data` value written is 5.
  - `GET /api/part?path=ram` gives a 200 with inputs `["address", "data", "write"]` and outputs `["out"]`. `out` equals the word at `address` in `state.memory`.
  - Both answer 409 with `BUSY_MESSAGE` while playing.
  - `GATES_AT_6_BITS` and `WIRES_AT_6_BITS` are unchanged.
- [ ] **Step 2: Run them.** `uv run pytest tests/test_parts_view.py -q`. Expect the new tests to fail with 404.
- [ ] **Step 3: Implement.**
  - Call `self._tap("cpu.registers", …)` right after `RegisterFile(...)` with the wires passed to it and `bank.a`/`bank.b`.
  - Add the `ram` tap after `self._ram = Ram(...)`, with `ram_address`, `ram_data`, `(ram_write,)` and `self._ram.out`. Use the real address width; the part view adds bits with `simulator.get` as it already does.
  - Add the two `PART_NAMES` entries.
  - Add the registers and RAM rows to the parts table in `the-magnifying-glass.md`, with what each value means in one sentence a 12-year-old can follow.
- [ ] **Step 4: Run** `uv run pytest tests/test_parts_view.py tests/test_docs.py -q`. Expect all to pass.
- [ ] **Step 5: Commit.** `feat: part views for the registers and the RAM`

### Task 2: The code that built each part

**Files:**
- Modify: `src/pycpu/cpu.py` (`GateMachine.builders`)
- Create: `src/pycpu/cockpit/code.py`
- Modify: `src/pycpu/cockpit/picture.py` (`part_picture` adds `built_by`) and `src/pycpu/cockpit/app.py` (only if the route needs it)
- Create: `docs/concepts/the-code-behind-a-part.md`, added to `mkdocs.yml` under The Cockpit and to `KEY_IDEAS`
- Test: `tests/test_code_view.py`

**Interfaces:**
- Consumes: the taps from Task 1 and `PART_NAMES`.
- Produces:
  - `GateMachine.builders: dict[str, Callable[..., object]]`, which maps each tapped part path to the function or method that built it:
    - `cpu.alu` → `pycpu.arithmetic.alu`
    - `cpu.registers` → `pycpu.cpu_parts.RegisterFile.__init__`
    - `ram` → `pycpu.memory.Ram.__init__`
    - each `cpu.*` block → its `GateMachine._build_*` method
  - `PART_PAGES: dict[str, str]`, in `code.py`, from part path to concept page stem.
    - Start from these: `cpu.alu`→`the-alu`, `cpu.registers`→`registers`, `ram`→`ram`, `cpu.halt`→`what-happens-when-things-go-wrong`; the rest→`the-control-unit`.
    - Keep a mapping only if that page's How It Works actually describes the part. Otherwise pick the page that does, and say which in the report.
  - `built_by(gate: GateMachine, path: str) -> dict[str, object]`, which returns:
    - `function` (a dotted name such as `"pycpu.arithmetic.alu"`);
    - `file` (repo-relative, such as `"src/pycpu/arithmetic.py"`);
    - `line` (the first line shown, 1-based);
    - `code` (str, or None if `inspect` can't find a source);
    - `page` (`{"title", "url"}`, with `url` = `http://127.0.0.1:8000/concepts/<stem>/`).
  - `part_picture(...)["built_by"]`, which is `built_by(...)`.

Steps:
- [ ] **Step 1: Write the doc first.**
  - Write `the-code-behind-a-part.md`. Open with an everyday analogy, then:
    - a table of parts → function → page;
    - a `## Try It` that prints `built_by(...)` for the ALU's first lines and file, with the output pinned;
    - How It Works, which explains how `inspect` reads the live module, why that means the code can't drift, and how a two-part method is cut to one block;
    - the docs-server sentence: "Start the docs on your own computer with `uv run mkdocs serve`."
- [ ] **Step 2: Write the failing tests.**
  - Every path in `GateMachine.taps` has a builder and a `PART_PAGES` entry. Every page stem names a file in `docs/concepts/`.
  - For `cpu.write_back`, `code` starts with `with c.scope("write_back"):` and does not contain `with c.scope("next_sp"):`. The reverse holds for `cpu.next_sp`.
  - For `cpu.alu`, `code` contains `with c.scope("alu"):`, and `file`/`line` point at the line in `arithmetic.py` that holds the first line of `code`. Read the file to check.
  - With `inspect.getsource` monkeypatched to raise `OSError`, `code` is None and the rest is still filled in.
  - `/api/part` answers include `built_by`.
  - The doc's Try It output is pinned (the existing docs-runner test covers this once the page is in `KEY_IDEAS`).
- [ ] **Step 3: Run them.** `uv run pytest tests/test_code_view.py -q`. Expect a fail.
- [ ] **Step 4: Implement.**
  - Record `self.builders[part] = <function>` next to each `_tap`. A small helper parameter on `_tap` is fine.
  - `code.py`:
    - Use `inspect.getsourcelines`.
    - Find the line `with c.scope("<last path segment>"):`. If it's there, keep that line and every following line indented deeper than it, using `textwrap.dedent`. If it's not there, keep the whole function.
    - `line` = the start line + the offset.
    - Make the file path relative to the repo root found from `pycpu.__file__`'s parents.
- [ ] **Step 5: Run** `uv run pytest tests/test_code_view.py tests/test_parts_view.py tests/test_docs.py -q && uv run pyright src tests`. Expect a pass.
- [ ] **Step 6: Commit.** `feat: the Cockpit knows the code that built each part`

### Task 3: The page shows the code, and walks point to their pages

**Files:**
- Modify: `src/pycpu/cockpit/page.html`
- Modify: `docs/concepts/the-cockpit.md` and `docs/concepts/guided-walks.md`
- Test: `tests/test_cockpit.py`

**Interfaces:**
- Consumes: `part_picture(...)["built_by"]` from Task 2, and `walk.see_also`. Add `see_also` to `walk_picture` if it isn't there, with a test in `tests/test_walks.py`.

Steps:
- [ ] **Step 1: Write the failing tests.** String pins in the same style as the existing `test_cockpit.py` page tests:
  - a "The code that built this" heading on the part view;
  - the code goes in through `textContent` inside a `<pre>` that scrolls inside itself (`overflow:auto`);
  - "The code isn't available here." for a None `code`;
  - the file:line text;
  - the "Read about it" link built from `built_by.page.url`, plus the `uv run mkdocs serve` sentence;
  - the walk's done card names `see_also`'s page title with the same kind of link.
  - Also check that no `innerHTML` and no URL other than `127.0.0.1` appear.
- [ ] **Step 2: Run them.** Expect a fail.
- [ ] **Step 3: Implement.**
  - In the part view, the existing inputs and outputs stay on top. Below them, put a "The code that built this ▸" toggle, closed by default so the 1280×720 layout doesn't change. When opened, it shows file:line, the code and the link.
  - Add the registers and RAM parts to the trail and the CPU part list wherever the page lists parts.
- [ ] **Step 4: Update the docs.**
  - In `the-cockpit.md`, describe the toggle, the two new parts and the link. Keep the drawing true to the page.
  - In `guided-walks.md`, describe the done card's pointer.
- [ ] **Step 5: Run** `uv run pytest tests/test_cockpit.py tests/test_walks.py tests/test_docs.py -q`. Expect a pass.
- [ ] **Step 6: Browser check.** Launch with `uv run python -m pycpu` and drive headless Chrome if you can:
  - open the ALU, write-back, registers and RAM views, and the code toggle on each, at 1280×720 and 375 px, light and dark;
  - check there's no page scroll and no JS errors.

  If you can't, record "browser check owed to controller".
- [ ] **Step 7: Commit.** `feat: the glass shows the code that built the part`

### Task 4: Build It Yourself

**Files:**
- Create: `docs/build-it-yourself.md`, added to `mkdocs.yml` right after From Scratch and to `KEY_IDEAS` if the docs tests need top-level pages there
- Test: `tests/test_docs.py`

Steps:
- [ ] **Step 1: Write the page.**
  - Open with an analogy: building a model kit, where each bag of pieces has its own picture of what you made.
  - Then a numbered path in nav order, from Switches and NAND to Printing a Number. Each step is a table row: what you build, the function (dotted name), the page link, the test file that checks it, and "Watch it" (a Cockpit walk link `http://127.0.0.1:8765/#walk=<name>`, or the part name to open in the glass, or "—").
  - Add `## Try It`: one block that builds a half adder, a full adder and a 4-bit ripple adder from the existing functions and prints their gate counts. Pin the output, using the same numbers `adding.md` prints.
  - `## How It Works` explains the rule that each rung uses only the rung below, and how the tests check each rung.
  - `## Why Does This Matter?` and `## What's Next`, which points at the Cockpit and the walks.
- [ ] **Step 2: Write the tests.**
  - Every dotted function name in the table imports.
  - Every page link resolves to a file.
  - Every test file named exists.
  - Every `#walk=` name is in `WALK_ORDER`.
  - Every part named is in `PART_NAMES`.
  - The rows follow the `mkdocs.yml` nav order of their pages.
- [ ] **Step 3: Run** `uv run pytest tests/test_docs.py -q && uv run mkdocs build --strict`. Expect a pass.
- [ ] **Step 4: Commit.** `docs: build it yourself, from NAND to Pebble`

### Task 5: The story leads with building, and the hand-off to Plan 7

**Files:** `README.md`, `docs/index.md`, `docs/from-scratch.md`, `CLAUDE.md` (Project notes), `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md`, `tests/test_docs.py` if any pinned sentence changes

Steps:
- [ ] **Step 1: Story.**
  - The README and `index.md` open with building a computer from NAND gates in code, and link to Build It Yourself first. The Cockpit comes second, as the place to check and watch what you built.
  - In the README ladder, show the Cockpit beside the ladder, not as its top rung. Use the words "watch any rung in the Cockpit".
  - `from-scratch.md` gets a short "Build, then watch" section.
  - The README Concepts table adds Build It Yourself and The Code Behind a Part.
- [ ] **Step 2: Fix stale notes.**
  - In `CLAUDE.md` Project notes, change "no version tags until Plan 5" and "PyCPU gets no tag until Plan 5" to "until the owner gives the go-ahead (Plan 7 at the earliest)".
  - Change "What the zoom shows" to "What the glass shows".
- [ ] **Step 3: Roadmap.**
  - Plan 6 becomes this plan, and PyStack plus the release become Plan 7.
  - Rename "Notes for Plan 6, after Plan 5" to "Notes for Plan 7".
  - Drop the registers and RAM deferral, which is now done.
  - Add this plan's parked minors and the owner's go-ahead, which is still needed.
- [ ] **Step 4: Final verification.**
  - `uv run pytest && uv run pytest -m slow --no-cov && uv run pytest --hypothesis-profile=thorough --no-cov tests/test_parts_view.py tests/test_code_view.py`
  - `uv run ruff check . && uv run ruff format --check . && uv run pyright src tests examples && uv run mkdocs build --strict`

  Expect everything to pass.
- [ ] **Step 5: Commit.** `docs: build first, then watch`. Then the controller:
  - pushes;
  - opens the PR;
  - asks the owner for a browser check;
  - merges once CI is green and the check passes.

  No tag.
