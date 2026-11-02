# Assembly Language

## A Recipe, and a Helper Who Translates It

Imagine you want to give the cook a recipe, but the cook only reads the secret number
code from the [last page](machine-code.md). Writing `57 3 1 0 9 2 ...` all day would
drive anyone mad, and one wrong digit would burn the dinner. So you do what a sensible
person does: you write the recipe in *words* ("put 3 in the blue bowl", "if it is not
empty, go back to the line called *loop*"), and you hire a helper who sits at a desk
and translates every line of your words into the cook's number code. The helper also
keeps **bookmarks**: you stick a sticky tab on a line and call it "loop", and wherever
the recipe says "go back to loop", the helper looks up which card number that tab is
on, so you never count cards yourself.

That helper is an **assembler**: a program that turns readable text into machine code.
The words you write are **assembly language**. Each instruction gets a short name
called a **mnemonic** (a memory-helper word, pronounced "nem-ON-ic"), such as `li`,
`addi` or `halt`. The bookmarks are **labels**: a name followed by a colon, like
`loop:`, which stands for "the address of the instruction right here".

| The recipe helper | In PyCPU |
|-------------------|----------|
| The recipe in words | Assembly text, one instruction per line |
| A word like "put" or "add" | A **mnemonic**: `li`, `addi`, `load`, `halt` ... |
| A sticky tab on a line | A **label**: `loop:` |
| "Go back to the tab called loop" | `br ne, loop` |
| The helper at the desk | `assemble(source)` in `src/pycpu/assembler.py` |
| The finished stack of number cards | A `Program`: `words`, `labels`, and `lines` |
| A helper reading cards back into words | `disassemble(word, address)` |
| A line the helper cannot understand | An `AssemblyError`, which says which line and what to do |

## Try It

Here is a program that says hello. It is written in assembly, assembled into words,
listed back out in words (each address, its number, and what the number means), and then
run on the fast engine from the last page. Everything after a `;` is a comment: a note
for people that the assembler skips.

```python
from pycpu.assembler import assemble, disassemble
from pycpu.fast import FastMachine

source = """
    set r1, msg        ; r1 = where the message lives
    set r2, 0xFFFF     ; r2 = the address of the output port, like a screen
next:
    load r3, [r1]      ; r3 = the next letter
    cmp r3, r0         ; r0 is 0, so is this the 0 that ends the message?
    br eq, done
    store r3, [r2]     ; send the letter to the screen
    addi r1, 1         ; move on to the next letter
    jmp next
done:
    halt
msg:
    .string "Hi"       ; the letters H and i, then a 0
"""
program = assemble(source)
print("labels:", program.labels)
for address, word in enumerate(program.words[: program.labels["msg"]]):
    print(f"{address:2}  {word:#06x}  {disassemble(word, address)}")
print("message words:", [f"{word:#04x}" for word in program.words[program.labels["msg"] :]])

machine = FastMachine(words=64)
machine.load_program(program.words)
machine.run(1000)
print("output:", machine.state().output_text)
# Output:
# labels: {'next': 4, 'done': 10, 'msg': 11}
#  0  0x220b  li r1, 11
#  1  0x3200  lhi r1, 0
#  2  0x24ff  li r2, 255
#  3  0x34ff  lhi r2, 255
#  4  0x4640  load r3, [r1]
#  5  0x10c0  cmp r3, r0
#  6  0x8003  br eq, 10
#  7  0x5680  store r3, [r2]
#  8  0xe201  addi r1, 1
#  9  0x6004  jmp 4
# 10  0xf000  halt
# message words: ['0x48', '0x69', '0x00']
# output: Hi
```

Two things to notice. First, `set r1, msg` became *two* instructions, `li` and `lhi`,
and `set r2, 0xFFFF` became `li r2, 255` then `lhi r2, 255`: a register is 16 bits but
an immediate only has room for 8, so `set` fills the register in two halves (it is not a
real instruction, just a shortcut the assembler expands for you). Second, the labels
turned into plain numbers: `br eq, done` became `br eq, 10`, and `jmp next` became
`jmp 4`. You never had to count.

## How It Works

The assembler lives in `src/pycpu/assembler.py` and it is built on the codebook from
the last page: every instruction it writes goes through `encode` in `isa.py`, and
`disassemble` reads with `decode`. The assembler adds no new idea about what a number
means. It only reads text.

**Step 0: tidy each line.** The assembler takes the text one line at a time, remembers
the line number (so it can complain helpfully), cuts off any comment after a `;`, and
skips the line if nothing is left.

**Pass 1: find the bookmarks.** The assembler cannot write `jmp next` until it knows
where `next` is, and `next` may even be *further down* than the `jmp`. So it reads the
whole text twice. On the first pass it only counts: how many words each line will
become. An ordinary instruction is 1 word, `set` is 2, `.word` is 1, and `.string "Hi"`
is one word per letter plus a 0 at the end. Whenever it meets a label it writes down the
current count as that label's address.

```
 source line              words    address counted so far
 set r1, msg                2       0, 1
 set r2, 0xFFFF             2       2, 3
 next:                      0       <- label "next" = 4
 load r3, [r1]              1       4
 ...
 halt                       1       10
 msg:                       0       <- label "msg" = 11
 .string "Hi"               3       11, 12, 13
```

**Pass 2: write the cards.** Now every label is known, so the assembler goes line by
line again. For each one it works out the fields from the words you wrote and calls
`encode`. Two cases are worth a look. A `jmp` or `call` takes the label's address
directly. A `br` is different: the machine adds an *offset* to the PC, and the PC
already points at the next instruction. So the assembler computes
`target - (address + 1)`. For `br eq, done` at address 6 with `done` at 10, that is
`10 - 7 = 3`, which is the `0003` at the end of `0x8003`. If that number does not fit in
`br`'s 9-bit box (it must be -256 to 255), the assembler says the target is too far, and
tells you to branch over a `jmp` instead (a `jmp` reaches anywhere).

```
   "br eq, done"
        |  pass 1 said: done = 10        this br sits at address 6
        v
   offset = 10 - (6 + 1) = 3
        v
   encode(Opcode.BR, rd=Condition.EQ, imm=3)  ->  0x8003
```

**Syntax in one place.** One instruction per line. A label is a name then a colon
(letters, digits and `_`, not starting with a digit; capitals matter), and it may sit
on a line of its own or in front of an instruction. Mnemonics and register names such as
`R1` can be written in any case. Operands are separated by commas. A memory operand is
`[r2]`, `[r2+3]` or `[r2-1]`. A number is decimal (`12`, `-3`), hex (`0x1F`) or a letter in
quotes (`'A'`, which is 65). Besides the instruction names on the
[Instruction Set page](../reference/instruction-set.md) there is `set`, plus two
directives (orders to the assembler itself, not to the CPU): `.word value` puts one raw
word in memory, and `.string "text"` puts one word per letter followed by a 0.

**Going backwards.** `disassemble(word, address)` is the same path in reverse: `decode`
the word, then print it as the text the assembler would accept, always in the same
neat shape (lower case, `[r2-1]`, and a `br` shows its absolute target such as
`br eq, 10`, which is why it needs the address). It cannot recover your labels or
comments, because the number cards never contained them. A test checks that
disassembling a word and assembling the text again gives the same word back.

**When you get it wrong.** Every mistake becomes an `AssemblyError` that begins with the
line number and says what is wrong and what would be right, for example
`line 2: r8 is not a register. The registers are r0, r1, r2, r3, r4, r5, r6 and r7.`
Nothing the assembler is given, however silly, should crash it with some other error.
A test throws thousands of random scraps of text at it to check.

## Why Does This Matter?

Without an assembler, every program would have to be written as raw numbers, and one
mistyped digit, or one jump that is off by a card after you add a line above it, would
break the whole thing in a way that is miserable to find. Labels mean you can add or
remove lines freely and the assembler fixes every address for you. Words are also how
people *think* about programs, so this is the first step on the way to writing programs
in a proper language.

The real world works the same way. Every program on your phone began as text that a
translator turned into numbers. The first assemblers, written in the 1940s and 1950s,
were exactly this idea: let people write `ADD` instead of `0110`. Later in this climb we
build a compiler that writes assembly for us, and its output goes through the assembler
you just met.

## What's Next

You can now write programs in words and the machine can run them, but so far the machine
is the plain-Python fast engine. Next we start building the real thing out of gates. For
now, continue with [The Bench](the-bench.md), a workbench where you can look inside the
parts we have built.
