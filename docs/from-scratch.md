# Why Build a Computer From Nothing?

## Making Bread From Wheat

You can buy bread at a shop and never think about it. But if you have ever grown
wheat, ground it into flour, mixed the dough and baked it yourself, you understand
bread in a way that shopping can never teach you. Nothing about it is magic any more.

Computers are usually shop-bought bread. You press a key and a letter appears, and the
bit in the middle is a mystery. PyCPU is the wheat-to-bread version: we build the
computer ourselves, one layer at a time, so that nothing inside it is a mystery.

## What "From Scratch" Means Here

Two ideas, and we keep both strictly.

**1. No hidden magic.** Every layer is made only from the layer directly below it. An
adder is made of gates. Memory is made of gates. When you read about a part, you can
always ask "what is this made of?" and get a real answer, all the way down.

**2. Everything is made of NAND.** There is a single building brick, the NAND gate
(see the [home page](index.md) for its one rule). Every other gate is a little pattern
of NANDs. Nothing higher up is allowed to sneak in its own shortcut for a logic
decision.

| Everyday idea | In PyCPU |
|---------------|----------|
| The wheat | The NAND gate, the one raw ingredient |
| Flour and dough | Other gates (NOT, AND, OR, XOR), made from NAND |
| A loaf | Adders, then the ALU, memory, the CPU |
| Baking it yourself | Every layer built only from the one below |

## Why Simulate Instead of Solder?

We could buy a bag of chips and a soldering iron, and people do, happily. But a
simulation has gifts that a pile of wire does not:

- **You can pause time.** A real circuit runs very fast. A simulated
  one can stop, and you can look at every wire.
- **You can look inside.** You never need a microscope. Any part can be opened up and
  shown, and a mistake costs nothing.
- **It is free and safe.** No burnt fingers, no tiny parts to lose in the carpet.
- **It fits in a text editor.** A circuit is just data, so you can read it, change it
  and test it like any other Python.

The trade-off is that Python is only *pretending* to be electricity. We do not claim
this is how real chips are made. We claim it is a faithful picture of **how they
think**: the same gates, wired in the same patterns, giving the same answers.

## A Thank You to *Code*

The idea of climbing from a single switch to a working computer comes from Charles
Petzold's book *Code: The Hidden Language of Computer Hardware and Software*. It walks
from flashlights and telegraph relays up to a processor, with nothing skipped. PyCPU
follows the same spirit in Python, with code you can run at every step. If you enjoy
these pages, read the book.

## The "No Faking" Promise

Here is the promise this project cares about most.

> When you look at a circuit, it must be **the real circuit**, computing **the real
> value**. Never a drawing of gates while the real work happens somewhere else.

It would be easy to cheat: show a lovely picture of an adder while Python quietly adds
the numbers with `+`. That would make the project a lie about the very thing it is
trying to teach. So faking is not allowed. Whatever the screen shows, the
gates underneath are really doing the work.

There is an honest limit, too. A computer's memory holds a lot of bits, and a
simulation of every one of them takes real effort. If we find we cannot afford all the
memory we hoped for, we will **make the memory smaller**. We will never swap in a
cheat and pretend.

## Build, Then Watch

PyCPU is about building. [Build It Yourself](build-it-yourself.md) gives the order to build
each part in code, from one NAND gate up to a computer that runs a Pebble program. The
Cockpit comes second. It is where you watch what you built run, pause it, and zoom down
to the gates. Each part view in it has a "The code that built this" panel, which shows the
real code that made the circuit you are looking at, never a copy
([The Code Behind a Part](concepts/the-code-behind-a-part.md)). Build first, then watch.

## Where PyCPU Fits in the Series

This site belongs to a collection of "from scratch in Python" projects. Most of them
sit *on top* of a computer, and PyCPU is the one that sits underneath.

| Project | What it builds | How it relates |
|---------|----------------|----------------|
| [Pebble](https://robcox2910.github.io/pebble-lang/) | A small programming language | Part of Pebble now runs on the PyCPU computer, translated into its machine code |
| [PyOS](https://robcox2910.github.io/py-os/) | An operating system | Software that runs on a computer like this one |
| [PyWeb](https://robcox2910.github.io/pyweb/) | A web server | Serves the Cockpit, and sends it live updates while a program plays |
| [The series home](https://robcox2910.github.io/) | All of them | Where to find the rest |

Pebble, PyOS and the others all quietly assume a computer exists. PyCPU is the project
that asks: what if we built that computer too?

## How to Read These Docs

1. **Go in order.** Each page builds only on the pages before it, and any new word is
   explained the first time it appears.
2. **Run the examples.** Pages that have code give you a complete example you can copy
   and paste. Run it, change a number, and see what happens. Learning by poking is
   the point.
3. **Look for "How It Works".** That section shows how the part is built from the layer
   below, which is the whole "from scratch" idea.
4. **Trust the numbers.** Any figure in these docs was measured by running the code,
   never invented.

One more honest note. Four climbs are built. The first runs from a single gate up to
adders, a calculator part called the ALU, and memory that remembers. The second builds
a processor from those parts, an assembler to write programs for it, a fast engine
that is checked against the gates, and the Cockpit, where you can pause a running
program and look inside it down to a single gate. The third translates Pebble programs
into machine code for that processor, so they run on it and print the same answers
as Pebble's own way of running them, for numbers that fit in 16 bits. Only part of
Pebble runs so far (whole numbers, variables, `if`, `while`, `for` over a range, functions and `print`),
and anything else gets a friendly "not supported yet" message. The fourth climb
finishes the Cockpit: one screen with the Pebble program on the left and a magnifying
glass on the right, one Step button that moves by a Pebble line, an instruction, a part
or a gate, and a pause that drops you into the gates at any moment.
`uv run python -m pycpu` opens it on guided walks, and
[A Tour of the Cockpit](concepts/a-tour-of-the-cockpit.md) follows one Pebble line down
to a single gate. One climb is left: fitting PyCPU into PyStack, the project that joins
the whole series together, and the first release.

Ready? Go back to the [home page](index.md) to see the whole ladder again, or start
climbing with [Bits and Binary](concepts/bits-and-binary.md).

And when you have climbed all the way, [You Built a Computer](you-built-a-computer.md)
looks back down the tower.
