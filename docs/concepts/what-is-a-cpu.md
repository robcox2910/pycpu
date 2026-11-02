# What Is a CPU?

## A Cook and a Stack of Recipe Cards

Picture a cook in a kitchen. On the wall is a stack of recipe cards, numbered
1, 2, 3 and so on, and each card holds exactly one small order: "crack two eggs
into the blue bowl", "add the flour to the blue bowl", "if the bowl is empty, go
back to card 2". The cook does not understand cooking in general. All the cook
can do is this: put a finger on a card, read it, obey it, and move the finger to
the next card. Then again. And again. Out of that one dull habit, a whole dinner
appears.

A **CPU** (central processing unit) is that cook. The recipe cards are
**instructions**: tiny orders, each one a single number, stored in memory. The
whole stack of cards is a **program**. The cook's finger on the current card is
the **program counter**, or **PC**: a number that says which instruction comes
next. And the bowls on the counter, where the cook keeps what is being worked on
right now, are **registers**: a few quick, small stores that hold one number each.
Registers are the sticky notes from [Registers](registers.md); the cards sit in the
[RAM](ram.md); the sums are done by the [ALU](the-alu.md). So a CPU is not a new
kind of magic. It is the parts we already built, plus one habit.

| In the kitchen | In PyCPU |
|----------------|----------|
| The stack of recipe cards | Memory: `memory`, 4,096 words (see [RAM](ram.md)) |
| One recipe card | One **instruction**: a single 16-bit word |
| The cook's finger on the current card | The **program counter**: `pc` |
| The bowls on the counter | The **registers** `r0` to `r7`, 16 bits each |
| A spare bowl for the stack of plates (a later page) | The stack pointer: `sp` |
| The cook doing the sums | The ALU, [from the ALU page](the-alu.md) |
| "Stop, dinner is ready" | The `HALT` instruction |
| Watching the cook, step by step | `FastMachine.step()` in `src/pycpu/fast.py` |

## Try It

Here is a four-card program, written as raw numbers. We will explain what the
numbers mean on the next page. For now, trust us that it says: put 3 in
register `r1`; take 1 away from `r1`; if `r1` is not yet zero, go back one card;
stop. It is a countdown. We run it one step at a time and watch the finger (`pc`)
and one bowl (`r1`).

```python
from pycpu.fast import FastMachine

program = [0x2203, 0xE2FF, 0x83FE, 0xF000]

machine = FastMachine(words=64)
machine.load_program(program)

state = machine.state()
print(f"start: pc={state.pc} r1={state.registers[1]}")
while not machine.state().halted:
    machine.step()
    state = machine.state()
    print(f"step:  pc={state.pc} r1={state.registers[1]}")
print("halted:", state.halted)
# Output:
# start: pc=0 r1=0
# step:  pc=1 r1=3
# step:  pc=2 r1=2
# step:  pc=1 r1=2
# step:  pc=2 r1=1
# step:  pc=1 r1=1
# step:  pc=2 r1=0
# step:  pc=3 r1=0
# step:  pc=4 r1=0
# halted: True
```

Watch the finger. It goes 1, 2, then jumps *back* to 1, because the third card
sent it back. It loops until `r1` hits 0, and then it falls through to the last
card and stops. A loop is nothing more than a card that moves the finger
backwards. (`FastMachine(words=64)` is a small computer with 64 words of memory,
so that this page runs in a blink.)

## How It Works

Everything a CPU does is one cycle, round and round:

```
        ┌──────────────────────────────────────────────┐
        │                                              │
        ▼                                              │
  1. FETCH            2. EXECUTE                       │
  read the card       obey it: change a register,      │
  the finger is on;   or memory, or move the finger;   │
  move the finger     the ALU does any sums            │
  to the next card ──────────────────────────────────►─┘
```

1. **Fetch.** Look at the word in memory at the address in `pc`. Then add 1 to
   `pc`, so the finger already points at the *next* card. (That detail matters
   later: it is why a jump counts from the next card, not this one.)
2. **Execute.** Work out what the card says and do it. Most cards change a
   register. Some read or write memory. Some change `pc` itself, which is how
   loops and jumps happen. The sums go through the ALU.
3. Go back to step 1, until a `HALT` card stops the machine.

Here is the whole computer, with the parts named as they are in the code:

```
   ┌──────────────── the CPU ────────────────┐       ┌───── memory ─────┐
   │  pc   ← which card is next              │       │ 0:  0x2203       │
   │  sp   ← the stack (a later page)        │ ◄───► │ 1:  0xE2FF       │
   │  r0 r1 r2 r3 r4 r5 r6 r7  ← the bowls   │       │ 2:  0x83FE       │
   │  flags ← four lamps about the last sum  │       │ 3:  0xF000       │
   │  ALU   ← does the sums                  │       │ ...  4,096 words │
   └─────────────────────────────────────────┘       └──────────────────┘
```

Every part of that picture is something you have already met. Each register is a
[`Register`](registers.md) (`src/pycpu/memory.py`): sixteen sticky notes that all
update on the clock beat. The program counter is one such register fed by an
adder that adds 1, the same counter as on the Registers page. Memory is the
[`Ram`](ram.md). The ALU is the one in `src/pycpu/arithmetic.py`.

The values that make up the computer at one moment, which are `pc`, `sp`, the
registers, the flags, the whole memory and whether it has halted, are collected in one
frozen record, `MachineState`, in `src/pycpu/state.py`. `power_on` makes the
state a computer has when you switch it on: everything 0, except that `sp` starts
at the end of memory, for reasons that the stack page explains.

**Two ways to build the same cook.** The `FastMachine` you ran above lives in
`src/pycpu/fast.py` and is ordinary Python: it follows the cards with plain
`if` statements and whole numbers, which makes it quick. It is not made of gates.
That is deliberate. Later in the climb we build the same CPU out of real gates,
the way this whole project works, and then prove that the two always agree. The
fast one is the answer key; the gate one is the real thing. They share one
definition of the instructions, in `src/pycpu/isa.py`, so they cannot disagree
about what a card means.

## Why Does This Matter?

Without a CPU, a pile of adders and memory is a pile of parts: it can add two
numbers if you place them just so, and then it sits there. The CPU's habit of
fetching and obeying turns those parts into something you can *program*. Change
the cards and the very same machine plays music, draws a game or checks your
spelling, without changing a single gate. That is why one phone can be a camera,
a map and a calculator.

It is also real. Your laptop's processor does the same two-beat cycle,
billions of times a second. It has more registers, longer words and many tricks to
go faster, but under all the tricks it is still a cook with a finger on a card.

## What's Next

We said the numbers `0x2203` and `0xE2FF` were orders, but how can a number be
an order? Read [Machine Code](machine-code.md) to see how 16 bits are cut up into
a command and its details.
