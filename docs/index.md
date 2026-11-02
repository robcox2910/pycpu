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

## The Ladder

Each layer is built only from the layer beneath it. The bottom rungs are where this
project starts. The higher ones are the plan for the climb, and they do not exist yet.

```
  ┌──────────────────────────────────────────────────────┐
  │  The Cockpit      watch a program run, zoom to gates │  coming later in the climb
  ├──────────────────────────────────────────────────────┤
  │  Pebble           a small language, compiled to      │  coming later in the climb
  │                   machine code                       │
  ├──────────────────────────────────────────────────────┤
  │  The assembler    readable text -> machine code      │  coming later in the climb
  ├──────────────────────────────────────────────────────┤
  │  The CPU          follows a list of instructions     │  coming later in the climb
  ├──────────────────────────────────────────────────────┤
  │  Memory           latches, registers, RAM            │  next up in the climb
  ├──────────────────────────────────────────────────────┤
  │  Arithmetic       adders and the ALU                 │  next up in the climb
  ├──────────────────────────────────────────────────────┤
  │  Gates            NOT, AND, OR, XOR                  │  next up in the climb
  ├──────────────────────────────────────────────────────┤
  │  NAND             the one brick                      │  where it all starts
  └──────────────────────────────────────────────────────┘
```

Read it from the bottom up. NAND makes the other gates. Gates make adders. Adders
make the ALU, the part of a computer that does sums. Gates also make memory. Put an
ALU, memory and some control together and you have a CPU. Teach the CPU to read
instructions, and you can run programs written in **Pebble**, the little language from
the same series of projects.

## Where We Are Today

Honesty first: right now this repository holds the foundations and the story, not the
machine. The pages you are reading explain what we are going to build and why. As each
rung of the ladder gets built, a new page appears for it, and each page does three
things: it explains the idea with an everyday comparison, it lets you run real code to
see it for yourself, and it shows you how the part is built from the one below.

## By the End of the Climb

When all of it is built, you will be able to:

- explain what a bit is, and count in binary
- say how a handful of NAND gates can add two numbers
- see how a loop of gates can *remember* something
- follow a program from a line of Pebble down to the individual gates that run it

## The Destination: The Cockpit

The prize at the top is a screen called the **Cockpit**. On one screen you will see
your Pebble program, the machine code it turned into, the registers and memory, and
the instruction that is running right now. You will be able to **pause at any moment**
and click down through the layers (the ALU, the adder, a single bit, a single gate)
and see the real circuit, with real wires carrying real values.

The Cockpit does not exist yet. It is where the climb is heading.

## Start Here

Head to [Why Build a Computer From Nothing?](from-scratch.md) to see the promises this
project makes, and how it fits with the rest of the series.
