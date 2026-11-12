# PyCPU Plan 7: Integration and First Release

**Status:** draft, 2026-11-12. Builds on the PyCPU spec (`2026-11-01-pycpu-design.md`,
sections 7 to 9) and the roadmap's "Notes for Plan 7".

## Why

Plans 1 to 6 built the whole climb, from NAND gates to Pebble running in the Cockpit, and
the owner's browser checks have passed. On 2026-11-12 the owner gave the go-ahead to make
PyCPU public. That covers PyPI `v0.1.0`, the docs site on GitHub Pages, the series listing
and the links from PyStack. Plan 7 does all of that, and it closes the story for the reader
with a "you built a computer" page.

## Goals

1. **The closing page.** `docs/you-built-a-computer.md` is the last page of the climb. It
   looks back at every layer, in one table from NAND to Pebble, and runs one Pebble
   program on the CPU in its `## Try It`. It ends by pointing at PyStack, where the
   computer sits underneath everything else. `docs/index.md` and `docs/from-scratch.md`
   link to it.
2. **A public docs site.** PyCPU's docs deploy to `https://robcox2910.github.io/pycpu/`.
   The Cockpit's "Read about it" links go to that site, not to `127.0.0.1:8000`.
   `DOCS_URL` in `cockpit/code.py` is the only place that address is set: `page.html`
   gets it from the server and no longer has its own `DOCS_SERVER`.
3. **Installable and runnable.** Add a `pycpu` console script that runs the same thing
   as `python -m pycpu`. The README and the docs show both ways to start PyCPU: from a
   clone with `uv run pycpu`, or from PyPI with `uvx --from fromscratch-pycpu pycpu`.
   The "See it in the Cockpit" links still go to `http://127.0.0.1:8765`, because the
   Cockpit only ever runs on your own computer. Each page with one of those links says
   how to start the Cockpit, or links to the place that does.
4. **The switch turned on.** Remove the "do not publish yet" notes from `CLAUDE.md`, from
   the `release.yml` and `docs.yml` comments, and from the roadmap. `docs.yml` gets back
   the standard push trigger. That happens through `series sync` where the sync owns the
   file, and by hand otherwise.
5. **Definition of done.** The roadmap gets a final pass against spec section 9, with
   every row Done and its evidence. The last row, "PyStack launches it and `import "cpu"`
   works", points at the PyStack PR.
6. **Release.** Tag `v0.1.0` on main. `release.yml` then publishes `fromscratch-pycpu` to
   PyPI and makes a GitHub release.
7. **PyStack plugin.** `pystack/src/pystack/plugins/cpu_plugin.py` follows PyStack's
   plugin rules: state on the instance, `@pebble_method`, and only Pebble's public API.
   It depends on `fromscratch-pycpu>=0.1.0` and adds:
   - the Pebble module `cpu`:
     - `cpu_run(source)` returns everything the program printed when run on PyCPU's
       fast engine (`pycpu.translator.program.run_pebble`). If the run faults, it
       returns the `describe()` sentence instead. If PyCPU can't run the program, it
       returns a friendly `error: ...` string.
     - `cpu_steps(source)` returns how many machine instructions the program took.
   - the shell command `cockpit`, which builds the Cockpit and serves it in a background
     thread, then returns its address. A second `cockpit` returns the same address.
     `shutdown` closes the server.
   - registration in `environment.py`, a docs section and tests, as for every other
     plugin. Then a PyStack release tag, following the series rule that a feature gets
     a tag.
8. **Series listing.** Add PyCPU to `series.yml` with `builds_on: [Pebble, PyNet, PyWeb]`,
   placed after PyWeb and before PyStack. Add it to `HOME_GROUPS` under "Putting it
   together", before `pystack`, and add PyCPU to PyStack's `builds_on`. Turn on Pages.
   Run `series sync` for PyCPU and then for every repo, and regenerate the hub with
   `series hub`. This follows the "Add a project" runbook in `robcox2910.github.io/README.md`.

## Non-goals

- Rebuilding the Cockpit inside PyStack's Flask UI (spec section 7).
- Any new CPU, Pebble-subset or Cockpit features.
- A hosted Cockpit. It stays on `127.0.0.1`.

## Order and checkpoints

The steps have to happen in this order, because each one needs the one before:

1. **PyCPU PR** (goals 1 to 5). Owner browser check, then merge.
2. **PyPI trusted publisher.** The owner adds a pending publisher for
   `fromscratch-pycpu` on pypi.org, unless one already exists. It needs repo
   `robcox2910/pycpu`, workflow `release.yml` and environment `pypi`. Only the owner can
   do this, because it needs their PyPI login. Before asking, check whether the `pypi`
   environment exists on the repo.
3. **Tag `v0.1.0`.** Check with the owner before pushing it, because a PyPI version can
   never be reused. Then confirm the package is on PyPI and installs (goal 6).
4. **Pages on, then `series sync` and `series hub`** (goal 8), which gives PyCPU's docs
   their live site.
5. **PyStack PR** (goal 7), pinned to the released package. Merge it on green CI, then tag.

## Constraints

- Every number in the docs is measured, never invented (repo `CLAUDE.md`).
- The closing page follows the documentation standard and is added to `mkdocs.yml` and to
  `KEY_IDEAS`.
- Never edit a block that `series sync` owns by hand. Change the source and re-run.
- Never force-push.

## Left to the builder

- The closing page's wording and its example program, as long as the output is measured.
- Where the "how to start the Cockpit" note sits on each page (inline, or a link).
- PyStack's test layout. `tests/test_cpu_plugin.py` is the default.
