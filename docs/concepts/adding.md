# Adding

## Column Addition and Carrying the One

Remember adding big numbers on paper at school? You line them up in columns
and start at the right:

```
    1 9 7
  + 0 0 5
  -------
    2 0 2
```

7 + 5 is 12. You cannot fit 12 in one column, so you write down the **2** and
**carry** the 1 over to the next column. Then 9 + 0 + the carried 1 is 10:
write the 0, carry another 1. And so on, one column at a time, right to left.
The carry is a little note that one column hands to its neighbour.

Computers add exactly like this, except every column holds a single bit (a 0
or a 1, see [Bits and Binary](bits-and-binary.md)), so the columns are small.
In binary there are only four things a column ever has to add:

```
   0 + 0 = 0        0 + 1 = 1        1 + 0 = 1        1 + 1 = 10  (write 0, carry 1)
```

A circuit that adds two bits and tells you the **sum** (the digit you write
down) and the **carry** (the 1 you pass on) is called a **half adder**. It is
"half" because it forgot something: it has no place to receive a carry that
the column to its right passed in. A **full adder** has that third input, so
it adds three bits: the two from this column, and the carry from the
neighbour. Chain sixteen full adders in a row, each handing its carry to the
next, and you can add two 16-bit numbers. Because the carry has to travel
along the row like a wave, from the right-hand end to the left, this layout
is called a **ripple** adder.

| Adding on paper | In PyCPU |
|-----------------|----------|
| One column of the sum | One `full_adder(c, a, b, carry_in)` |
| The digit you write down | The `sum` wire it returns |
| The 1 you carry to the next column | The `carry` wire it returns |
| A column with nothing carried in | A `half_adder(c, a, b)` |
| A whole row of columns | `ripple_adder(c, a, b, carry_in)` |
| Working right to left | Bit 0 first: buses are least significant bit first |
| A carry that runs along the row | The ripple, seen in the wire values |

## Try It

First the half adder: every possible pair of bits, and what it costs.

```python
from pycpu.arithmetic import half_adder
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

c = Circuit()
a = c.input("a")
b = c.input("b")
total, carry = half_adder(c, a, b)
sim = Simulator(c)
for x in (0, 1):
    for y in (0, 1):
        sim.set(a, x)
        sim.set(b, y)
        sim.settle()
        print(x, "+", y, "= carry", sim.get(carry), "sum", sim.get(total))
print("a half adder costs", c.gate_count, "NAND gates")
# Output:
# 0 + 0 = carry 0 sum 0
# 0 + 1 = carry 0 sum 1
# 1 + 0 = carry 0 sum 1
# 1 + 1 = carry 1 sum 0
# a half adder costs 6 NAND gates
```

Now watch a carry ripple. We chain four full adders by hand and add 7 (0111)
and 1 (0001). Each line shows one column. Look at the carry going in: it is
the carry that came out of the line above.

```python
from pycpu.arithmetic import full_adder
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

c = Circuit()
a = c.bus_input("a", 4)
b = c.bus_input("b", 4)
carries = [c.low]  # nothing is carried into the first column
sums = []
for i in range(4):
    total, carry = full_adder(c, a[i], b[i], carries[i])
    sums.append(total)
    carries.append(carry)
sim = Simulator(c)
sim.set_bus(a, 7)
sim.set_bus(b, 1)
sim.settle()
for i in range(4):
    print(
        f"column {i}: {sim.get(a[i])} + {sim.get(b[i])} + carry in {sim.get(carries[i])}"
        f" -> sum {sim.get(sums[i])}, carry out {sim.get(carries[i + 1])}"
    )
print("7 + 1 =", sim.get_bus(tuple(sums)))
one = Circuit()
full_adder(one, one.input("x"), one.input("y"), one.input("carry"))
print("a full adder costs", one.gate_count, "NAND gates")
# Output:
# column 0: 1 + 1 + carry in 0 -> sum 0, carry out 1
# column 1: 1 + 0 + carry in 1 -> sum 0, carry out 1
# column 2: 1 + 0 + carry in 1 -> sum 0, carry out 1
# column 3: 0 + 0 + carry in 1 -> sum 1, carry out 0
# 7 + 1 = 8
# a full adder costs 15 NAND gates
```

The carry started in column 0 and was handed along, one column at a time,
until column 3 had a 1 to add. Finally the ready-made version, sixteen
columns wide, and how much work the carry causes:

```python
from pycpu.arithmetic import ripple_adder
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator

c = Circuit()
a = c.bus_input("a", 16)
b = c.bus_input("b", 16)
total, carry_out = ripple_adder(c, a, b, c.low)
sim = Simulator(c)
sim.set_bus(a, 0x00FF)
sim.set_bus(b, 1)
sim.settle()
print(f"0x00FF + 1 = {sim.get_bus(total):#06x}, carry out {sim.get(carry_out)}")
print("sixteen columns cost", c.gate_count, "NAND gates")
print("its columns are named", c.children("")[:3], "...")

# How far does a carry have to travel? Start from two numbers that make no
# carry at all, then from a pile of 1s that carries the whole way.
quiet = Simulator(c)
quiet.settle()
quiet.set_bus(b, 1)
print("a quiet add took", quiet.settle(), "gate evaluations")
rippling = Simulator(c)
rippling.set_bus(a, 0xFFFF)
rippling.settle()
rippling.set_bus(b, 1)
print("a full ripple took", rippling.settle(), "gate evaluations")
# Output:
# 0x00FF + 1 = 0x0100, carry out 0
# sixteen columns cost 240 NAND gates
# its columns are named ['bit0', 'bit1', 'bit2'] ...
# a quiet add took 8 gate evaluations
# a full ripple took 132 gate evaluations
```

## How It Works

The code is in `src/pycpu/arithmetic.py`. Each adder is built from the layer
just below it, and the bottom layer is the gates from
[Logic Gates from NAND](gates.md). In the pictures, a box is a part we built
earlier, and a line is a wire.

**1. The half adder: an XOR and an AND.** Look at the four sums again. The
sum digit is 1 when the two bits *differ* (0+1, 1+0) and 0 when they match.
That is exactly an XOR. The carry is 1 only when *both* bits are 1. That is
exactly an AND. So a half adder is two gates we already own, fed the same two
wires. XOR is 4 NAND gates and AND is 2, so a half adder is **6** NAND gates.

```
        ┌─────────────┐
 a ──┬──┤     XOR     ├── sum
     │  │  (4 NANDs)  │
 b ──┼┬─┤             │
     ││ └─────────────┘
     ││ ┌─────────────┐
     │└─┤     AND     ├── carry
     └──┤  (2 NANDs)  │
        └─────────────┘
```

**2. The full adder: two half adders and an OR.** We have three bits to add:
`a`, `b` and the carry coming in. Add two of them with a half adder. Then
add the third to *that* answer with a second half adder. The final sum digit
is the second half adder's sum. A carry can come out of either half adder,
and they can never both carry at once, so we OR the two carries together. Two
half adders (6 + 6) and an OR (3) make **15** NAND gates.

```
 a ───►┌────────┐ sum1 ┌────────┐
 b ───►│ half 1 ├─────►│ half 2 ├──────────────► sum
       └───┬────┘      └─▲────┬─┘
        c1 │             │    │ c2
           │   carry in ─┘    │
           │                  │
           │     ┌────┐       │
           └────►│ OR ├◄──────┘
                 └─┬──┘
                   └──────────────────────────► carry out
```

`c1` and `c2` are the two carries. The OR passes on a 1 if either of them is 1.

**3. The ripple adder: sixteen full adders in a row.** Column 0 gets the
`carry_in` you give it (usually `low`, a wire that is always 0). Its carry out
becomes column 1's carry in, and so on. Each column is filed in its own scope
named `bit0`, `bit1`, ... up to `bit15`, so with
[Looking Inside a Circuit](looking-inside.md) you can zoom into any column and
see the real values on its wires. 16 columns at 15 gates each is **240**
NAND gates.

```
   a15 b15       a2  b2        a1  b1        a0  b0
    │   │         │   │         │   │         │   │
  ┌─┴───┴─┐     ┌─┴───┴─┐     ┌─┴───┴─┐     ┌─┴───┴─┐
  │ full  │ ... │ full  │     │ full  │     │ full  │
  │ adder │◄────┤ adder │◄────┤ adder │◄────┤ adder │◄── carry in
  └─┬───┬─┘ c3  └─┬───┬─┘ c2  └─┬───┬─┘ c1  └─┬───┬─┘ (c0)
    │   │         │   │         │   │         │   │
 carry  s15       │  s2         │  s1         │  s0
  out             │             │             │
```

**4. Why it ripples.** Column 3 cannot know its answer until column 2 has
decided whether it is sending a carry, and column 2 has to wait for column 1,
and so on. When no carry is made, nothing travels and the circuit settles
quickly. When a carry has to run the whole row, every column in turn has to
wake up and change its mind. The last Try It measured this on the real
circuit: the quiet add took 8 gate evaluations, and the carry that ran the whole row
took 132.
Real processors use cleverer layouts to shorten the wait. We keep the ripple
because you can see it.

## Why Does This Matter?

Adding is the one piece of arithmetic a computer cannot live without. The
next page shows that subtracting is just adding with a trick, and the page
after builds the part of a processor, the ALU, that does the sums. Counting
which instruction to run next is addition. Working out which memory address
to fetch is addition. Even the circuit that draws this page for you leans on
adders. And you have just seen that the whole tower, sum and carry and all,
rests on a pile of NAND gates and nothing else.

## What's Next

A 16-bit adder always gives a 16-bit answer. What happens when the true answer
does not fit, and how can the same adder subtract? Read
[Negative Numbers](negative-numbers.md).
