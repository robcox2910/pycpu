# Printing a Number

## A Cash Register With One Slot Per Letter

Imagine a cash register whose printer has a slot for only *one character at a time*.
You cannot hand it the number 305. You have to post three little cards through the slot,
one after another: a `3`, then a `0`, then a `5`. The number 305 is one idea in the
computer, but the printer only understands single characters.

So printing a number means breaking it into its **digits** (the single symbols 0 to 9
that we write numbers with) and posting one **character** (a single letter, digit or
symbol, like `3` or `-` or `A`) for each. Our computer has exactly such a slot: the
**output port**, a special address, `0xFFFF`, that works like a screen. When a program
stores a word there, the word is not saved in memory. It is sent out as a character, as
described in the [instruction set](../reference/instruction-set.md).

There is a catch. The characters are not the numbers themselves. The computer writes
every character as a **character code**, a number that stands for the symbol. The code
for `'0'` is 48, `'1'` is 49, and so on up to `'9'` which is 57. So to print the digit 5
we do not send 5, we send 5 + 48 = 53. (The newline, the "go to the next line" character,
is code 10.)

| Cash register | In PyCPU |
|---------------|----------|
| The slot that takes one card | The output port, address `0xFFFF` |
| Posting a card | `store r3, [r6]` with `r6` holding `0xFFFF` |
| A card with a digit on it | The digit plus 48, its character code |
| Breaking 305 into 3, 0, 5 | Dividing by ten again and again (`__divmod`) |
| A tray that hands the cards back in reverse | The stack: `push` and `pop` |
| The routine that prints a number | `__print_int` |
| The routine that prints a piece of text | `__print_text` |
| Their home | `RUNTIME`, in `src/pycpu/translator/runtime.py` |

## Try It

We call the routines the same way as in [Multiply and Divide](multiply-and-divide.md):
set up the registers, `call`, and look at the result. This time the result is what the
machine **printed**: the machine's `output` is the list of codes sent to the port, and
`output_text` turns those codes into text.

```python
from dataclasses import replace

from pycpu.assembler import assemble
from pycpu.fast import FastMachine
from pycpu.state import program_state
from pycpu.translator import RUNTIME, RUNTIME_STACK_WORDS


def run(number=0, text=None):
    """Print a number (or, if text is given, a piece of text) and return the machine's state."""
    routine = "__print_text" if text is not None else "__print_int"
    data = f'message: .string "{text}"' if text is not None else ""
    program = assemble(f"call {routine}\nhalt\n{RUNTIME}\n{data}", words=256)
    state = program_state(program.words, 256)
    registers = list(state.registers)
    registers[1] = program.labels["message"] if text is not None else number & 0xFFFF
    machine = FastMachine(words=256)
    machine.load_state(replace(state, registers=tuple(registers)))
    machine.run(5000)
    return machine.state()


for number in (305, -42, 0, -32768):
    print(repr(run(number).output_text))
print("codes sent for 305:", run(305).output)
print("codes sent for -42:", run(-42).output)
print(repr(run(text="Hi there").output_text))
print("stack words the routines need:", RUNTIME_STACK_WORDS)
# Output:
# '305\n'
# '-42\n'
# '0\n'
# '-32768\n'
# codes sent for 305: (51, 48, 53, 10)
# codes sent for -42: (45, 52, 50, 10)
# 'Hi there\n'
# stack words the routines need: 9
```

The first line of output is `'305\n'`: the three digits and then the newline that moves
on to the next line. Look at the codes: 305 sends 51, 48, 53, which are `'3'`, `'0'`
and `'5'`. And `-42` starts with 45, the code for the minus sign.

## How It Works

Both routines live in `src/pycpu/translator/runtime.py`, next to `__mul` and
`__divmod`, and follow the same rules: input in `r1`, `call` it, and `r0` and `r7` come
back untouched. Both finish by printing a newline, so each call prints a whole line.

### The digits come out backwards

How do you get the digits of 305? Divide by ten. `305 // 10` is 30 with a **remainder**
(what is left over, from [Multiply and Divide](multiply-and-divide.md)) of 5. That
remainder is the *last* digit. Do it again: `30 // 10` is 3 remainder 0, so the next
digit from the right is 0. Again: `3 // 10` is 0 remainder 3, and the number has run out.

```
   number   // 10   remainder (the digit)
     305      30        5      <- the last digit comes out FIRST
      30       3        0
       3       0        3      <- the first digit comes out LAST
```

We get the digits right to left, but we must print them left to right. The fix is the
**stack** from [The Stack](the-stack.md), the pile where the last thing pushed is the first
thing popped. Push 5, push 0, push 3, and then pop: out come 3, 0, 5, the right way
round. A stack turns a list round, like flipping a pile of cards over. We use
repeated division by ten through `__divmod` rather than repeated subtracting: a 16-bit
number has at most five digits, so that is at most five rounds, while subtracting ten
again and again could take far more.

Each digit is turned into its character code by adding 48 (`addi r2, 48`) before it is
pushed. To know when to stop popping, `__print_int` first pushes a **sentinel**, a
marker that can never be a character: the number 0, which is no printable character. The
popping loop prints until it pops the 0.

### Printing text

`__print_text` is simpler. A piece of text in memory is a row of character codes, one per
word, ending with a 0 (that is what `.string` writes, from
[Assembly Language](assembly-language.md)). `r1` holds the address of the first one. The
routine `load`s a word, stops if it is 0, `store`s it to the output port, steps `r1` along
by one, and repeats.

### The minus sign

A negative number gets a `-` posted first, and then its digits are those of the number
without its sign. The cheap way would be to negate the number and carry on, but
`-32768` has no positive partner in 16 bits (the biggest is 32767), so negating it gives
`-32768` again. Instead, the first division is done on the negative number itself.
Floor division (it rounds down) gives `-305 // 10 = -31` with remainder 5, which means
`-305 = -31 * 10 + 5`. The last digit of 305 is therefore `10 - 5`, and the rest of the
number is `31 - 1`, which is 30. If the remainder is 0, the digit is simply 0 and the
rest is `-quotient`. After that first step everything is positive and the ordinary loop
takes over.

## Why Does This Matter?

Without this routine a program could compute anything and never tell you. Showing a
result means turning it into characters, and every `print` in every language does the
same job under the hood: divide by ten, collect the digits, add the code for `'0'`.
Early computers had no printing routine built in, so programmers wrote this loop
themselves. Here it also decides how much stack we must keep spare: a 5-digit negative
number is the deepest use, which is why `RUNTIME_STACK_WORDS` is now 9 (it was 3 before
the printing routines): the return address, the sentinel, four digits waiting, the `call` into `__divmod` and its
two pushes. This is the routine behind every Pebble `print(x)`: as you saw in
[From Pebble to Machine Code](from-pebble-to-machine-code.md), it becomes `pop r1` and
`call __print_int`.

## What's Next

You can now compute with numbers and show them. Next, do all of this with buttons, and
watch the whole running computer, on [The Bench](the-bench.md).
