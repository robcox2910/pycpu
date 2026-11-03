# If and While as Jumps

## A Choose-Your-Own-Adventure Book

Have you ever read a choose-your-own-adventure book? You read page 12, and at the
bottom it says: "If you have the golden key, turn to page 40. Otherwise, read on." A
few pages later: "The tunnel loops round. Go back to page 12." The book is printed in
one long line of pages, page 1 to page 100, yet the story can split into different
paths and even go round in circles. All it takes is two kinds of instruction at the
bottom of a page: "turn to page N" and "*if* something is true, turn to page N".

A computer program is the same. A Pebble program is written as one long list of lines,
and its bytecode (from [From Pebble to Machine Code](from-pebble-to-machine-code.md)) is
one long numbered list of instructions. PyCPU's memory is one long row of words. There
is no "if" and no "while" in the hardware at all. There are only **jumps**: an
instruction that says "the next instruction to run is over *there*", which works by
changing the program counter (the register that holds the address of the next
instruction, from [Fetch, Decode, Execute](fetch-decode-execute.md)).

An `if` is a jump that skips a block of the program when its **condition** (the yes/no
question, such as `n > 0`) is false. A `while` is a **loop**: a block that ends with "go
back to page 12", where page 12 asks the question again.

| The adventure book | In Pebble's bytecode | On PyCPU |
|--------------------|----------------------|----------|
| A page number | An instruction's position in the list (its **index**, counting from 0) | A **label** such as `__main_2`, which becomes an address |
| "Turn to page 40" | `JUMP 40` | `jmp __main_40` |
| "If you do NOT have the key, turn to page 40" | `JUMP_IF_FALSE 40` | `cmp r1, r0`, then a `br` and a `jmp` |
| "Do you have the key?" | A comparison such as `GREATER_THAN` | `cmp r1, r2` and a `br` that reads the flags |
| "Go back to page 12" | `JUMP 12`, to an earlier index | `jmp __main_12`: a loop |
| "If you have the key AND the lamp..." | `JUMP_IF_FALSE_OR_POP` | Skip the second question if the first says no |

## Try It

A rocket countdown: a `while` loop with an `if`/`else` inside it. We print Pebble's
bytecode with the index of every instruction, so you can follow the jumps, then run the
program on Pebble's own VM and on PyCPU.

```python
from pebble import compile_source, run_source

from pycpu.translator import run_pebble

source = """let n = 3
while n > 0 {
    if n == 1 {
        print("one more...")
    } else {
        print(n)
    }
    n = n - 1
}
print("lift off!")"""

code = compile_source(source).compiled.main
for index, instruction in enumerate(code.instructions):
    operand = "" if instruction.operand is None else instruction.operand
    if instruction.opcode == "LOAD_CONST":
        operand = repr(code.constants[instruction.operand])
    print(f"{index:3}  {instruction.opcode} {operand}".rstrip())
print("Pebble VM:", run_source(source).splitlines())
print("PyCPU:    ", run_pebble(source).output.splitlines())
# Output:
#   0  LOAD_CONST 3
#   1  STORE_NAME n
#   2  LOAD_NAME n
#   3  LOAD_CONST 0
#   4  GREATER_THAN
#   5  JUMP_IF_FALSE 20
#   6  LOAD_NAME n
#   7  LOAD_CONST 1
#   8  EQUAL
#   9  JUMP_IF_FALSE 13
#  10  LOAD_CONST 'one more...'
#  11  PRINT
#  12  JUMP 15
#  13  LOAD_NAME n
#  14  PRINT
#  15  LOAD_NAME n
#  16  LOAD_CONST 1
#  17  SUBTRACT
#  18  STORE_NAME n
#  19  JUMP 2
#  20  LOAD_CONST 'lift off!'
#  21  PRINT
#  22  HALT
# Pebble VM: ['3', '2', 'one more...', 'lift off!']
# PyCPU:     ['3', '2', 'one more...', 'lift off!']
```

Look for the jumps, and treat each index as a page number. Instructions 2 to 4 ask the
`while`'s question, `n > 0`. At index 5, `JUMP_IF_FALSE 20` says "if the answer is
false, turn to page 20", which is just past the end of the loop, where "lift off!" is
printed. At index 19, the last instruction of the loop, `JUMP 2` says "go back to page
2", where `n > 0` is asked again. That backwards jump is what makes it a loop.

The `if` inside works the same way. `JUMP_IF_FALSE 13` at index 9 skips the "one
more..." block when `n == 1` is false, landing on the `else` block at 13. And `JUMP 15`
at the end of the "one more..." block skips *over* the `else` block, so only one of the
two blocks ever runs. There is no `else` instruction at all: just a jump round it.

Now look at the cards the translator writes for a loop's question. This time the loop
is shorter, so it ends at index 12 with `JUMP 2`, and the instruction after the loop is
13. We cut the assembly from the label `__main_2` (instruction 2, the top of the loop)
up to the first instruction inside the loop, then find the jump at the bottom:

```python
from pycpu.translator import translate

source = """let n = 3
while n > 0 {
    print(n)
    n = n - 1
}"""

lines = translate(source).assembly.splitlines()
start = lines.index("__main_2:")
stop = lines.index("    ; line 3: LOAD_NAME n")
print("\n".join(lines[start:stop]))
for line in lines:
    if "JUMP 2" in line or "jmp  __main_2" in line:
        print(line)
# Output:
# __main_2:
#     ; line 2: LOAD_NAME n
#     load r1, [r7-1]         ; r1 = n
#     push r1                 ; onto the stack
#     ; line 2: LOAD_CONST 0
#     li   r1, 0              ; r1 = 0
#     push r1                 ; onto the stack
#     ; line 2: GREATER_THAN
#     pop  r2                 ; r2 = the right-hand number
#     pop  r1                 ; r1 = the left-hand number
#     li   r3, 1              ; r3 = 1 (true), unless we find otherwise
#     cmp  r1, r2             ; work out r1 - r2, keeping only the flags
#     br   gt, __main_yes_4   ; is r1 > r2? then keep the 1
#     li   r3, 0              ; no: r3 = 0 (false)
# __main_yes_4:
#     push r3                 ; true or false goes on the stack
#     ; line 2: JUMP_IF_FALSE 13
#     pop  r1                 ; r1 = the condition
#     cmp  r1, r0             ; is it 0 (false)?
#     br   ne, __main_go_on_5 ; no, it is true: carry on
#     jmp  __main_13          ; yes, false: go to instruction 13
# __main_go_on_5:
#     ; line 2: JUMP 2
#     jmp  __main_2           ; go to instruction 2
```

Read it from the top. `__main_2:` is the page number for instruction 2. `n` and `0` go
on the stack. `GREATER_THAN` pops them, compares them, and leaves a 1 (true) or a 0
(false) on the stack. `__main_yes_4` is a little label of its own, used only for
instruction 4's short hop over `li r3, 0`. Then `JUMP_IF_FALSE 13` pops that 1 or 0 and,
if it is 0, jumps to `__main_13`, past the loop. The very last card of the loop, `jmp
__main_2`, sends the machine back up to the question. The `JUMP 2` comment says line 2
because Pebble counts the jump back as part of the `while` line.

`and` and `or` take a short cut, just as they do on Pebble's VM: if the left side
already decides the answer, the right side is never worked out at all. Below, `z` is 0,
so `10 // z` would stop the machine with a divide-by-zero fault, but it never runs. And
a true/false value can only be used to make a decision; storing or printing one is
refused politely:

```python
from pycpu.translator import UnsupportedFeature, run_pebble

source = """let z = 0
if z != 0 and 10 // z > 1 {
    print(1)
} else {
    print(2)
}
let x = 0 or 5
print(x)"""
print(run_pebble(source).output.split())

for source in ["let a = 4\nlet big = a > 2", "let a = 4\nprint(a == 4)"]:
    try:
        run_pebble(source)
    except UnsupportedFeature as error:
        print(error)
# Output:
# ['2', '5']
# true and false outside if and while are not supported on PyCPU yet at line 2, column 13
# true and false outside if and while are not supported on PyCPU yet at line 2, column 9
```

The first program prints 2 (the `else` block ran, and nothing divided by zero) and then
5. The refusals point at the comparison itself: column 13 of `let big = a > 2` is the
`>`, and column 9 of `print(a == 4)` is the `==`.

## How It Works

The translator lives in `src/pycpu/translator/codegen.py`. Every bytecode instruction
still becomes a few cards on its own, exactly as on
[From Pebble to Machine Code](from-pebble-to-machine-code.md). Jumps add one new idea:
**labels for page numbers**.

**Step 1: a label for every page someone turns to.** Before writing anything, the
translator looks at every jump and collects the indexes they go to. Each of those
instructions gets a label in front of its cards: instruction 2 of `main` is `__main_2:`.
The assembler (from [Assembly Language](assembly-language.md)) later turns every label
into the address of the word that follows it, so `jmp __main_2` becomes "jump to address
so-and-so" without anyone counting words.

```
  Pebble bytecode              PyCPU assembly
  ---------------              --------------
                               __main_2:              <- a label: "this is page 2"
   2  LOAD_NAME n      ---->       load r1, [r7-1]
                                   push r1
   3  LOAD_CONST 0     ---->       ...
   4  GREATER_THAN     ---->       ... cmp, br gt ...  leaves 1 or 0 on the stack
   5  JUMP_IF_FALSE 13 ---->       ... jmp __main_13  "if it was 0, turn to page 13"
   6 ... 11  (the loop's body)     ...
  12  JUMP 2           ---->       jmp __main_2       "go back to page 2"
                               __main_13:             <- "this is page 13"
  13  HALT             ---->       halt 0
```

**Step 2: a comparison becomes `cmp` and a branch.** PyCPU has no "greater than"
instruction. It has `cmp r1, r2`, which works out `r1 - r2` in the ALU, throws the
answer away and keeps only the **flags** (the four yes/no lamps from
[The ALU](the-alu.md)). Then `br gt, somewhere` reads the lamps and branches only if
they say "the first number was bigger". So `n > 0` becomes: put a 1 in `r3` ("true"),
compare, and if the flags say *greater*, jump past the line that would change `r3` to 0.
Whatever is left in `r3`, 1 or 0, goes on the stack, because PyCPU has no true or false
either: **a word is false when it is 0**, and true otherwise.

The six comparisons use six branch conditions: `<` is `lt`, `<=` is `le`, `>` is `gt`,
`>=` is `ge`, `==` is `eq` and `!=` is `ne`. These are the **signed** conditions, the
ones that know `-1` is smaller than `1`. They do not just look at the sign of `r1 - r2`:
if the subtraction overflowed (from
[Why 16-Bit Numbers Wrap](why-16-bit-numbers-wrap.md)), the sign is upside down, so `lt`
asks "is *negative* different from *overflow*?". That is why `-30000 < 30000` is still
true, even though `-30000 - 30000` wraps round to a positive number.

**Step 3: `JUMP_IF_FALSE` takes the condition off the stack and jumps if it is 0.**
You might expect one card, `br eq, __main_13`. But a `br` can only hop 255 words
forwards or 256 back (it has only 9 bits for the distance, from
[Assembly Language](assembly-language.md)), and the body of a loop can easily be longer
than that. So the translator branches *over* a `jmp`, which can reach any address: "if
the condition is not 0, hop over the next card; otherwise, `jmp` to page 13".

**Step 4: `not` swaps 0 and 1.** `not c` puts a 1 in a register, compares `c` with 0,
and keeps the 1 only if `c` was 0.

**Step 5: `and` and `or` skip the right side.** Pebble compiles `a and b` as:

```
   a                         work out the left side
   JUMP_IF_FALSE_OR_POP L    if it is false, it IS the answer: keep it, turn to L
   b                         otherwise throw it away and work out the right side
 L:                          whichever value is on the stack is the answer
```

`or` is the same with `JUMP_IF_TRUE_OR_POP`. On PyCPU that is: pop the left side,
compare it with 0, and either push it back and `jmp` to `L`, or carry on into the right
side. Because the jump goes *past* the right side's cards, those cards never run, and
`10 // z` above never divides by zero.

**Step 6: checking kinds along every path.** Before any of this, the subset check in
`src/pycpu/translator/subset.py` plays the program through without running it, keeping
the **kind** of every value on the stack (a number, true/false or text). With jumps,
there is more than one way to reach an instruction, so it keeps a to-do list: start at
instruction 0; after each instruction, add every instruction that could come next (both
pages, for a jump that might or might not be taken); and when two paths meet, mix their
kinds. If one path brings a number and the other a true/false, the result counts as a
true/false, so it is treated as carefully as one. It stops when no path brings anything
new. Pebble's compiler promises that every
path reaches a meeting point with the same number of values on the stack.

**Why true and false stay inside conditions.** On a 16-bit machine, `true` is stored as
the word 1, and the number 1 is also stored as the word 1. Once a value is in memory,
nothing says which one it was. If PyCPU let you write `let big = a > 2` and then
`print(big)`, it could only print `1`, where Pebble's VM prints `true`. Rather than
print the wrong thing, the translator lets true/false be *made* and *used for a
decision*, but refuses to store, print or calculate with one. A number in a condition is
fine, though: `let x = 0 or 5` keeps whichever number decides the answer, and prints 5
on both machines.

**What about `for`?** Pebble's compiler turns `for i in range(3) { ... }` into a
`while` loop before PyCPU ever sees it: it stores the limit in a hidden variable called
`$for_limit_0` (the `$` means "the compiler made this, you cannot type it"), sets `i` to
0, and loops while `i < $for_limit_0`, adding 1 to `i` at the end of each pass. Every
instruction in that is one this page has already translated, so `for` loops over
`range` just work. The hidden variable gets a slot in the frame like any other.

## Why Does This Matter?

Without jumps, a program could only run from top to bottom once, the same way every
time: it could never react to anything, or repeat anything. Every `if`, `while`,
`for`, every game loop and every menu you have ever used is a jump underneath. Even the
fanciest languages compile their loops to "compare, then branch", exactly like this.

Real compilers are a little cleverer than ours. A comparison followed straight away by
a `JUMP_IF_FALSE` is so common that a real compiler skips making the 1 or 0 and branches
straight from the flags. Ours keeps every Pebble instruction separate, so you can always
find the cards for each one in the assembly. The short cut that `and` and `or` take is
not just for speed, either: programmers rely on it every day, writing things like
`z != 0 and 10 // z > 1` so the risky part only runs when it is safe.

## What's Next

You have seen `__mul` and `__divmod` at work in these programs. Find out how a machine
with no multiply or divide instruction builds them out of shifting and adding, in
[Multiply and Divide](multiply-and-divide.md).
