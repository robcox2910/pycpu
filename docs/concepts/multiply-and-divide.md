# Multiply and Divide

## Long Multiplication on Paper

Remember learning to multiply big numbers on paper? You write one number on top of the
other, and for each digit of the bottom number you write a row: the top number times that
digit, shifted one place further left each time. Then you add up the rows. It is slow
and neat, and it works.

Now do it in **binary** (counting with only 0 and 1, from [Bits and Binary](bits-and-binary.md)).
Every digit of the bottom number is either 0 or 1, so every row is either *nothing* or
*the top number, shifted*. There is no times-table to remember at all: just "shift" and
"add". That is how our computer multiplies, even though its [instruction set](../reference/instruction-set.md)
has no multiply instruction. It has `shl` (shift left, which slides every bit one place
along and so doubles the number), `shr` (shift right, which halves it) and `add`, and
that is plenty.

Division is long division, also on paper: "how many times does the divisor fit into the
next bit of the number?" In binary the answer is only ever *fits* or *does not fit*. Each
time we ask, we also write down one bit of the answer. The leftover at the end is the
**remainder**: what is left over after sharing out as many whole groups as you can.
Division is the question "how many groups of 3 in 7?": the answer is 2 groups with 1
left over, so 7 divided by 3 is 2 and the remainder is 1.

| Paper maths | In PyCPU |
|-------------|----------|
| Multiplying on paper | The routine `__mul` |
| A row that is "nothing" or "the top number, shifted" | Skip the `add`, or `add r3, r3, r1` |
| Sliding a row one place left | `shl r1, r1` |
| Moving to the next digit of the bottom number | `shr r2, r2` |
| Long division | The routine `__divmod` |
| "Does it fit?" | `cmp r4, r2` then `br ltu, ...` |
| The answer and the leftover | `r1` (the quotient) and `r2` (the remainder) |
| The routines' home | `RUNTIME`, in `src/pycpu/translator/runtime.py` |

## Try It

Here is a tiny program that calls the routines. `RUNTIME` is a block of assembly text
that we paste after our own code. We set up `r1` and `r2`, `call` a routine, and then
read the answers out of the registers. (A **routine** is a little program other code
calls to do a job and come back, from [Calling and Returning](calling-and-returning.md).)

```python
from dataclasses import replace

from pycpu.assembler import assemble
from pycpu.fast import FastMachine
from pycpu.state import program_state
from pycpu.translator import RUNTIME, RUNTIME_STACK_WORDS


def run(routine, a, b):
    """Run one routine on the fast engine; return (r1, r2, instructions taken)."""
    program = assemble(f"call {routine}\nhalt\n{RUNTIME}", words=256)
    state = program_state(program.words, 256)
    registers = list(state.registers)
    registers[1], registers[2] = a & 0xFFFF, b & 0xFFFF
    machine = FastMachine(words=256)
    machine.load_state(replace(state, registers=tuple(registers)))
    steps = machine.run(5000)
    result = machine.state().registers
    return result[1], result[2], steps


def signed(word):
    """Read a 16-bit word as a signed number."""
    return word - 65536 if word >= 32768 else word


print("6 * 7 =", run("__mul", 6, 7)[0])
print("300 * 300 =", run("__mul", 300, 300)[0], "(wrapped to 16 bits)")
quotient, remainder, _ = run("__divmod", 7, 2)
print("7 // 2 =", signed(quotient), "and 7 % 2 =", signed(remainder))
quotient, remainder, _ = run("__divmod", -7, 2)
print("-7 // 2 =", signed(quotient), "and -7 % 2 =", signed(remainder))
print("steps for 6 * 7:", run("__mul", 6, 7)[2])
print("steps for 60000 * 60000:", run("__mul", 60000, 60000)[2])
print("stack words the routines need:", RUNTIME_STACK_WORDS)
# Output:
# 6 * 7 = 42
# 300 * 300 = 24464 (wrapped to 16 bits)
# 7 // 2 = 3 and 7 % 2 = 1
# -7 // 2 = -4 and -7 % 2 = 1
# steps for 6 * 7: 32
# steps for 60000 * 60000: 127
# stack words the routines need: 3
```

Some things to notice. `300 * 300` is really 90000, but a register only holds 16 bits
(up to 65535), so the answer **wraps around**: 90000 minus 65536 is 24464. The computer
does this on purpose, and [Negative Numbers](negative-numbers.md) explains why a
wrapped answer is still useful. The step counts include the `call` and the `halt`
around the routine. And `-7 // 2` is `-4`, not `-3`: more on that below.

## How It Works

Everything here lives in `src/pycpu/translator/runtime.py`, as one long piece of
assembly text called `RUNTIME`. Every label in it starts with two underscores
(`__mul`, `__divmod_loop`), so it can never be confused with a label somebody else
writes. The rules for using a routine are the same for both: the two inputs go in
`r1` and `r2`, you `call` it, and the answer comes back in `r1` (`__divmod` also
answers in `r2`). The routines never touch `r0` (always 0) or `r7` (a register kept for the
**translator**, the part coming later in this section that turns a Pebble program into
instructions like these, which uses it to find its place on the stack), but they use `r1` to `r6` freely.

### Multiplying: shift and add

Take 6 times 7. In binary, 7 is `111` and 6 is `110`. Look at the bottom number's bits
from the right. Each `1` means "add a row"; each row is the top number, shifted one place
further left than the row before:

```
        110      <- 6 (the top number)
      x 111      <- 7 (the bottom number)
      -----
        110      bit 0 is 1: add 6        =  6
       1100      bit 1 is 1: add 6 shifted = 12
      11000      bit 2 is 1: add 6 shifted again = 24
      -----
     101010      = 42
```

`__mul` does exactly this with a loop. `r3` is the running total, starting at 0. Each time
round: if `r2` is all zeros, stop. Otherwise look at the lowest bit of `r2` (`and` with
`r4`, which holds 1); if it is 1, `add r3, r3, r1`. Then `shl r1, r1` slides the top number
left for the next row, and `shr r2, r2` throws away the bit we just used. Because `r2` is 16
bits wide, it is empty after at most 16 rounds, which is why even `60000 * 60000` finishes
in 127 steps in the Try It. Bits shifted off the left end of `r1` are simply lost. That is
exactly the "wrap around" above, and it is why the answer is right *modulo 65536* (the
answer you get after throwing away everything from 65536 upwards).

### Dividing: does it fit?

Long division in binary brings the top number's bits down one at a time into a
"leftover", and after each one asks one question: does the divisor fit into the leftover?

Here it is for 7 divided by 3 (`111` divided by `11`):

```
   bring down   leftover   divisor 3 fits?   leftover after   answer so far
   1            1          no                1                0
   1            11 (3)     yes               0                01
   1            1          no                1                010
```

Read the answer bits top to bottom: `010` is 2, with a leftover of 1. So 7 divided by 3
is 2 remainder 1. `__divmod` does this 16 times, one for each bit of the number
(`r6` counts down from 16). It slides the top bit of `r1` out with `shl r1, r1`: the bit
lands in the **carry flag** (a little lamp the CPU keeps that remembers the bit that fell
off the end, from [The ALU](the-alu.md)), and `br ltu` ("lower than, unsigned": **unsigned** means we read the bits as a plain
number with no minus sign), which
looks at that lamp, tells us whether it was 0 or 1. Then `cmp r4, r2` asks "does it fit?"
and a second `br ltu` skips the subtraction when the leftover is smaller. In the first
round above you can see the shape: `r4` is the leftover, `r5` the answer bits.

### Negative numbers: rounding down

The routine does the sum on the *sizes* of the numbers first, then fixes the signs, so
the loop never has to think about minus signs. The signs need a decision, because
Pebble's `//` is **floor division**: it always rounds *down*, toward the left on the
number line, never toward zero.

```
   -5     -4     -3     -2     -1      0      1      2
 ---+------+------+------+------+------+------+------+---
           ^  ^
          -4 -3.5   <- -7 / 2 sits here, halfway; "down" is to the left
```

`-7 / 2` is `-3.5`. Rounding *down* from `-3.5` lands on `-4`, so `-7 // 2` is `-4`. The
remainder is whatever makes the sum work: `-7 = 2 * -4 + 1`, so `-7 % 2` is `1`. A
remainder from floor division has the same sign as the divisor (`7 % -2` is `-1`).

The cheap way to get this: first do the sum on the sizes, as if both were positive, then
patch the signs. If the signs of the two numbers are the same, the answer is already right
(`-7 // -2` is `3` because 7 // 2 is 3). If they differ, the exact answer is negative; we
negate the quotient (**negate** means flip its sign, so 5 becomes -5; this is rounding toward zero), and if there was a leftover we step
one further down (`addi r5, -1`) and move the remainder across by adding the divisor
(`add r4, r4, r2`). The routine uses `push` and `pop` to keep the original numbers while
the loop uses up `r1` and `r2`. `RUNTIME_STACK_WORDS` is the deepest the routines reach
into the stack: 1 word for the return address that `call` pushes, plus the 2 pushes
in `__divmod`, so 3. A test steps the real machine and checks that figure. One odd
corner: `-32768 // -1` should be `32768`, which does not fit in 16 bits, so it wraps
to `-32768`. The machine never divides by zero here: whoever calls `__divmod` checks for
zero first.

## Why Does This Matter?

A multiply instruction needs a big circuit of its own, and the first microprocessors
did not have one. Their programs multiplied exactly the way `__mul` does, with loops of
shifts and adds, and the same trick is still inside every chip that has to multiply
fast: a hardware multiplier is shift-and-add built out of gates, with the rows added
up side by side instead of one after another. So building it in assembly shows what is really going on inside a `*`.

It also means everything bigger can be built from a very small kit. A computer that can
add, shift, compare and jump can do any arithmetic at all, only more slowly. That is the
idea behind the [calling convention](calling-and-returning.md) too: write a recipe once,
call it from everywhere. The next steps will use these two routines whenever a Pebble
program writes `*`, `//` or `%`.

## What's Next

You have seen the machine build multiplying and dividing out of nothing but shifts, adds
and comparisons. Next, do all of this with buttons, and watch the whole running computer,
on [The Bench](the-bench.md).
