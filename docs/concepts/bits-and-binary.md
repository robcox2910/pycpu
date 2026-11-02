# Bits and Binary

## The Light Switch

Look at the light switch on your wall. It can be in only two positions: **up**
(the light is on) or **down** (the light is off). There is no "a little bit
on". A computer is built from billions of tiny switches just like it, and
everything a computer does, from showing a cartoon to adding up your score,
comes from switches being on or off.

One switch holds the smallest piece of information there is: a yes or a no.
We call it a **bit**. We write "on" as `1` and "off" as `0`.

One bit is not much, but you can count with a row of them. Hold up your
fingers: with ten fingers you can count to ten. But if each finger can be
**up or down** and you use the *pattern*, you can count much higher. Four
fingers can make 16 different patterns, and ten fingers can make 1,024.

That way of counting with on/off patterns is called **binary**. In our
ordinary counting (called *decimal*) the places are ones, tens, hundreds,
each worth ten times the one before. In binary each place is worth **two
times** the one before: 1, 2, 4, 8, 16, and so on.

| In everyday life | In PyCPU |
|------------------|----------|
| A light switch, up or down | A **bit**, `1` or `0` |
| A row of switches | A **bus**: a row of wires, one per bit |
| The first switch, worth 1 | Bit 0, the *least significant* bit |
| Each next switch, worth double | Bit 1 is worth 2, bit 2 is worth 4, bit 3 is worth 8 |
| A short way to write a long pattern | **Hex**, base sixteen, like `0xBEEF` |

Notice the order. PyCPU always lists the **ones switch first**, then the twos,
then the fours. "Least significant bit first" is just the grown-up way of
saying that. (A bus is a row of wires treated as one number; you will meet wires on the
next page.)

## Try It

Here is a row of four switches, ones switch first, turned into a number, and
then shown three ways. The last line uses a 16-switch row, the size of every
word in PyCPU.

```python
switches = [1, 1, 0, 1]  # the ones, twos, fours and eights switches
value = 0
for place, switch in enumerate(switches):
    value += switch * 2**place  # each place is worth double the one before
print("the number is", value)
print("in binary:", format(value, "b"))
print("in hex:", format(value, "x"))

word = 0xBEEF
print("a 16-bit word:", format(word, "016b"))
print("its value:", word, "which is hex", format(word, "x"))
# Output:
# the number is 11
# in binary: 1011
# in hex: b
# a 16-bit word: 1011111011101111
# its value: 48879 which is hex beef
```

Read `1011` from the right: one 1, one 2, no 4, one 8. That is 1 + 2 + 8 = 11.
(Written on paper, binary puts the biggest place on the *left*, just like
decimal. The list in our code runs the other way round, ones first.)

## How It Works

**Why only two states?** A switch that has to tell apart ten different
levels is fussy; a tiny bit of dust and it gets confused. A switch that only
has to say "on" or "off" is easy to build, and easy to trust. So computers use
two, and make big things out of lots of them.

**Counting in binary.** Each place is worth double the one before:

```
place:    3    2    1    0
worth:    8    4    2    1
switch:   1    0    1    1     ->  8 + 0 + 2 + 1 = 11
```

With `n` switches there are `2**n` patterns, so 4 switches give 16 numbers
(0 to 15) and 16 switches give 65,536 numbers (0 to 65,535). That is why
PyCPU's words, which are 16 bits wide, can hold up to 65,535.

**Hex.** Sixteen switches are a long thing to read out loud. Hex (short for
*hexadecimal*, counting in sixteens) is a shorthand: every group of four bits
becomes one character, using `0`-`9` and then `a`-`f` for ten to fifteen.

```
1011  1110  1110  1111      <- 16 bits
  b     e     e     f       <- 4 hex characters:  0xBEEF
```

The `0x` in front just says "what follows is hex". Hex and binary are the
same number written two ways, like "twelve" and "12".

PyCPU's own code that does this lives in `src/pycpu/simulator.py`:
`set_bus` and `get_bus` turn a number into a row of wires and back, ones
switch first.

## Why Does This Matter?

Everything a computer holds is a number made of bits: a photo is a long row
of them, a song is a long row of them, and the instructions of a program are
a row too. If you understand that a pile of on/off switches can stand for any
number, you already understand what the memory of a computer *is*. Real
computers, from the one in a microwave to the one in a games console, store
and count in exactly this way.

## What's Next

You have a switch. Now: what can you *do* with switches? The next page,
[Switches and NAND](switches-and-nand.md), connects them with wires and
builds the one tiny part that the whole computer is made of.
