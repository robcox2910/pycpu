# Contributing to PyCPU

Thanks for your interest in contributing! This guide covers everything you need
to get started.

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.14+ | [python.org](https://www.python.org/downloads/) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| git | 2.x+ | [git-scm.com](https://git-scm.com/) |

## Setup

```bash
# Clone the repo
git clone https://github.com/robcox2910/pycpu.git
cd pycpu

# Install all dependencies (including dev and docs tools)
uv sync --all-extras

# Install pre-commit hooks (linting + commit message validation)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
```

Verify everything works:

```bash
uv run pytest                  # tests pass, >= 90% coverage
uv run ruff check .            # no lint errors
uv run pyright src tests       # no type errors
uv run mkdocs build --strict   # the docs build cleanly
```

## The Rules That Make PyCPU PyCPU

These matter more than any style rule below:

- **NAND is the only building block.** Nothing above `simulator.py` may work out
  a logic result in plain Python, except test helpers and `peek`/`poke`.
- **Never fake the gate view.** What the zoom shows must be the real circuit
  computing the real value.
- **RAM is real gates.** Never add a shortcut store that skips them.
- **Docs come first.** Write a concept page before its code (see below).

## TDD Workflow

We follow **Red-Green-Refactor** for every code change:

1. **Red** -- Write a failing test that describes the behaviour you want.
2. **Green** -- Write the simplest code that makes the test pass.
3. **Refactor** -- Clean up while keeping all tests green.

Never skip the red step. A new concept page's `## Try It` counts as a failing
test: `tests/test_docs.py` runs it, so it fails until the code exists.

## Branch Naming

Create a branch from `main` using one of these prefixes:

| Prefix | When to use |
|--------|-------------|
| `feat/` | New feature or circuit |
| `fix/` | Bug fix |
| `refactor/` | Restructuring without behaviour change |
| `test/` | Test-only changes |
| `docs/` | Documentation updates |
| `ci/` | CI/CD workflow changes |
| `chore/` | Dependency bumps, config tweaks |

Example: `feat/program-counter`, `fix/ram-write-hazard`

## Conventional Commits

Every commit message must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short description in imperative mood>

Optional longer explanation.
```

Types match the branch prefixes: `feat:`, `fix:`, `refactor:`, `test:`,
`docs:`, `ci:`, `chore:`.

Good examples:

```
feat: add a 16-bit register
fix: settle before the write pulse
docs: add the clock concept page
```

Bad examples:

```
updated stuff          # no type, vague description
feat: adds register    # not imperative mood ("adds" -> "add")
```

## Code Style

### Modern Python

Use Python 3.14 idioms everywhere:

- `X | Y` for union types (not `Union[X, Y]` or `Optional[X]`)
- `match/case` instead of if/elif chains where appropriate
- Never use `TYPE_CHECKING` or `from __future__ import annotations`

### Wires and Buses

- Words are 16 bits.
- A bus is a tuple of wires, **least significant bit first**.

### Docstrings

Every public function, method, class, and module needs a docstring:

- Use **imperative mood**: "Return the sum." not "Returns the sum."
- One-liner for simple functions, multi-line (Google style) for complex ones.
- Module docstrings open with an everyday analogy and run at least 3 lines.

```python
def half_adder(c: Circuit, a: int, b: int) -> tuple[int, int]:
    """Add two bits and return the sum bit and the carry bit."""
```

### Named Constants

Use named constants instead of magic numbers in tests and source code. Ruff
rule PLR2004 enforces this.

```python
# Good
GATES_IN_A_HALF_ADDER = 6
assert c.gate_count == GATES_IN_A_HALF_ADDER

# Bad
assert c.gate_count == 6
```

## Linting and Type Checking

Run these before every commit (pre-commit hooks enforce them automatically):

```bash
uv run ruff check .             # lint
uv run ruff format .            # format (or --check to verify)
uv run pyright src tests        # type check (strict mode)
```

Fix all violations. Inline `# noqa:` is acceptable only when tools genuinely
conflict.

## Testing

```bash
uv run pytest                   # run the tests (slow ones are skipped)
uv run pytest -m slow           # run the slow tests, such as the 4K RAM proof
uv run pytest tests/test_ram.py # run a specific file
uv run pytest -k "half_adder"   # run tests matching a pattern
```

- Minimum **90% coverage** is enforced.
- Test classes and methods need docstrings too.
- Long-running tests carry `@pytest.mark.slow`.
- Every program in `examples/` is run by `tests/test_examples.py`.

## Documentation Style

Our docs target a **curious 12-year-old who has never heard of a logic gate**.
Documentation ranks above every other rule: a change with good code and weak
docs is not finished.

Each concept page in `docs/concepts/` has:

- an everyday analogy first, and a table;
- `## Try It`, a runnable example with its exact output after `# Output:`;
- `## How It Works`, showing how the thing is built from the layer below;
- `## Why Does This Matter?` and `## What's Next`, which links the next page.

Numbers in the docs are measured, never invented. Add each new page to
`mkdocs.yml` and to `KEY_IDEAS` in `tests/test_docs.py`.

Good:

> A register is like a row of light switches with a "save" button: you can
> set the switches however you like, but the row only remembers them when the
> clock says "now".

Bad:

> A register is an array of edge-triggered D flip-flops sharing a common
> enable and clock net.

## Pull Request Process

1. Create a feature branch from `main`.
2. Make your changes following TDD, docs first.
3. Ensure all checks pass: `uv run ruff check .`, `uv run pyright src tests`,
   `uv run pytest`, `uv run mkdocs build --strict`.
4. Push your branch and open a PR against `main`.
5. PRs are squash-merged to keep history clean.

## Questions?

Open an issue on [GitHub](https://github.com/robcox2910/pycpu/issues) --
we're happy to help!
