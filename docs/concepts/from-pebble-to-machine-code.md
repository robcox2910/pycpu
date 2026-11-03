# From Pebble to Machine Code

## Translating a Recipe, Card by Card

Your gran has a recipe book written in Italian, and you want the cook at the café round
the corner to make her lasagne. The cook does not read Italian. In fact the cook only
reads a strange number code: card 12 means "take the next thing out of the cupboard",
card 30 means "stir the top two bowls together", and so on.

So you hire a translator. The translator does not cook anything. They go through the
recipe one line at a time, and for each line they write a few number cards that mean the
same thing. "Mix the flour and the eggs" might become three cards. When they finish, the
cook gets a neat pile of cards and can make the lasagne without knowing a word of Italian.

The translator does one more clever thing. On the back of every card they pencil the
recipe line it came from: "this card is from line 4". If the cook gets stuck ("I've run
out of eggs!"), anyone can turn the card over and see *which line of gran's recipe* was
being made when it went wrong.

That is exactly what this page builds. The recipe is a program in **Pebble**, the small
programming language from the same from-scratch series. The cook is PyCPU, which only
understands [machine code](machine-code.md). And the translator is a new part of the
project, called, well, the **translator**: it reads a Pebble program and writes
[assembly language](assembly-language.md) for it, which the assembler then turns into
machine code.

Pebble helps us a lot here, because it already does half the job. Pebble has its own
**compiler**, a program that reads Pebble text and turns it into a list of very simple
orders called **bytecode**. Bytecode is like a recipe that has been rewritten as a
numbered list of tiny steps, each one so small that it is nearly a machine instruction
already. Our translator only has to turn each bytecode step into a few PyCPU instructions.

| The recipe and the cook | In PyCPU |
|-------------------------|----------|
| Gran's recipe in Italian | A Pebble program, such as `print(apples * 7)` |
| The recipe rewritten as tiny numbered steps | Pebble's **bytecode**, made by `compile_source` |
| One tiny step, like "stir the top two bowls" | One bytecode instruction, such as `MULTIPLY` |
| The translator | `translate`, in `src/pycpu/translator/` |
| The number cards for one step | A few lines of PyCPU **assembly** |
| The pencil note on the back of each card | `pebble_lines`: the Pebble line of every machine word |
| The cook making the dish | `run_pebble`: the fast engine running the machine code |

## Try It

This little program sets a variable and prints a sum. We look at it three ways: as
Pebble's bytecode, as the assembly our translator writes for it, and as what comes out
when PyCPU runs it. (`split` cuts the assembly where the shared routines start, so we
only see the part written for this program.)

```python
from pebble import compile_source

from pycpu.translator import run_pebble, translate

source = "let apples = 6\nprint(apples * 7)"

code = compile_source(source).compiled.main
print("Constants:", code.constants)
print("Bytecode:")
for instruction in code.instructions:
    operand = "" if instruction.operand is None else instruction.operand
    print("   ", instruction.opcode, operand)

program = translate(source)
print(program.assembly.split("; ==== runtime")[0].strip())
print("Words for this program:", program.program.labels["__mul"])
print("Words in all, with the routines:", len(program.program.words))
print("It printed:", run_pebble(source).output, end="")
# Output:
# Constants: [6, 7]
# Bytecode:
#     LOAD_CONST 0
#     STORE_NAME apples
#     LOAD_NAME apples
#     LOAD_CONST 1
#     MULTIPLY
#     PRINT
#     HALT
# ; ==== main: the Pebble program's own code ====
# __main:
#     ; make the frame: 1 word for the old r7, 1 for variables, 2 for the stack, 9 for the routines
#     getsp r1                ; r1 = the top of the stack, where the frame starts
#     set  r2, __end          ; r2 = the first free word after the program
#     li   r3, 13             ; r3 = the 13 words this code may need
#     add  r2, r2, r3         ; r2 = the lowest the stack may start from
#     cmp  r1, r2             ; is there room?
#     br   geu, __main_room   ; yes: carry on
#     halt 2                  ; no: STACK_OVERFLOW, before anything is overwritten
# __main_room:
#     push r7                 ; keep the old frame pointer
#     getsp r7                ; r7 = the frame pointer: variables sit just below it
#     push r0                 ; apples = 0, at [r7-1]
#     ; line 1: LOAD_CONST 6
#     li   r1, 6              ; r1 = 6
#     push r1                 ; onto the stack
#     ; line 1: STORE_NAME apples
#     pop  r1                 ; r1 = the value on top of the stack
#     store r1, [r7-1]        ; apples = r1
#     ; line 2: LOAD_NAME apples
#     load r1, [r7-1]         ; r1 = apples
#     push r1                 ; onto the stack
#     ; line 2: LOAD_CONST 7
#     li   r1, 7              ; r1 = 7
#     push r1                 ; onto the stack
#     ; line 2: MULTIPLY
#     pop  r2                 ; r2 = the right-hand number
#     pop  r1                 ; r1 = the left-hand number
#     call __mul              ; r1 = r1 * r2
#     push r1                 ; the answer goes on the stack
#     ; line 2: PRINT
#     pop  r1                 ; r1 = the thing to print
#     call __print_int        ; print it and a newline
#     ; line 2: HALT
#     halt 0                  ; the program has finished
# Words for this program: 26
# Words in all, with the routines: 122
# It printed: 42
```

The bytecode is seven tiny steps. A **constant** is a value written straight into the
program, like the `6` and the `7`; Pebble keeps them in a numbered list. `LOAD_CONST 0`
means "put constant number 0 on the stack", and the list says constant 0 is `6`. Then each step becomes a few
lines of assembly, and above each group a comment such as `; line 2: MULTIPLY` says
which Pebble step and which Pebble line it was written for. The routines are placed
right after the program, so the address of the first one, `__mul`, is also the size of
the program's own part: only 26 words; the rest of the 122 are the ready-made routines for multiplying,
dividing and printing that every translated program carries along.

Not every Pebble program can be translated yet. When something is outside what PyCPU
can do, the translator says what and where, instead of crashing or printing nonsense:

```python
from pycpu.translator import UnsupportedFeature, translate

for source in ['let name = "Ada"', "let half = 1.5", "let a = 7\nprint(a / 2)"]:
    try:
        translate(source)
    except UnsupportedFeature as error:
        print(error)
# Output:
# text outside print is not supported on PyCPU yet at line 1, column 12
# decimal numbers are not supported on PyCPU yet at line 1, column 12
# the / operator (it always makes a decimal number; use // for whole numbers) is not supported on PyCPU yet at line 2, column 9
```

## How It Works

The translator lives in `src/pycpu/translator/`. `translate`, in `program.py`, passes the
program along a short line of workers, like a recipe passing along a counter:

```
  Pebble text            let apples = 6
                         print(apples * 7)
       |
       |  compile_source    Pebble's own compiler (not ours)
       v
  bytecode               LOAD_CONST 0, STORE_NAME apples, ...
       |
       |  check_program     subset.py: is everything something PyCPU can do?
       v
  checked bytecode       plus notes: which names are variables, how deep the stack gets
       |
       |  generate          codegen.py: a few lines of assembly per bytecode step
       v
  assembly text          li   r1, 6
                         push r1
                         ...
       |
       |  assemble          the assembler from Assembly Language
       v
  machine code           122 words, and the Pebble line of every word
```

### Pebble thinks in stacks

Pebble's bytecode is written for a **stack machine**: every step takes what it needs off
the top of a stack and puts its answer back on top. To work out `apples * 7`, it puts
`apples` on the stack, puts `7` on the stack, then `MULTIPLY` takes both off and puts
back the answer:

```
  LOAD_NAME apples     LOAD_CONST 7       MULTIPLY          PRINT
                       +-----+
                       |  7  |  <- top
  +-----+              +-----+            +-----+
  |  6  |              |  6  |            | 42  |           (empty)
  +-----+              +-----+            +-----+           prints 42
```

PyCPU already has a stack, from [The Stack](the-stack.md), with `push` and `pop`. So the
big idea of the translator is simple: **Pebble's stack becomes the real stack.** Every
"put on the stack" becomes a `push`, and every "take off the stack" becomes a `pop`.
Between two steps no value is left lying in a register: everything waits on the stack.
That makes every step's cards the same wherever the step appears.

| Bytecode step | The cards the translator writes |
|---------------|---------------------------------|
| `LOAD_CONST` (a number) | `li r1, 6` (or `set` for a big one), then `push r1` |
| `LOAD_NAME apples` | `load r1, [r7-1]`, then `push r1` |
| `STORE_NAME apples` | `pop r1`, then `store r1, [r7-1]` |
| `ADD`, `SUBTRACT` | `pop r2`, `pop r1`, `add r1, r1, r2` (or `sub`), `push r1` |
| `MULTIPLY` | `pop r2`, `pop r1`, `call __mul`, `push r1` |
| `FLOOR_DIVIDE` (`//`), `MODULO` (`%`) | the same, but check `r2` is not 0 first, then `call __divmod` |
| `NEGATE` (a minus sign in front) | `pop r1`, `sub r1, r0, r1`, `push r1` |
| `PRINT` | `pop r1`, then `call __print_int` (or `__print_text` for text) |
| `POP` (a value nobody needs) | `pop r1`, and forget it |
| `HALT` | `halt 0` |

The right-hand number is on top of the stack, so it comes off first, into `r2`. The
`[r7-1]` is where the variable lives in memory; the next page is all about that. The
multiply, divide and print routines are the ones from
[Multiply and Divide](multiply-and-divide.md) and [Printing a Number](printing-a-number.md),
coming up in this section.

### Text is a list of letters in memory

`print("hello")` cannot push five letters into one register. Instead the translator puts
the text after the program, one character code per word, with a 0 at the end, and gives
it a label such as `__str_0`. The bytecode step `LOAD_CONST "hello"` becomes
`set r1, __str_0` and `push r1`: what goes on the stack is the *address* of the text, and
`PRINT` hands that address to `__print_text`, which posts the letters one by one. Text
can only be printed for now; that is why `let name = "Ada"` was refused above.

### The pencil notes: a source map

While it writes, the code generator tags every line of assembly with the Pebble line it
came from. The assembler already remembers which assembly line made each word, so
putting the two together gives `pebble_lines`, one entry per machine word, and
`line_at(address)` to look one up. The routines and the text belong to no Pebble line,
so their entry is `None`. This list is called a **source map**, and it is how, later,
the machine can tell you "it went wrong on line 3 of your Pebble program" rather than
only "it went wrong at some address".

### Pebble does some sums before we see them

Pebble's compiler is clever. If you write `print(1 + 2 * 3)`, it works out the answer
while compiling, and the bytecode is just `LOAD_CONST 7` and `PRINT`. Sums made only
of numbers you wrote down never reach the CPU at all. That is why the Try It keeps 6 in
a variable called `apples`: it makes the CPU do the multiplying itself.

### The checker comes first

Before any cards are written, `check_program` in `subset.py` looks at every bytecode
step, the way a customs officer checks every suitcase. It plays the program through
without running it, keeping track of what *kind* of thing each stack slot holds: a
number, `true` or `false`, a piece of text, or nothing. Then it knows that `PRINT` of a
text needs `__print_text`, and that `let name = "Ada"` would store text in a variable,
which PyCPU cannot do yet. If it finds several problems, it reports the one nearest the
top of the program, with its line and column, as an `UnsupportedFeature` error.

## Why Does This Matter?

Without a translator, the only way to program PyCPU is to write every `push` and `pop`
yourself. With it, a learner writes `print(apples * 7)` and the machine works out the
rest, and every card it wrote is still there to read.

This is how many real languages run too. Java and WebAssembly (the language that runs
fast code inside web browsers), for example, compile programs into stack bytecode
first. Then a part called a **JIT compiler** ("just in time") translates the bytecode
into the real machine code of your computer's processor while the program runs, often
step by step much as ours does. (Standard Python makes stack bytecode too, but mostly
follows it one step at a time with a **VM**, a "virtual machine": a program that obeys
bytecode itself, the way Pebble's own VM does, instead of translating it.) And every debugger that shows you "the error is on line 12"
is reading a source map like `pebble_lines`.

## What's Next

Every variable above turned into something like `[r7-1]`. Find out what that means, and
why a name becomes an address, in [Variables in Memory](variables-in-memory.md).
