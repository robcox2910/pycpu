# Why 16-Bit Numbers Wrap

## The Mileage Counter Again

Back in [Negative Numbers](negative-numbers.md) we met a car's mileage counter: a row of
little wheels, each showing one digit. With five wheels it can show 00000 to 99999, and
one more mile after 99999 rolls every wheel round to 00000. The counter is not broken.
It simply has no sixth wheel to carry the 1 into, so the 1 falls off the end and is
lost. That rolling round is called **wrap**.

Now imagine two drivers comparing trips. One has the five-wheel counter in the car. The
other writes the miles in a notebook, and a notebook never runs out of room for digits.
For short trips they agree perfectly. But after a long trip of 100,003 miles the
notebook says 100003 and the counter says 00003. Both did their sums right; one of them
just had fewer wheels.

That is exactly the difference between Pebble running on its own and Pebble running on
PyCPU. Pebble's own **VM** (its "virtual machine", the program that normally runs Pebble
bytecode, written in Python) is the notebook: its whole numbers can grow as big as you
like. PyCPU is the counter: every register and every word of memory is **16-bit**,
sixteen wires, so it holds only 65,536 different patterns. In two's complement (from
[Negative Numbers](negative-numbers.md)) those patterns mean -32768 up to 32767, and
going past either end wraps round to the other.

| The mileage counter | In PyCPU |
|---------------------|----------|
| Five wheels | 16 bits in a register or a word of memory |
| The biggest reading, 99999 | The biggest number, 32767 (`0x7FFF`) |
| One more mile rolls round to 00000 | 32767 + 1 wraps to -32768 (`0x8000`) |
| The 1 that falls off the end | The carry out of the adder, which nobody keeps |
| The notebook with endless room | Pebble's VM, whose whole numbers never wrap |
| A short trip both agree on | A program whose numbers all stay from -32768 to 32767 |
| A trip so long they disagree | **Overflow**: the true answer did not fit in 16 bits |

## Try It

Each program below runs twice: on Pebble's own VM with `run_source`, and on PyCPU with
`run_pebble`. We keep the starting numbers in variables, so that PyCPU really does the
sums itself (the last part of this Try It shows why).

```python
from pebble import run_source

from pycpu.translator import UnsupportedFeature, run_pebble

programs = [
    "let big = 32767\nprint(big + 1)",
    "let n = 300\nprint(n * n)",
    "let n = 300\nprint(n * n // 300)",
    "let a = 1000\nprint(a * 30 // 7)",
]
for source in programs:
    vm = run_source(source).strip()
    cpu = run_pebble(source).output.strip()
    print(source.replace("\n", "; "), "->", "Pebble VM:", vm, "PyCPU:", cpu)

try:
    run_pebble("print(32767 + 1)")
except UnsupportedFeature as error:
    print(error)
# Output:
# let big = 32767; print(big + 1) -> Pebble VM: 32768 PyCPU: -32768
# let n = 300; print(n * n) -> Pebble VM: 90000 PyCPU: 24464
# let n = 300; print(n * n // 300) -> Pebble VM: 300 PyCPU: 81
# let a = 1000; print(a * 30 // 7) -> Pebble VM: 4285 PyCPU: 4285
# numbers bigger than 32767 or smaller than -32768 are not supported on PyCPU yet at line 1, column 7
```

Line by line:

- `32767 + 1` is one past the top, so PyCPU wraps to the very bottom, -32768. The VM
  says 32768.
- `300 * 300` is really 90000, which does not fit. Take away one whole trip round the
  circle, 65536, and you get the 24464 that PyCPU prints.
- `n * n // 300` is the sneaky one. The final answer, 300, fits easily, but the number
  in the middle, 90000, did not. PyCPU divided the wrapped 24464 by 300 and got 81.
- `a * 30 // 7` works on both, because every number along the way (1000, 30000 and 4285)
  fits in 16 bits.
- `print(32767 + 1)` with plain numbers is refused. Pebble's compiler works out sums of
  plain numbers itself, before PyCPU ever sees them (see
  [From Pebble to Machine Code](from-pebble-to-machine-code.md)), so the translator is
  handed the single number 32768, which no 16-bit word can hold. It says so rather than
  quietly storing something else.

## How It Works

There is no special code for wrapping anywhere in the translator. It happens because
the hardware does it. `big + 1` becomes `add r1, r1, r2`, and the ALU adds the two
16-bit numbers with its ripple of full adders (from [Adding](adding.md)). Here is the sum
in bits:

```
     0111 1111 1111 1111     32767   (0x7FFF), the biggest positive number
   + 0000 0000 0000 0001         1
   ---------------------
     1000 0000 0000 0000     0x8000: the sign bit is now 1, so this means -32768
```

Every bit up to bit 14 carried into the next, and the last carry landed in bit 15, the
**sign bit**. The bits are a perfectly good answer to "what is `0x7FFF + 1`", but read as
a two's complement number they mean -32768. The ALU even notices: it lights the
**overflow** flag, which means "the true answer did not fit" (from [The ALU](the-alu.md)).
The translated program does not look at that flag; it carries on with the wrapped answer,
just as the counter carries on from 00000. Then `__print_int` reads the word as a signed
number, sees the sign bit, and prints a minus sign.

Multiplying wraps the same way. `__mul` (from [Multiply and Divide](multiply-and-divide.md))
shifts the top number left once per row, and any bit pushed off the left end of the
register is simply lost, so the answer is always the true answer with whole trips of
65536 taken away.

The translator's job is only to make sure nothing *else* goes wrong. A number written in
the program that cannot fit, like `let x = 40000`, is refused with a friendly error, as
is any number Pebble's compiler worked out that does not fit. Numbers that fit go into
the machine exactly; numbers that are *made* too big while the program runs wrap.

So a Pebble program gives the same answers on both machines whenever every number in it,
including every number in the middle of a sum, stays from -32768 to 32767. The helper
`run_and_compare` in `tests/test_translator.py` runs every test program on both machines
and checks exactly that.

## Why Does This Matter?

We could have hidden this. PyCPU could keep every number in two words and do the sums in
two halves, and it would wrap much later. But it would still wrap somewhere, because
*every* real computer has a fixed number of wires per number, and we would only have
moved the cliff edge further away and made it harder to see. A from-scratch computer
should show you the edge.

Real programs fall off this edge. In 2014 the "Gangnam Style" music video was watched
more than 2,147,483,647 times, the biggest number a 32-bit counter can hold, and YouTube
had to switch its view counter to 64 bits before it wrapped round to a negative number.
In the arcade game Pac-Man, the level number is kept in 8 bits, and on level 256 the
game draws garbage over half the screen. Languages such as C and Java wrap whole
numbers exactly the way PyCPU does; Python and Pebble's VM switch to bigger numbers
automatically, which is friendlier but slower. Knowing which kind of machine you are on
is part of being a programmer.

## What's Next

You have seen `__mul` and `__divmod` at work in these sums. Find out how a machine with no
multiply or divide instruction builds them out of shifting and adding, in
[Multiply and Divide](multiply-and-divide.md).
