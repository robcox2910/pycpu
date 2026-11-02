# PyCPU

An educational computer, built from nothing but NAND gates, in Python.

Have you ever wondered what a computer *actually is*, underneath the apps and the
screen? PyCPU is a project that answers that question by building one, from the
very bottom. Everything starts with a single tiny part, the **NAND gate**: a switch
that only turns on when its two inputs are *not both on*. It sounds far too simple to
matter. But if you wire enough NAND gates together you can make every other gate, then
adders that do sums, then memory that remembers, and eventually a whole processor.

Part of the "from scratch in Python" series. Each layer is made only from the one
below it, so nothing is hidden, and nothing is faked: when a page shows you a circuit,
that is the real circuit, doing the real work.

## The ladder

Each rung is built only from the rung beneath it.

```
  Pebble programs        <- coming later in the climb
  Assembler              <- coming later in the climb
  The CPU                <- coming later in the climb
  Memory (RAM)           <- being built now
  Arithmetic (the ALU)   <- being built now
  Gates (AND, OR, ...)   <- being built now
  NAND                   <- the one brick everything is made of
```

The destination is the **Cockpit**, a screen where you can watch a Pebble program run
on this computer, pause at any moment, and zoom all the way down to individual gates.
The Cockpit is not built yet. Right now the project is the scaffold and the story.

## Quick start

You need Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
uv run pytest
uv run mkdocs serve   # read the docs at http://127.0.0.1:8000
```

## Read the docs

Start with [`docs/index.md`](docs/index.md) ("What Is a Computer, Really?"), then
[`docs/from-scratch.md`](docs/from-scratch.md) ("Why Build a Computer From Nothing?").
The docs are the heart of the project; the code exists to back them up.

## License

MIT, see [LICENSE](LICENSE).
