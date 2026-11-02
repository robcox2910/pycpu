# Negative Numbers

## The Mileage Counter That Rolls Backwards

A car's mileage counter has a row of little wheels, each showing a digit. Say
it has five wheels. Drive one more mile from 00099 and the wheels turn over to
00100. Now imagine the car could drive *backwards*. From 00000, one mile in
reverse and every wheel rolls back past zero and shows **99999**.

Nothing broke. The counter has only five wheels, so it has only 100,000
possible readings, arranged in a circle. Going past the biggest reading brings
you back to the smallest, and going below the smallest brings you round to the
biggest. We call this **wrap**: the numbers wrap around like a clock face.

Now notice something clever. On that circle, 99999 sits exactly one step *before*
00000. So we could simply agree that 99999 *means* "minus one". Then 99998
means "minus two", and so on. The counter never needed a minus sign.

A computer does the same with its bits. A 16-bit number has 65,536 possible
readings, from `0x0000` to `0xFFFF`, arranged in a circle. We agree that the
top half of the circle, the readings from `0x8000` up, mean negative numbers.
The leftmost bit, bit 15, becomes the **sign bit**: 1 means negative. This
agreement is called **two's complement**, and it has a wonderful side effect:
the same adder works for positive and negative numbers alike.

| The mileage counter | In PyCPU |
|---------------------|----------|
| Five wheels | Sixteen wires in a bus |
| 100,000 readings in a circle | 65,536 readings, `0x0000` to `0xFFFF` |
| Rolling past the top back to 00000 | **Wrap**: `0xFFFF + 1` gives `0x0000` |
| 99999 means "minus one" | `0xFFFF` means -1 in two's complement |
| Knowing which half of the circle you are in | The sign bit, bit 15 |
| Driving so far you land on the wrong side | **Overflow**: the true answer did not fit |
| Backwards by adding | Subtracting by adding: `a - b = a + NOT b + 1` |

## Try It

We build two things out of the adder from [Adding](adding.md): one adds `a`
and `b`, and the other flips every bit of `b` with `not_bus`, then adds `a`,
the flipped `b` and a carry in of 1. The helper `signed` reads a reading as a
number that may be negative. Watch what we get from the edges of the circle.

```python
from pycpu.arithmetic import ripple_adder
from pycpu.circuit import Circuit
from pycpu.logic import not_bus
from pycpu.simulator import Simulator


def signed(reading: int) -> int:
    """Read 16 bits as a whole number that can be negative."""
    return reading - 65536 if reading >= 32768 else reading


c = Circuit()
a = c.bus_input("a", 16)
b = c.bus_input("b", 16)
added, carry = ripple_adder(c, a, b, c.low)
subtracted, no_borrow = ripple_adder(c, a, not_bus(c, b), c.high)
sim = Simulator(c)
for x, y in [(5, 3), (3, 5), (0, 1), (0xFFFF, 1), (0x7FFF, 1)]:
    sim.set_bus(a, x)
    sim.set_bus(b, y)
    sim.settle()
    s, d = sim.get_bus(added), sim.get_bus(subtracted)
    print(f"{x:#06x} + {y:#06x} = {s:#06x} (reads {signed(s)}), carry {sim.get(carry)}")
    print(f"{x:#06x} - {y:#06x} = {d:#06x} (reads {signed(d)}), no borrow {sim.get(no_borrow)}")
# Output:
# 0x0005 + 0x0003 = 0x0008 (reads 8), carry 0
# 0x0005 - 0x0003 = 0x0002 (reads 2), no borrow 1
# 0x0003 + 0x0005 = 0x0008 (reads 8), carry 0
# 0x0003 - 0x0005 = 0xfffe (reads -2), no borrow 0
# 0x0000 + 0x0001 = 0x0001 (reads 1), carry 0
# 0x0000 - 0x0001 = 0xffff (reads -1), no borrow 0
# 0xffff + 0x0001 = 0x0000 (reads 0), carry 1
# 0xffff - 0x0001 = 0xfffe (reads -2), no borrow 1
# 0x7fff + 0x0001 = 0x8000 (reads -32768), carry 0
# 0x7fff - 0x0001 = 0x7ffe (reads 32766), no borrow 1
```

Look at the line `0x0000 - 0x0001`. We only ever used the adder, yet the
answer is `0xFFFF`, which reads as -1. And `0xFFFF + 0x0001` wrapped to
`0x0000`, which is just "-1 plus 1 is 0" seen from the other side. The line for
`0x7FFF + 0x0001` is the trap: 32,767 plus 1 should be 32,768, but that reading
is on the negative half of the circle and so it reads as -32,768. The answer
did not fit. That is **overflow**.

## How It Works

The code that does this lives in `src/pycpu/arithmetic.py` (the adder) and
`src/pycpu/logic.py` (`not_bus`). Six small ideas, numbered 0 to 5, make it work.

**0. A small circle first.** The idea is easiest to see with 4 bits, which
have only 16 readings. We agree that readings 0 to 7 mean themselves, and
readings 8 to 15 mean -8 to -1:

```
 reading:  0  1  2  3  4  5  6  7 | 8  9 10 11 12 13 14 15
 means:    0  1  2  3  4  5  6  7 |-8 -7 -6 -5 -4 -3 -2 -1
                                  ^ the sign bit (the leftmost bit) is 1 from here
```

Reading 15 is one step before 0, so it means -1; and 15 + 1 wraps to 0. To
read a reading as a signed number you subtract the size of the circle (16)
from any reading in the top half: 13 - 16 = -3. For our 16-bit circle the size
is 65,536, so `signed` in the Try It does `reading - 65536` for readings of
32768 and up. It works because going all the way round the circle lands you
back where you started, so `reading` and `reading - 65536` are the same spot.
Now the recipe. To make -3 from 3, flip the bits of `0011` to get `1100` (12)
and add one to get `1101` (13), which is -3.

**1. Flip the bits and add one.** To get the negative of a number in two's
complement, flip every bit (a NOT gate on each wire, `not_bus`) and add 1.
Take 5, which is `0000 0000 0000 0101`:

```
    0000 0000 0000 0101      5
    1111 1111 1111 1010      flip every bit
  +                   1      add one
    ───────────────────
    1111 1111 1111 1011      0xFFFB, which reads as -5
```

**2. Why that works.** Take `b` away from 65535, which is sixteen 1s. In
each column you are doing `1 - bit`, and that never needs a borrow, so each bit
simply flips: 0 becomes 1 and 1 becomes 0. So flipping every bit of `b` gives
exactly `65535 - b`. Add one and you have `65536 - b`. But 65536 is one full
trip round the circle, which is the same place as 0. So `65536 - b` sits at
the same spot as `-b`. The circle does the maths for us.

**3. Subtracting is adding.** Put that together: `a - b` is `a + (-b)`, which
is `a + NOT b + 1`. The adder already has a `carry_in` wire, so the "+ 1"
costs nothing: just give it `high` instead of `low`. The whole subtractor is
one row of NOT gates in front of the adder we already own:

```
  b ──[NOT each bit]──┐
                      ├──► [ 16-bit ripple adder ] ──► a - b
  a ──────────────────┘            ▲
                                   │
                   carry in ───── high (always 1)
```

**4. The carry tells you about borrowing.** Subtracting by adding computes
`a + (65536 - b)`. That reaches 65536, which is a carry out of the top column,
exactly when `a` is at least `b`. So the carry out is 1 when no borrow was
needed (`5 - 3`) and 0 when `a` was smaller and the sum fell short (`0 - 1`).
It looks backwards, but it is just the borrow, turned upside down.

**5. Detecting overflow.** If you add two numbers that are both on the same
side of the circle, say two positives, and the answer lands on the other side,
the answer is nonsense, and that is overflow. Adding a positive and a negative
can never overflow, because the answer lies between them. The ALU will watch
the sign bits of both inputs and of the answer to light a warning lamp.

## Why Does This Matter?

Without this trick a computer would need a second, different circuit for
subtracting, and another for comparing, and special handling for every negative
number. Instead one adder serves everything, and a few extra NOT gates give
subtraction. That is why almost every computer you have ever used stores
negative numbers this way. Programmers also meet wrap and overflow in real
life: a counter that suddenly goes from huge to negative, a game score that
flips sign, and rockets that have failed because a number did not fit in the
room it was given.

## What's Next

We have an adder and a subtractor, but a processor needs to do more: AND, OR,
shift, pass a value through, and tell us things about the answer. The next
page packs all of these into one box with a dial: [The ALU](the-alu.md).
