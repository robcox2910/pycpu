# Variables in Memory

## Pigeonholes Behind the Counter

Picture an old hotel with a wall of wooden pigeonholes behind the front desk, one little
box for each guest's post. The night clerk does not know any guest's name by heart.
What they do know is a rule: "Mr Ahmed's box is the first one below my hand, Ms Brook's
is the second, Dr Chen's is the third." So whenever someone asks for Ms Brook's post,
the clerk puts their hand on the row, counts down two boxes, and reaches in.

Now suppose a second clerk takes over for the night shift with a *different* list of
guests. They do not need a new wall. They put their hand somewhere else on the same
wall, below the first clerk's boxes, and use the very same rule: "first box below my
hand, second box below my hand". Neither clerk ever needs to know the real number of
any box.

A **variable** in a program is a name for a value that can change, like `apples` in
`let apples = 6`. The computer has no idea what a name is: its memory is just a long row
of numbered words, from [RAM](ram.md). So the translator turns every name into a
pigeonhole. All the pigeonholes for one piece of code sit together in a block of memory
called a **frame**. A register, `r7`, holds the address at the top of the frame, like
the clerk's hand on the row; it is called the **frame pointer**. And a name becomes
"so many words below `r7`": the first variable is `[r7-1]`, the second `[r7-2]`, and so on.

| The pigeonholes | In PyCPU |
|-----------------|----------|
| The wall of boxes | RAM, near the top of memory, where the stack lives |
| One box | A **slot**: one 16-bit word holding one variable |
| One clerk's set of boxes | A **frame**: the slots for one piece of code |
| The clerk's hand on the row | `r7`, the **frame pointer** |
| "Ms Brook is two boxes below my hand" | `b` is at `[r7-2]` |
| Reaching into a box to read | `load r1, [r7-2]` |
| Putting post into a box | `store r1, [r7-2]` |
| The guest list | `variables` in `subset.py`: the names, in the order they first appear |

## Try It

This program uses three variables. We print every line of its assembly that uses the
frame pointer, then run it and look at the very top of memory, where the frame was built.
(The memory has 4,096 words, numbered 0 to 4095, so the top word is 4095.)

```python
from pycpu.fast import FastMachine
from pycpu.translator import translate

source = """let a = 10
let b = 20
let c = a + b
print(c)"""

program = translate(source)
print("Every line that uses the frame pointer r7:")
for line in program.assembly.splitlines():
    if "r7" in line.split(";")[0]:
        print("   ", line.strip())

machine = FastMachine()
machine.load_program(program.program.words)
machine.run(10_000)
memory = machine.state().memory
print("The top of memory after the run:")
for address in range(4095, 4091, -1):
    print("   ", address, memory[address])
print("Printed:", "".join(chr(code) for code in machine.state().output), end="")
# Output:
# Every line that uses the frame pointer r7:
#     push r7                 ; keep the old frame pointer
#     getsp r7                ; r7 = the frame pointer: variables sit just below it
#     store r1, [r7-1]        ; a = r1
#     store r1, [r7-2]        ; b = r1
#     load r1, [r7-1]         ; r1 = a
#     load r1, [r7-2]         ; r1 = b
#     store r1, [r7-3]        ; c = r1
#     load r1, [r7-3]         ; r1 = c
# The top of memory after the run:
#     4095 0
#     4094 10
#     4093 20
#     4092 30
# Printed: 30
```

Look at the memory. Word 4095 holds 0: that is the old value of `r7`, saved so it could
be put back (at the start it is 0). Just below it, 4094 holds `a` (10), 4093 holds `b`
(20) and 4092 holds `c` (30). `a` is one below the hand, `b` two below, `c` three below,
exactly as the `load` and `store` lines say.

### Seeing Them in the Cockpit

The machine never learns the name `n`; only the translator knows it. So the translator
leaves a note for every word of machine code it writes: "when this word is about to run,
`r7` points at *this* frame, and here is where each name sits in it". That note is the
**frame map**. With it, the [Cockpit](the-cockpit.md) can do what the night clerk does:
put its hand where `r7` points, count along the row, and read each name's box.

Here a small Cockpit (256 words, every bit real gates) runs a countdown one instruction
at a time. Each time the program arrives at `print(n)`, line 3, we ask the Cockpit's
picture for its `variables`. We also peek once just after the program jumps into the
ready-made printing routine.

```python
from pycpu.cockpit.picture import machine_picture
from pycpu.cockpit.session import Cockpit
from pycpu.computer import StepSize

COUNTDOWN = """\
let n = 2
while n > 0 {
    print(n)
    n = n - 1
}
"""

cockpit = Cockpit(8)  # 256 words of memory, every bit real gates
cockpit.load_pebble(COUNTDOWN)
picture = machine_picture(cockpit)
print("first instruction:", picture["instruction"]["text"], "- variables:", picture["variables"])

line, visits = picture["pebble"]["line"], 0
while visits < 2:
    cockpit.step(StepSize.INSTRUCTION)
    picture = machine_picture(cockpit)
    if picture["pebble"]["line"] == 3 and line != 3:  # just arrived at print(n)
        visits += 1
        variables = picture["variables"]
        print("print(n) is next; the frame pointer r7 is", variables["frame_pointer"])
        for name in variables["names"]:
            print("   ", name["name"], "is at address", name["address"], "and holds", name["value"])
    if line == 3 and picture["pebble"]["line"] is None:  # just went into the print routine
        print("inside the print routine - variables:", picture["variables"])
    line = picture["pebble"]["line"]
print("printed so far", repr(picture["output"]))
# Output:
# first instruction: getsp r1 - variables: None
# print(n) is next; the frame pointer r7 is 255
#     n is at address 254 and holds 2
# inside the print routine - variables: None
# print(n) is next; the frame pointer r7 is 255
#     n is at address 254 and holds 1
# printed so far '2\n'
```

This memory has 256 words, so the top word is 255. Main's prologue saved the old `r7`
there and pointed `r7` at it, so `n`, one below the hand, is word 254. The first time we
reach `print(n)` it holds 2; the next time round the loop, 1.

Two answers are `None`, and both are on purpose. At the very first instruction the frame
does not exist yet: the prologue is still checking for room and building it, so there is
nothing safe to read. Inside the printing routine `r7` still holds main's address, but the
routine is not Pebble code and has no names of its own, so the Cockpit shows none rather
than pretend. The frame map says "not ready" for every word of a prologue, for the last
word of a `return` (by then `r7` has already been handed back to the caller), and for the
routines and the text.

## How It Works

The frame is built by the first few instructions of the program, the **prologue**,
written by `_prologue` in `src/pycpu/translator/codegen.py`. Before it runs, the stack
pointer `sp` is at the very top of memory (4096, one past the last word, from
[The Stack](the-stack.md)).

```
  push r7      keep the old frame pointer
  getsp r7     r7 = sp: the hand goes here
  push r0      a = 0     (r0 always holds 0)
  push r0      b = 0
  push r0      c = 0

  address    what is there                 how the code finds it
  -------    -------------                 ---------------------
   4095      old r7 (0)          <- r7      [r7]
   4094      a                              [r7-1]
   4093      b                              [r7-2]
   4092      c                              [r7-3]
   4091      Pebble's stack starts here     push and pop
     ...     (grows downwards)
```

Each `push r0` makes one slot and fills it with 0, so every variable starts out as a
clean 0 rather than whatever junk was in that word before. After that, the stack pointer
sits just below the last slot, and Pebble's own stack (the one from the last page,
holding numbers in the middle of a sum) grows down from there. The slots never move,
because `r7` never moves while the code runs; only `sp` goes up and down.

Which name gets which slot is decided by the translator, long before the program runs.
`subset.py` walks the bytecode and lists every name that is stored (`STORE_NAME`), in
the order they first appear. The first name on the list gets `[r7-1]`, the second
`[r7-2]`, and so on. After that, the name is gone: the machine code only ever says
`[r7-2]`. That is why a name *becomes* an address. The translator also writes a comment
like `; b = r1` so a person reading the assembly can still see which slot is which.

The translator keeps one more copy of that list for the Cockpit. `translate` gives back
a `TranslatedProgram` whose `frames` has one entry for every word of machine code: either
`None` (no frame is ready) or a `FrameLayout`, which names the function (`None` for the
top level) and lists a `Slot` for each name: its `name`, its `offset` from `r7` (such as
-1), its `kind` (`"parameter"` or `"variable"`) and whether it is `hidden`. The offsets
come from the very same table the code generator uses to write `[r7-1]`, so the map and
the code can never disagree.

The number after `r7` has to fit inside the instruction. `load` and `store` keep it in
6 bits, which can count from -32 to 31, so one frame can hold at most 32 variables, at
`[r7-1]` down to `[r7-32]`. A 33rd variable gets a friendly "more than 32 variables in
one function" error from the translator.

### Is there room?

Before it pushes anything, the prologue checks that the frame will fit. It adds up the
words the code could need: 1 for the old `r7`, 1 per variable, the deepest Pebble's stack
ever gets (the checker measures that while it walks the bytecode), and
`RUNTIME_STACK_WORDS` for the routines it calls. If the stack pointer is not at least
that far above `__end`, the label just after the program and its text, the machine stops
at once with `halt 2`, the **stack overflow** fault, *before* a single word of the
program could be overwritten. The Try It on the last page shows the check: it is the
`getsp r1` to `halt 2` lines at the top of the program.

## Why Does This Matter?

Why not give each variable a fixed address, like "`a` is always word 4094"? For one
piece of code that would work. But soon Pebble programs will have **functions**, pieces
of code that can be called many times, and even call *themselves*. Each call needs its
own `a`, and they must not trample each other. With a frame pointer, that is free: each
call builds its own frame lower down the stack and points `r7` at it, like the second
clerk using a lower part of the same wall, and `[r7-1]` means "my `a`" for whichever
call is running.

Every real language does this. When a debugger shows you "local variables", it is
reading the current frame, and a program that calls itself too deeply runs out of room
for frames, which is the famous **stack overflow** error that a well-known programming
question-and-answer website is named after.

**See it in the Cockpit.** The Cockpit has a guided walk about this page's idea, where the variable `n` lives in memory. Start the Cockpit first with `uv run python -m pycpu`, then open [the walk](http://127.0.0.1:8765/#walk=where-n-lives).

## What's Next

Each slot holds one 16-bit word, so a variable can only count so high. Find out what
happens when it goes past the top, and why PyCPU and Pebble disagree about it, in
[Why 16-Bit Numbers Wrap](why-16-bit-numbers-wrap.md).
