# Claude Code Instructions

<!-- standard:start -->
## Code Style

- All public functions, methods, classes, and modules **must** have a docstring
- Use imperative mood: "Return the result." not "Returns the result."
- One-line docstrings for simple functions; multi-line with summary + details for complex ones
- Follow the Google docstring convention (D211, D212 selected via ruff)

## Linting

- Ruff enforces a comprehensive rule set -- run `uv run ruff check .` before committing
- Pyright runs in strict mode -- run `uv run pyright src tests` before committing
- All violations must be fixed, not ignored. Exceptions are the repo-owned `ignore` and `per-file-ignores` lists in `pyproject.toml`, which belong to this repo; the series sync never edits them

## Testing

- TDD workflow: Red-Green-Refactor
- Coverage is enforced by pytest-cov; the floor in `pyproject.toml` is repo-owned
- Test classes and methods also require docstrings
- Use named constants instead of magic values (PLR2004)
- Run `uv run pytest` before committing
- Property-based tests (Hypothesis) live in `tests/test_properties.py` and `tests/test_model.py`; the shared profiles are in the root `conftest.py` (owned by `series sync`). Run `uv run pytest --hypothesis-profile=thorough` before a release.

## Commits

- Use conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`, `ci:`, `chore:`
- All changes go via PR from a feature branch (main is protected); merge when CI is green

## Dependencies

- Package manager: uv
- Run `uv sync --all-extras` after modifying dependencies
- `uv.lock` is committed; CI and pre-commit audit it with pip-audit through `uvx`, so pip-audit is not a project dependency
- Sibling projects, where used, are their PyPI releases (`fromscratch-<name>>=X.Y.Z`); never use `path` or git sources

## Releasing

- A release is a `vX.Y.Z` tag on main after the PR is merged
- Docs-only and tooling-only changes do not get a release tag
- Docs are built with `mkdocs build --strict` and deployed to GitHub Pages by the docs workflow
<!-- standard:end -->

## Project notes

PyCPU is an educational computer simulated from NAND gates. Teaching comes first.

- **NAND is the single primitive.** Nothing above `simulator.py` may compute a logic result in Python, except test helpers and `peek`/`poke`.
- **Never fake the gate view.** What the glass shows must be the real circuit computing the real value.
- **RAM is 4K words of 16 bits, every bit real gates.** If that proves unworkable, shrink the RAM; never add a behavioural store.
- 16-bit words. Buses are tuples of wires, least significant bit first.
- Never use `TYPE_CHECKING` or `from __future__ import annotations`.
- Documentation ranks above every other rule. Write each concept page before its code, for a curious 12-year-old: everyday analogy first, a table, a runnable `## Try It`, `## How It Works`, `## Why Does This Matter?`, `## What's Next`. Numbers in docs are measured, never invented.
- Every public module, class and function has a docstring; module docstrings open with an analogy and run at least 3 lines.
- Add each new page to `mkdocs.yml` and to `KEY_IDEAS` in `tests/test_docs.py`.
- Coverage floor is 90%. Slow tests carry `@pytest.mark.slow` and are skipped by default.
- Do not publish yet: no GitHub Pages, no `series.yml` entry, no version tags until the owner gives the go-ahead (Plan 7 at the earliest).
- PyCPU's Hypothesis tests are named by subject (`test_lockstep.py` and the like) rather than `test_properties.py`.
- `.github/workflows/release.yml` only runs on a `v*.*.*` tag, and PyCPU gets no tag until the owner gives the go-ahead (Plan 7 at the earliest), so nothing publishes yet.
