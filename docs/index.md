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

You build it yourself, in code. [Build It Yourself](build-it-yourself.md) is the
instruction sheet: the order to write the parts, from one NAND gate up to a computer that
runs a Pebble program, with a picture to check each step. Once you have built something,
you open the **Cockpit** to check it and watch it run.

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
7. **Pebble**, a small programming language that already exists in the same series. Pebble's
   own **compiler** (a translating program) turns a Pebble program into simple steps, and
   PyCPU's **translator** turns those steps into PyCPU machine code.

Beside the ladder sits **the Cockpit**, the screen where you check and watch what you
built, at any rung.

Here it is as a picture. Read it from the bottom up.

```
  ┌──────────────────────────────────────────────────────┐
  │  Pebble           programs, translated to numbers    │  built for part of Pebble
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

  The Cockpit sits beside the ladder: use it to watch any rung.
```

Each layer is built only from the layer beneath it. Everything from NAND up to the
CPU and the assembler exists and works, and Pebble programs now run on top of it: whole
numbers, variables, `if`, `while`, `for` over a range, functions (even ones that call
themselves) and `print`. That is only part of Pebble. Decimal numbers, lists, text kept in
variables and the rest are refused with a friendly message naming the line, so that rung
says "built for part of Pebble". The Cockpit is built too.

## Where We Are Today

All seven rungs are built, the seventh only for part of Pebble, and the Cockpit beside
them is built too. Gates, adders, the ALU, registers and a 4,096-word RAM are all made
of real NAND gates, and on top of them sits a whole **CPU**, also made of NAND gates,
that fetches instructions from memory and obeys them, one after another. You can write
programs for it in **assembly language** (short words such as `add` and `store`), and
the assembler turns them into the numbers the CPU obeys.

Running a program on gates is slow, so there is also a **fast engine** that follows
the same rules with ordinary Python arithmetic, and the tests check after every
instruction that the two always agree. A program runs fast, and you can **pause** it,
which carries the whole machine over to the gates, so you can step through an
instruction one gate at a time and **rewind** it to watch again.

You can do all of that on **the Cockpit**, a page on your own computer. Start it with
`uv run python -m pycpu`: it opens on **guided walks**, short tours that show you one
idea at a time on the real machine and end with a small task for you to try. The Pebble
program is on the left, with the running line marked, and a **magnifying glass** is on the
right. One **Step** button moves by as much as the glass is looking at: a whole Pebble
line, one instruction, one part of the CPU, or one gate, with the real 0s and 1s on its
wires. A sentence says what just happened, and you can rewind, run, or **play** the
program on its own while the screen updates live, and **pause** it at any moment. The
Expert drawer holds every exact control. Read [The Cockpit](concepts/the-cockpit.md), or take
[A Tour of the Cockpit](concepts/a-tour-of-the-cockpit.md), which follows one Pebble
line all the way down to a single NAND gate.

And you can write programs in **Pebble**. The section "Pebble on the CPU", starting at
[From Pebble to Machine Code](concepts/from-pebble-to-machine-code.md), shows how each
piece of a Pebble program becomes machine code: variables become places in memory,
`if` and `while` become jumps, a function call builds a **frame** (its own patch of
memory) on the stack, and multiplying, dividing and printing are small routines written
in assembly, because the CPU itself can only add, shift and compare. When a program goes
wrong, for example by dividing by zero, PyCPU stops and names the Pebble line to blame.
Load a Pebble program on the Cockpit and it shows the line that is running, next to the
machine code.

One last climb is left: putting PyCPU into **PyStack**, the series'
project that joins all the others together, and then the first release, so other
projects can use it.

## By the End of the Climb

By the end of the climb, you will be able to:

- explain what a bit is, and count in binary (counting with only on and off)
- say how a handful of NAND gates can add two numbers
- see how a loop of gates can *remember* something
- follow a program from a line of Pebble down to the individual gates that run it

## Check and Watch: The Cockpit

Once you have built a part, a screen called the **Cockpit** lets you check it and watch it
work. Each part view in the Cockpit has a "The code that built this" panel, so the gates
you see are tied to the code you wrote
([The Code Behind a Part](concepts/the-code-behind-a-part.md)). On one screen you see
your Pebble program, the machine code it turned into, the registers (scratchpads) and
memory, and the instruction that is running right now. You can **pause at any moment**
and click down through the layers (the ALU, the adder, a single bit, a single gate)
and see the real circuit, with real wires carrying real values.

That screen is built. `uv run python -m pycpu` opens it on guided walks, and
[A Tour of the Cockpit](concepts/a-tour-of-the-cockpit.md) shows the whole journey, from
one Pebble line to one gate. The climb has reached the top.

## Start Here

Head to [Why Build a Computer From Nothing?](from-scratch.md) to see the promises this
project makes, and how it fits with the rest of the series.

When you have climbed it all, [You Built a Computer](you-built-a-computer.md) shows every
layer of the tower in one table.
