# What Is a Computer, Really?

## A Giant Machine Made of Tiny Switches

Imagine you want to build a castle out of Lego. You do not need a special brick for
the towers, another for the gate and another for the drawbridge. You just need lots
and lots of the same little bricks, snapped together in the right pattern. Tiny bricks
make small shapes, small shapes make bigger parts, and bigger parts make a castle.

A computer is exactly like that. Underneath the games, the websites and the programs,
there is nothing but a huge number of tiny **switches**, each one either **on** or
**off**. Wire a few switches together the right way and you get a part that can make a
simple decision. Wire a few of *those* together and you get a part that can add two
numbers. Keep going and you get memory that remembers, and finally a processor that
follows a list of instructions.

PyCPU builds a computer this way, from the very bottom, using Python to pretend to be
the electricity. We use only **one** kind of brick, and it is a very small one.

## The One Brick: NAND

The brick is called a **NAND gate**. It has two inputs and one output, and it follows
one rule:

> The output is **on**, unless **both** inputs are on.

| Input A | Input B | Output |
|---------|---------|--------|
| off | off | **on** |
| off | on | **on** |
| on | off | **on** |
| on | on | off |

That is the whole rule. It looks far too simple to build a computer from, and the
surprise at the heart of this project is that it is not. Every other kind of gate, and
so everything above it, can be made by wiring NAND gates together.

## Walking Up the Ladder

Here is the climb in plain English, from the bottom rung to the top. Each new word is
explained the first time it appears.

1. **NAND**, the one brick, a switch with the rule above.
2. **Gates.** A gate is any small part that turns switches into a decision. With NANDs
   you can build gates with names like NOT, AND, OR and XOR.
3. **Arithmetic.** Gates can be arranged into an **adder**, a part that adds two numbers
   written in **binary**, which is counting using only on and off. A single on-or-off
   switch is called a **bit**. Many adders together make the **ALU**, the part of a
   computer that does all the sums.
4. **Memory.** Gates wired in a loop can hold on to a bit, like a switch that stays where
   you leave it; that is a **latch**. A row of them makes a **register**, a tiny
   scratchpad. Thousands of them make **RAM**, the big notebook where a computer keeps
   what it is working on.
5. **The CPU**, the **processor**: the part that follows a list of instructions, using
   the ALU to do sums and registers and RAM to remember things.
6. **The assembler**, which turns instructions written in readable words into **machine
   code**, the plain numbers the processor actually obeys.
7. **Pebble**, a small programming language that already exists in the same series. Pebble
   programs get **compiled**, which means translated, into PyCPU machine code.
8. **The Cockpit**, the screen where you watch it all run.

Here it is as a picture. Read it from the bottom up.

```
  ┌──────────────────────────────────────────────────────┐
  │  The Cockpit      watch a program run, zoom to gates │  coming later in the climb
  ├──────────────────────────────────────────────────────┤
  │  Pebble           programs, translated to numbers    │  partly built: simple programs run
  ├──────────────────────────────────────────────────────┤
  │  The assembler    readable words -> numbers          │  built and working
  ├──────────────────────────────────────────────────────┤
  │  The CPU          follows a list of instructions     │  built and working
  ├──────────────────────────────────────────────────────┤
  │  Memory           latches, registers, RAM            │  built and working
  ├──────────────────────────────────────────────────────┤
  │  Arithmetic       adders and the ALU                 │  built and working
  ├──────────────────────────────────────────────────────┤
  │  Gates            NOT, AND, OR, XOR                  │  built and working
  ├──────────────────────────────────────────────────────┤
  │  NAND             the one brick                      │  built, where it all starts
  └──────────────────────────────────────────────────────┘
```

Each layer is built only from the layer beneath it. Everything from NAND up to the
CPU and the assembler now exists and works. Pebble has started to arrive: simple Pebble
programs with variables, sums and `print` already run on PyCPU, and the rest of Pebble and
the Cockpit are still to come; those are the rungs marked "coming later" and "partly built".

## Where We Are Today

The bottom six rungs are built. Gates, adders, the ALU, registers and a 4,096-word RAM
are all made of real NAND gates, and on top of them sits a whole **CPU**, also made of
NAND gates, that fetches instructions from memory and obeys them, one after another. You can write programs for it in **assembly language** (short
words such as `add` and `store`), and the assembler turns them into the numbers the CPU obeys.

Running a program on gates is slow, so there is also a **fast engine** that follows
the same rules with ordinary Python arithmetic, and the tests check after every
instruction that the two always agree. A program runs fast, and you can **pause** it,
which carries the whole machine over to the gates, so you can step through an
instruction one gate at a time and **rewind** it to watch again.

You can do all of that on **the Bench**, a page on your own computer: it shows the
registers, the memory with the current instruction marked, and buttons to step by a
gate, a clock beat or an instruction, and to rewind and run. Its zoom panel goes from
the whole CPU down to a single gate, with the real 0s and 1s on its wires. Start it
with `uv run python -m pycpu`, or read [The Bench](concepts/the-bench.md). Simple Pebble
programs already run on PyCPU (see
[From Pebble to Machine Code](concepts/from-pebble-to-machine-code.md)); the rest of
Pebble and the full Cockpit come next.

## By the End of the Climb

When all of it is built, you will be able to:

- explain what a bit is, and count in binary (counting with only on and off)
- say how a handful of NAND gates can add two numbers
- see how a loop of gates can *remember* something
- follow a program from a line of Pebble down to the individual gates that run it

## The Destination: The Cockpit

The prize at the top is a screen called the **Cockpit**. On one screen you will see
your Pebble program, the machine code it turned into, the registers (scratchpads) and memory, and
the instruction that is running right now. You will be able to **pause at any moment**
and click down through the layers (the ALU, the adder, a single bit, a single gate)
and see the real circuit, with real wires carrying real values.

The full Cockpit does not exist yet, but a good part of it does: the Bench already shows
the registers, the memory and the running instruction, and zooms down to the gates.
What it cannot show yet is a Pebble program, because the Bench cannot load one yet.
That is where the climb is heading.

## Start Here

Head to [Why Build a Computer From Nothing?](from-scratch.md) to see the promises this
project makes, and how it fits with the rest of the series.
