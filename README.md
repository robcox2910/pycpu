# PyCPU

An educational computer, built from nothing but NAND gates, in Python.

Have you ever wondered what a computer *actually is*, underneath the apps and the
screen? PyCPU is a project that answers that question by building one, from the
very bottom. Everything starts with a single tiny part, the **NAND gate**: a switch
that only turns on when its two inputs are *not both on*. It sounds far too simple to
matter. But if you wire enough NAND gates together you can make every other gate (a gate is
a small part that turns switches into a decision), then adders that do sums, then memory
that remembers, and eventually a whole processor (the part of a computer that follows
instructions).

You build it yourself, in code. [Build It Yourself](docs/build-it-yourself.md) is the
instruction sheet: the order to write the parts, from one NAND gate up to a computer that
runs a Pebble program, with a picture to check each step. Then you open the **Cockpit** to
check and watch what you built.

Part of the "from scratch in Python" series. Each layer is made only from the one
below it, so nothing is hidden, and nothing is faked: when a page shows you a circuit,
that is the real circuit, doing the real work.

## The ladder

Each rung is built only from the rung beneath it. An ALU is the part that does the
sums, RAM is the computer's big notebook, the CPU is the processor that follows instructions,
and the Assembler turns readable instructions into the numbers the CPU understands. The docs explain every word.

```
  Pebble programs           <- built for part of Pebble
  Assembler                 <- built
  The CPU                   <- built
  Memory (RAM)              <- built
  Arithmetic (adders, ALU)  <- built
  Gates (AND, OR, ...)      <- built
  NAND                      <- built, where it all starts

  The Cockpit, beside the ladder, not on top of it: watch any rung in the Cockpit
```

The Cockpit comes second, as the place to check and watch what you built. It is a screen where you can watch a program written in
Pebble (a small programming language from the same series) run on this computer, pause at any moment, and zoom all the way down to individual gates.
The Cockpit is built: a local page (`uv run python -m pycpu`) that opens on **guided
walks**, short tours of the real machine that end with a small task for you. It shows the
Pebble program on the left and a magnifying glass on the right. One Step button moves by a
whole Pebble line, an instruction, a part of the CPU or a single gate, a sentence says
what just happened, and you can rewind, run, or play the program while the page updates
live, then pause and look from the CPU down to a single gate. The Expert drawer keeps
every exact control. Pebble programs run on PyCPU: whole numbers, variables, `if`,
`while`, `for` over a range, functions and `print`, translated into machine code, with
multiplying, dividing and printing done by small assembly routines. The rest of Pebble
(decimals, lists, text in variables, ...) is refused with a friendly message. What is
left comes next: PyCPU in PyStack (the series' project that joins the others together),
and the first release.

## Features

- **A gate simulator** -- NAND is the only building block, and every wire's value is real
- **Logic gates** -- NOT, AND, OR, XOR and friends, each built from NANDs
- **Choosing and decoding** -- pick one of two values, or light one of many lines
- **Arithmetic** -- half and full adders, a 16-bit adder, negative numbers
- **The ALU** -- add, subtract, AND, OR, XOR and shifts, with zero, negative, carry and overflow flags
- **Memory** -- latches, flip-flops, a two-beat clock, registers, and 4,096 words of RAM
- **Zoom** -- every part is named, so you can open any circuit and see the gates inside
- **An instruction set** -- 16 opcodes, every instruction one 16-bit word, with flags, a stack and fault halts
- **The CPU** -- built from NAND gates and wired to the RAM, fetching and executing one clock beat at a time
- **An assembler** -- readable assembly in, machine code out, with labels and friendly line-numbered errors
- **Two engines** -- a fast engine in plain Python, checked in lockstep against the gates
- **Pause and rewind** -- run fast, pause into the gates, step by a gate, a beat or an instruction, rewind, resume
- **Pebble on the CPU** -- a translator from Pebble's compiled programs to PyCPU assembly, with frames, jumps, calls, fault lines and a source map
- **The Cockpit** -- a local web page (served by [PyWeb](https://github.com/robcox2910/pyweb)) opening on guided walks, with the Pebble program on the left and a magnifying glass on the right, one Step button at four depths (line, instruction, part, gate), a "what just happened" sentence, live play and pause

## Example

```python
from pycpu.arithmetic import ripple_adder
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

c = Circuit()
a = c.bus_input("a", 16)
b = c.bus_input("b", 16)
total, carry_out = ripple_adder(c, a, b, c.low)

sim = Simulator(c)
sim.set_bus(a, 1234)
sim.set_bus(b, 4321)
sim.settle()
print(sim.get_bus(total))  # 5555, worked out by 240 NAND gates
```

## Quick start

You need Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --all-extras
uv run pytest
uv run python examples/run_assembly.py   # assemble and run a program that prints Hi
uv run python examples/run_pebble.py   # translate a Pebble program and run it: prints 6, 4, 2
uv run python examples/cockpit_tour.py   # follow one Pebble line down to a single gate
uv run python examples/alu_tour.py   # more programs live in examples/
uv run mkdocs serve   # read the docs at http://127.0.0.1:8000
uv run python -m pycpu   # open the Cockpit at http://127.0.0.1:8765
```

## Concepts

Every idea gets its own page, with an everyday analogy:

| Concept | Doc | Analogy |
|---------|-----|---------|
| Bits and binary | [bits-and-binary.md](docs/concepts/bits-and-binary.md) | A light switch |
| Switches and NAND | [switches-and-nand.md](docs/concepts/switches-and-nand.md) | A lamp with two switches |
| Simulating a circuit | [simulating-a-circuit.md](docs/concepts/simulating-a-circuit.md) | Dominoes |
| Logic gates from NAND | [gates.md](docs/concepts/gates.md) | One lamp, many questions |
| Choosing and decoding | [choosing-and-decoding.md](docs/concepts/choosing-and-decoding.md) | Railway points and a hotel panel |
| Looking inside a circuit | [looking-inside.md](docs/concepts/looking-inside.md) | A map you can zoom |
| Adding | [adding.md](docs/concepts/adding.md) | Column addition and carrying the one |
| Negative numbers | [negative-numbers.md](docs/concepts/negative-numbers.md) | A mileage counter that rolls backwards |
| The ALU | [the-alu.md](docs/concepts/the-alu.md) | A kitchen multi-tool with a dial |
| Remembering | [remembering.md](docs/concepts/remembering.md) | Two friends who keep repeating |
| The clock | [the-clock.md](docs/concepts/the-clock.md) | The drummer in a rowing boat |
| Registers | [registers.md](docs/concepts/registers.md) | A row of sticky notes |
| RAM | [ram.md](docs/concepts/ram.md) | A wall of lockers |
| How big is our memory? | [how-big-is-our-memory.md](docs/concepts/how-big-is-our-memory.md) | Lockers and a stopwatch |
| Instruction set (reference) | [instruction-set.md](docs/reference/instruction-set.md) | A lookup table, not a lesson |
| What is a CPU? | [what-is-a-cpu.md](docs/concepts/what-is-a-cpu.md) | A cook and a stack of recipe cards |
| Machine code | [machine-code.md](docs/concepts/machine-code.md) | A secret code card |
| Assembly language | [assembly-language.md](docs/concepts/assembly-language.md) | A recipe, and a helper who translates it |
| The control unit | [the-control-unit.md](docs/concepts/the-control-unit.md) | A railway signal box |
| Fetch, decode, execute | [fetch-decode-execute.md](docs/concepts/fetch-decode-execute.md) | A cook and a drum |
| The stack | [the-stack.md](docs/concepts/the-stack.md) | A pile of plates |
| Calling and returning | [calling-and-returning.md](docs/concepts/calling-and-returning.md) | A bookmark on the pile |
| Two engines | [two-engines.md](docs/concepts/two-engines.md) | A flip-book and a slow-motion camera |
| Pausing and rewinding | [pausing-and-rewinding.md](docs/concepts/pausing-and-rewinding.md) | Pause, replay, back to live |
| From Pebble to machine code | [from-pebble-to-machine-code.md](docs/concepts/from-pebble-to-machine-code.md) | Translating a recipe, card by card |
| Variables in memory | [variables-in-memory.md](docs/concepts/variables-in-memory.md) | Pigeonholes behind the counter |
| Why 16-bit numbers wrap | [why-16-bit-numbers-wrap.md](docs/concepts/why-16-bit-numbers-wrap.md) | The mileage counter again |
| If and while as jumps | [if-and-while-as-jumps.md](docs/concepts/if-and-while-as-jumps.md) | A choose-your-own-adventure book |
| How a function call really works | [how-a-function-call-really-works.md](docs/concepts/how-a-function-call-really-works.md) | Leaving your desk to help a friend |
| Multiply and divide | [multiply-and-divide.md](docs/concepts/multiply-and-divide.md) | Long multiplication on paper |
| Printing a number | [printing-a-number.md](docs/concepts/printing-a-number.md) | A cash register with one slot per letter |
| What happens when things go wrong | [what-happens-when-things-go-wrong.md](docs/concepts/what-happens-when-things-go-wrong.md) | The referee's whistle |
| The Cockpit | [the-cockpit.md](docs/concepts/the-cockpit.md) | An aeroplane cockpit: every dial in view, and a pilot who can freeze the flight |
| Stepping a Pebble line | [stepping-a-pebble-line.md](docs/concepts/stepping-a-pebble-line.md) | Reading aloud with a bookmark |
| Watching it run | [watching-it-run.md](docs/concepts/watching-it-run.md) | Live radio commentary of a match |
| A tour of the Cockpit | [a-tour-of-the-cockpit.md](docs/concepts/a-tour-of-the-cockpit.md) | Following one letter through the post |
| The magnifying glass | [the-magnifying-glass.md](docs/concepts/the-magnifying-glass.md) | A magnifying glass over a map |
| What just happened | [what-just-happened.md](docs/concepts/what-just-happened.md) | A commentator who only says what really happened |
| Build It Yourself | [build-it-yourself.md](docs/build-it-yourself.md) | A model kit with a picture on every bag |
| The code behind a part | [the-code-behind-a-part.md](docs/concepts/the-code-behind-a-part.md) | The recipe printed next to the cake |
| Guided walks | [guided-walks.md](docs/concepts/guided-walks.md) | A museum audio guide |

## Read the docs

Start with [`docs/index.md`](docs/index.md) ("What Is a Computer, Really?"), then
[`docs/from-scratch.md`](docs/from-scratch.md) ("Why Build a Computer From Nothing?").
The docs are the heart of the project; the code exists to back them up.

## Developing alongside a sibling

PyCPU uses PyWeb, Pebble and PyNet from PyPI (`fromscratch-pyweb`,
`fromscratch-pebble` and `fromscratch-pynet`). To work on a sibling
checkout at the same time, install it editable and tell `uv` not to
re-sync over it:

```bash
uv pip install -e ../pyweb
uv run --no-sync pytest
```

## Releasing

PyCPU has no release yet. Its first release, `v0.1.0`, comes when the whole
climb is finished, from gates to Pebble programs running in the Cockpit. From
then on, other projects in the series use a released version of it from PyPI
(`fromscratch-pycpu`), not whatever is on `main`. To publish a change for them:

1. Merge the change to `main`.
2. Release it: `gh release create vX.Y.Z --target main --generate-notes`
   (or push a `vX.Y.Z` tag); the release workflow publishes it to PyPI.
   A change to the public API bumps the minor version (`v0.1.0` → `v0.2.0`);
   anything else bumps the patch (`v0.1.0` → `v0.1.1`).
3. In each project that uses it, raise the `fromscratch-pycpu>=X.Y.Z` floor in
   `pyproject.toml`, run `uv lock --upgrade-package fromscratch-pycpu`, and open
   a pull request so CI checks the pair together.

Docs-only and tooling-only changes do not get a release.

## License

MIT, see [LICENSE](LICENSE).
