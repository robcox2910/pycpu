# PyCPU Integration and First Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the climb with a "you built a computer" page, make PyCPU public (docs site, PyPI `v0.1.0`, series listing) and plug it into PyStack as `import "cpu"` plus a `cockpit` command.

**Architecture:** Tasks 1 to 3 are one PyCPU PR, on branch `plan-7-integration-and-release`. After the owner's check it merges, and then the controller does the release steps (R1 to R3) by hand. Task 4 is a PyStack PR pinned to the released package. Task 5 is the series sync.

**Tech Stack:** Python 3.14, uv, hatch-vcs, mkdocs-material, PyWeb/PyNet, Pebble public API, GitHub Actions, PyPI trusted publishing.

**Spec:** `docs/superpowers/specs/2026-11-12-pycpu-integration-and-release-design.md`

## Global Constraints

- Docs come first, for a curious 12-year-old: an analogy first, then a table, `## Try It`, `## How It Works`, `## Why Does This Matter?` and `## What's Next`. Every number is measured.
- The public docs base is `https://robcox2910.github.io/pycpu/`. The Cockpit stays at `http://127.0.0.1:8765`.
- The package is `fromscratch-pycpu`, the first version is `v0.1.0`, and the console script is `pycpu`.
- In PyStack: plugin state lives on the instance, Pebble is used only through its public API, and the dependency is `fromscratch-pycpu>=0.1.0`.
- Never edit a block that `series sync` owns by hand. Never force-push.
- Run `uv run ruff check .`, `uv run ruff format --check .`, `uv run pyright src tests`, `uv run pytest` and `uv run mkdocs build --strict` before each commit.

## Review Focus

1. Some "Read about it" link in the Cockpit still points at `127.0.0.1:8000` after the switch. A test greps `src/` for that address.
2. `cpu_run` gets a program PyCPU can't run, like a list or a Pebble syntax error. It must return an `error:` string, never crash the PyStack shell. Task 4 tests both.
3. `cpu_run` gets a program that never stops. It must give up after the step limit and return the `describe()` sentence. Task 4 tests `while true {}`.
4. The user types `cockpit` twice, or exits PyStack with the Cockpit open. The second call returns the same address, and `shutdown` closes the server. Task 4 tests both, using port 0.
5. The `uvx --from fromscratch-pycpu pycpu` line in the docs must be really runnable once released. R3 runs it from a clean temp directory.

---

### Task 1: The closing page

**Files:**
- Create: `docs/you-built-a-computer.md`
- Modify: `mkdocs.yml` (nav: after `Build It Yourself`, as `You Built a Computer`), `tests/test_docs.py` (`KEY_IDEAS`), `docs/index.md`, `docs/from-scratch.md`

- [ ] **Step 1:** Add the page to `KEY_IDEAS` with its key ideas: NAND as the one brick, layers each built from the one below, and the same program running on the real gates. Run `uv run pytest tests/test_docs.py`. It should fail because the page is missing.
- [ ] **Step 2:** Write the page:
  - A table of every layer (NAND → gates → adder/ALU → memory → CPU → assembler → Pebble → Cockpit), each with its concept page link and gate count. Use the measured figures already pinned in the docs, such as 15,525 gates at 6 bits; measure any new figure with a throwaway script.
  - A `## Try It` that runs a short Pebble program with `run_pebble` and shows its real output and step count.
  - A `## What's Next` that points at PyStack (`import "cpu"`).

  Link to it from the end of `docs/index.md` and `docs/from-scratch.md`.
- [ ] **Step 3:** Run all the checks. Commit `docs: the closing page, you built a computer`.

### Task 2: Public docs links and the `pycpu` command

**Files:**
- Modify: `src/pycpu/cockpit/code.py` (`DOCS_URL`), `src/pycpu/cockpit/page.html` (remove `DOCS_SERVER`), `src/pycpu/cockpit/app.py` or wherever the walk `see_also` URL is built, `pyproject.toml` (`[project.scripts] pycpu = "pycpu.__main__:main"`), `README.md`, `docs/index.md`, and the docs pages that mention `127.0.0.1:8000` or start the Cockpit
- Test: `tests/test_cockpit.py`, `tests/test_code_view.py`

**Interfaces:**
- Produces: `DOCS_URL = "https://robcox2910.github.io/pycpu/concepts"` in `pycpu.cockpit.code`. It is the only source of the docs address, and both `built_by(...)["page"]["url"]` and `walk_picture(...)["see_also"]["url"]` start with it.

- [ ] **Step 1:** Write the failing tests:
  - `test_docs_links_are_public` checks that `built_by` and `see_also` URLs start with `https://robcox2910.github.io/pycpu/concepts/`.
  - `test_no_local_docs_server` checks that no file under `src/` contains `127.0.0.1:8000`.
  - `test_console_script` checks that `pyproject.toml` maps `pycpu` to `pycpu.__main__:main`.
- [ ] **Step 2:** Make them pass. `page.html` must take its links from the URLs the API returns, never build its own.
- [ ] **Step 3:** Update the docs:
  - Replace `uv run python -m pycpu` with `uv run pycpu`, and add the PyPI way: `uvx --from fromscratch-pycpu pycpu`.
  - Fix the pages that describe `127.0.0.1:8000`: `the-cockpit.md`, `guided-walks.md` and `the-code-behind-a-part.md`.
  - Make sure every page with a `127.0.0.1:8765` link says how to start the Cockpit, or links to the place that does.
- [ ] **Step 4:** Run all the checks. Commit `feat: public docs links and a pycpu command`.

### Task 3: Turn the switch on and the definition of done

**Files:**
- Modify: `CLAUDE.md` (remove both "until the owner gives the go-ahead" notes), `.github/workflows/release.yml` and `docs.yml` (comments; `docs.yml` gets the standard `push: branches: [main]` trigger plus `workflow_dispatch`), `docs/superpowers/plans/2026-11-01-pycpu-roadmap.md` (the top note, plus a "Plan 7" section with the spec section 9 table; the PyStack row says "Plan 7 Task 4, PyStack PR")

- [ ] **Step 1:** Make the edits. Keep the definition-of-done table's evidence column real (test file names, page links).
- [ ] **Step 2:** Run all the checks. Commit `chore: switch on publishing for v0.1.0`.

### Owner check, then release (controller, by hand)

- [ ] **R1:** Push and open the PR. The owner's browser check covers the closing page, the Cockpit's "Read about it" links (they now go to the public site, which only works once Pages is on), and `uv run pycpu`. Merge on green CI.
- [ ] **R2:** Check `gh api repos/robcox2910/pycpu/environments`. Ask the owner to confirm the PyPI pending publisher (`fromscratch-pycpu`, `robcox2910/pycpu`, `release.yml`, environment `pypi`) and to approve tagging `v0.1.0`.
- [ ] **R3:** Tag `v0.1.0` on main and push the tag. Watch `release.yml`. Then run `cd $(mktemp -d) && uvx --from fromscratch-pycpu==0.1.0 python -c "from pycpu.translator.program import run_pebble; print(run_pebble('print(1 + 2)').output)"`, which should print `3`.

### Task 4: PyStack `cpu` plugin (repo `pystack`, branch `feat/pycpu-plugin`)

**Files:**
- Create: `src/pystack/plugins/cpu_plugin.py`, `tests/test_cpu_plugin.py`
- Modify: `pyproject.toml` (`fromscratch-pycpu>=0.1.0`, then `uv lock`), `src/pystack/environment.py` (register `CPUPlugin`), `docs/index.md` and `README.md` (a PyCPU section, in the same style as the other plugins)

**Interfaces:**
- Consumes: `pycpu.translator.program.run_pebble(source, max_steps=1_000_000) -> PebbleRun`, with `.output`, `.halted`, `.fault`, `.steps` and `.describe()`. Also `pycpu.translator.subset.PebbleCPUError`, `pebble.PebbleError`, and `pycpu.__main__.open_cockpit(port, address_bits, start_example) -> AsyncServer` (async, PyNet loop).
- Produces: `CPUPlugin` with the Pebble module name `cpu`, the functions `cpu_run(source)` and `cpu_steps(source)`, and the shell command `cockpit`.

- [ ] **Step 1:** Write the failing tests:
  - `cpu_run('print(1 + 2)')` returns `"3\n"`, or whatever PyCPU really prints; measure it.
  - `cpu_steps` returns a positive int.
  - A list program and a syntax error each return a string starting `error:`.
  - `while true {}` returns the "still running" `describe()` sentence (pass a small step limit through a plugin attribute so the test is fast).
  - `import "cpu"` works through PyStack's own Pebble front door.
  - `cockpit` on port 0 returns `http://127.0.0.1:<port>`, a second call returns the same address, and `shutdown_all()` closes it so a request to the address fails.
- [ ] **Step 2:** Implement `CPUPlugin`. The Cockpit runs in a daemon thread with its own PyNet loop. The thread, server and address live on the plugin instance. `shutdown` stops the loop and joins the thread.
- [ ] **Step 3:** Run PyStack's checks, open the PR, and merge on green. Then tag the next PyStack minor version.

### Task 5: Series listing (repo `robcox2910.github.io`, controller)

- [ ] **Step 1:** Run `gh api -X POST repos/robcox2910/pycpu/pages -f build_type=workflow`.
- [ ] **Step 2:** Make the `series.yml` and `HOME_GROUPS` changes from spec goal 8. Run `uv run pytest`, open the PR and merge on green.
- [ ] **Step 3:** Run `SERIES_SCRATCH=$(mktemp -d) uv run series sync --repo pycpu`, then the full `series sync`. Merge each PR on green CI.
- [ ] **Step 4:** Run `uv run series hub`, commit and merge. Check that `https://robcox2910.github.io/pycpu/` serves, and that a Cockpit "Read about it" link lands on a real page.
- [ ] **Step 5:** Update the roadmap's PyStack row to Done, with the PR link, in a small PyCPU docs PR.
