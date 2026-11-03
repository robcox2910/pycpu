# Machine Code

## A Secret Code Card

Imagine a spy's codebook where every order is a short row of boxes on a card:
the first box says *what to do* (1 = "open", 2 = "close", 3 = "wait"), and the
other boxes give the details (*which* door, *how long*). Handing someone the
card "2 5 1" means "close door 5 for 1 minute". The card is only numbers, but
anyone with the codebook knows what it means.

That is **machine code**: instructions written as numbers. Each PyCPU instruction
is one 16-bit word, cut into boxes called **fields**. The first box, the top four
bits, is the **opcode** (operation code): it says what to do. Four bits give
16 different opcodes, from 0 to 15. The rest of the word holds the details: which
register to use, or a small number to use. A different layout of boxes is used by
different opcodes, but the opcode is always in the same place, so the CPU always
knows where to look first.

| In the spy's codebook | In PyCPU |
|-----------------------|----------|
| The codebook | `src/pycpu/isa.py` (ISA means *instruction set architecture*: the list of orders) |
| The first box, what to do | The **opcode**: bits 15 to 12, an `Opcode` |
| The other boxes | Fields such as `rd`, `ra`, `rb`, `fn` and `imm`, the **immediate**: a number written right inside the instruction, such as the 3 in "put 3 in `r1`" |
| Writing a card | `encode(opcode, rd=..., ra=...)` gives the 16-bit word |
| Reading a card | `decode(word)` gives an `Instruction` with the fields |
| Four lamps on the machine | The **flags**: `zero`, `negative`, `carry`, `overflow` |
| The machine refusing an impossible order | A **fault**: `Fault.BAD_ADDRESS` and friends |

## Try It

First, make one instruction and take it apart again. `ALU` with `ADD` means
"add two registers". Here: `rd = r3`, `ra = r1`, `rb = r2`, so it says
`r3 = r1 + r2`. (`rd` is the *d*estination register, where the answer goes;
`ra` and `rb` are the two registers to read.)

```python
from pycpu.arithmetic import AluOp
from pycpu.fast import FastMachine
from pycpu.isa import Condition, Fault, Opcode, decode, encode

word = encode(Opcode.ALU, rd=3, ra=1, rb=2, fn=AluOp.ADD)
print(f"{word:#06x} = {word:016b}")
instruction = decode(word)
print("opcode:", instruction.opcode.name)
print("rd, ra, rb:", instruction.rd, instruction.ra, instruction.rb)
print("fn:", AluOp(instruction.fn).name)

# The countdown from the last page, written with encode instead of by hand.
countdown = [
    encode(Opcode.LI, rd=1, imm=3),
    encode(Opcode.ADDI, rd=1, imm=-1),
    encode(Opcode.BR, rd=Condition.NE, imm=-2),
    encode(Opcode.HALT),
]
print([hex(w) for w in countdown])

# The flags: compare 5 with 5 and look at the lamps.
machine = FastMachine(words=64)
machine.load_program(
    [
        encode(Opcode.LI, rd=1, imm=5),
        encode(Opcode.LI, rd=2, imm=5),
        encode(Opcode.CMP, ra=1, rb=2),
    ]
)
machine.run(3)
print(machine.state().flags)

# A fault: jump to a card that is not in memory.
machine = FastMachine(words=64)
machine.load_program([encode(Opcode.JMP, imm=4000)])
machine.run(10)
state = machine.state()
print("halted:", state.halted, "because", Fault(state.halt_code).name)
# Output:
# 0x0650 = 0000011001010000
# opcode: ALU
# rd, ra, rb: 3 1 2
# fn: ADD
# ['0x2203', '0xe2ff', '0x83fe', '0xf000']
# Flags(zero=1, negative=0, carry=1, overflow=0)
# halted: True because BAD_ADDRESS
```

Look at `0x0650` in binary, cut into its boxes:

```
   0000   011   001   010   000
   opcode  rd    ra    rb    fn
   ALU     r3    r1    r2    ADD
```

## How It Works

`src/pycpu/isa.py` is the codebook, written once. Every other part of the
project, the assembler, the fast engine and the gate CPU, reads the same one.

**The boxes.** Bits are numbered from the right, starting at 0:

```
 15 14 13 12 | 11 10  9 |  8  7  6 |  5  4  3 |  2  1  0
   opcode    |   rd     |    ra    |    rb    |    fn          (ALU, CMP)
   opcode    |   rd     |   immediate: 8 bits (imm8)          (LI, LHI, ADDI, HALT)
   opcode    |   rd     |    ra    |  offset: 6 bits (off6)   (LOAD, STORE)
   opcode    |  cond    |  offset: 9 bits (off9)              (BR)
   opcode    |  address: 12 bits (addr12)                     (JMP, CALL)
```

Not every field is used by every opcode. An unused field is written as 0, and
ignored when the word is read. This means that *any* 16-bit word is a valid
instruction: the CPU never meets a word it cannot read. A word like `0xFFFF` is
simply `HALT` with the code 255. `decode` never fails; it is `encode` that
refuses to write a value which does not fit a box, such as `LI` with 256 (the
box is only 8 bits, so it tops out at 255).

**How `decode` takes a word apart.** There is no magic: it is shifting and masking,
which are the same wires-and-gates ideas from the ALU page. To get `rd` out of
`0x0650`, shift the word right 9 places so that bits 11-9 land at the bottom, then
keep only the bottom three bits (a *mask* is a pattern of 1s that lets only those
bits through, here `0b111`): `0x0650 >> 9` is `0b11`, and `0b11 & 0b111` is 3. The
opcode is `word >> 12`. In the same way `ra` is `(word >> 6) & 0b111` and `rb` is
`(word >> 3) & 0b111`. Signed immediates need one more step, because the bits
alone cannot say whether `FF` means 255 or -1: if the top bit of the box is 1,
`decode` subtracts the box's size (256 for an 8-bit box) to get the negative
number.

**Numbers that can be negative.** An *immediate* is a number written right inside
the instruction. Some immediates are signed: `ADDI r1, -1` needs a -1. Remember
[two's complement](negative-numbers.md): in eight bits, -1 is `11111111`. That is
why the countdown's second card is `0xE2FF`: the `FF` at the end is -1. Offsets
work the same way, so `BR` can jump backwards, and `LOAD` can reach the word
just before an address.

**The branch.** The card `BR NE, -2` (`0x83FE`) means "if the answer last time
was not zero, add -2 to the PC". Remember the PC already points to the *next*
card when this one runs. We count cards from 0, so this is card 2 and the PC is
3, and 3 - 2 = 1. That is why the countdown goes back to card 1.

**The four lamps.** The ALU page showed four flags. Some instructions set them
(`ALU`, `CMP` and `ADDI`) and the rest leave them as they were. `CMP` is a
subtraction whose answer is thrown away, kept only for the lamps. A `BR` then asks
a question about the lamps. The eight questions, called **conditions**, are:

| Condition | Asks | In terms of the lamps |
|-----------|------|-----------------------|
| `EQ` | equal? | `zero` is on |
| `NE` | not equal? | `zero` is off |
| `LT` | less than (signed)? | `negative` differs from `overflow` |
| `GE` | at least (signed)? | `negative` equals `overflow` |
| `LE` | at most (signed)? | `zero`, or `negative` differs from `overflow` |
| `GT` | greater than (signed)? | not `zero`, and `negative` equals `overflow` |
| `LTU` | less than (unsigned)? | `carry` is off |
| `GEU` | at least (unsigned)? | `carry` is on |

(A subtraction sets `carry` to 1 when nothing had to be borrowed, which is why
"carry is on" means "at least". Unsigned means we treat every word as a plain
number from 0 to 65,535, with no negatives.) `condition_holds` in `isa.py` is the
function that answers the question.

**Faults.** A **fault** is the machine refusing an impossible order, like a cook
told to fetch recipe card number 9,000 from a stack of 4,096. The computer
stops at once (`halted` becomes true), writes why into `halt_code`, and changes
nothing else, so you can look at the scene of the crime. `BAD_ADDRESS` (1) means
an address outside memory. `HALT 0` is the happy ending: the code 0 means "finished
normally". Any other number is a problem report. Two more fault codes, `STACK_OVERFLOW`
(2) and `DIVIDE_BY_ZERO` (3), are reserved for the language we build near the end,
which raises them with `HALT`.

The full table of all 16 opcodes, with one worked example each, is on the
[Instruction Set reference page](../reference/instruction-set.md).

## Why Does This Matter?

Here is the idea that makes computers possible: *an order is just a number, so it
can sit in memory right next to data.* The program and the things it works on
are stored in the same RAM, in the same kind of word. That means a program can
be loaded, copied, swapped for another, or even written by another program, which
is what a compiler does. It is why your phone can install a new app without
changing a single wire.

Real processors work the same way. Your computer's chip also splits a word into an
opcode and fields, with more opcodes and longer words. The pattern of "a few bits to say
what, the rest to say with what" is the same everywhere from toys to supercomputers.

## What's Next

Writing `0xE2FF` by hand is miserable, and you will not remember which number means
`ADDI`. Continue with [Assembly Language](assembly-language.md), where you write
`addi r1, -1` and a helper program turns it into numbers for you.
