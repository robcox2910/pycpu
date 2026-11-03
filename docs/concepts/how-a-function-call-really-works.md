# How a Function Call Really Works

## Leaving Your Desk to Help a Friend

You are doing your homework at a desk in the library, and a friend at another desk calls
over: "can you work something out for me?" Before you go, you do three things. You leave
the numbers your friend needs on a tray between the desks. You write a note saying
exactly where you were ("maths, question 4, halfway down"). And when you sit at your
friend's desk, you clear a corner of it for your own scribbling, so you never mess up
their papers. When you have the answer, you put it on the tray, throw away your
scribbles, read your note, and walk back to exactly where you were. Your friend picks the
answer up from the tray.

Now imagine your friend's question makes *you* ask a third friend for help, and that
friend asks a fourth. Each one leaves a tray, a note and a cleared corner. As long as
everyone walks back in the right order, nobody gets lost, however long the chain is.

A Pebble **function** (a named piece of code you can use again and again, like
`fn double(n) { return n * 2 }`) works exactly like that on PyCPU. The numbers you hand
to it are its **arguments**. Inside the function they have names, its **parameters**
(here `n`). The tray, the note and the cleared corner together are the function's
**frame**, the block of memory from [Variables in Memory](variables-in-memory.md), and
the answer it hands back is its **return value**. A function that calls *itself* is
called **recursion**, and it is just a long chain of friends who all happen to be doing
the same job.

| At the library | In Pebble | On PyCPU |
|----------------|-----------|----------|
| The numbers left on the tray | The **arguments**, such as the `3` in `double(3)` | Words the caller pushes, which sit at `[r7+2]`, `[r7+3]`, ... |
| The note saying where you were | (hidden) | The **return address**, pushed by `call`, at `[r7+1]` |
| Remembering whose desk you came from | (hidden) | The caller's frame pointer, the **old `r7`**, at `[r7]` |
| Your cleared corner | The function's own variables | Slots at `[r7-1]`, `[r7-2]`, ... made by the prologue |
| The answer on the tray | `return n * 2` | The value in `r1` when `ret` runs |
| Walking back | The function ends | `setsp r7`, `pop r7`, `ret` |
| A chain of friends | **Recursion**: a function calling itself | A pile of frames, each lower down the stack |
| The library running out of desks | Too much recursion | `halt 2`: **stack overflow** |

## Try It

The program below calls `double` three times in a loop. We run it on Pebble's own VM and
on PyCPU, then print the cards the translator wrote for the call in `main` and for the
whole of `double`:

```python
from pebble import run_source

from pycpu.translator import run_pebble, translate

source = """fn double(n) {
    return n * 2
}
let i = 3
while i > 0 {
    print(double(i))
    i = i - 1
}"""

print("Pebble VM:", run_source(source).split())
print("PyCPU:    ", run_pebble(source).output.split())
lines = translate(source).assembly.splitlines()
call = lines.index("    ; line 6: CALL double")
print("\n".join(lines[call : call + 6]))
start = lines.index("__fn_double:")
stop = lines.index("; ==== runtime: the ready-made routines for multiply, divide and print ====")
print("\n".join(lines[start:stop]))
# Output:
# Pebble VM: ['6', '4', '2']
# PyCPU:     ['6', '4', '2']
#     ; line 6: CALL double
#     call __fn_double        ; go to double, leaving the return address on the stack
#     getsp r2                ; r2 = the top of the stack
#     addi r2, 1              ; step over the 1 argument
#     setsp r2                ; the argument is thrown away
#     push r1                 ; the answer double gave back goes on the stack
# __fn_double:
#     ; make the frame: 1 word for the old r7, 0 for variables, 2 for the stack, 9 for the routines
#     getsp r1                ; r1 = the top of the stack, where the frame starts
#     set  r2, __end          ; r2 = the first free word after the program
#     li   r3, 12             ; r3 = the 12 words this code may need
#     add  r2, r2, r3         ; r2 = the lowest the stack may start from
#     cmp  r1, r2             ; is there room?
#     br   geu, __fn_double_room ; yes: carry on
#     halt 2                  ; no: STACK_OVERFLOW, before anything is overwritten
# __fn_double_room:
#     push r7                 ; keep the old frame pointer
#     getsp r7                ; r7 = the frame pointer: variables sit just below it
#     ; line 2: LOAD_NAME n
#     load r1, [r7+2]         ; r1 = n
#     push r1                 ; onto the stack
#     ; line 2: LOAD_CONST 2
#     li   r1, 2              ; r1 = 2
#     push r1                 ; onto the stack
#     ; line 2: MULTIPLY
#     pop  r2                 ; r2 = the right-hand number
#     pop  r1                 ; r1 = the left-hand number
#     call __mul              ; r1 = r1 * r2
#     push r1                 ; the answer goes on the stack
#     ; line 2: RETURN
#     pop  r1                 ; r1 = the value to give back
#     setsp r7                ; drop the variables and the stack in one go
#     pop  r7                 ; get the caller's frame pointer back
#     ret                     ; go back to the caller
```

Before the `CALL`, `main` has already pushed `i`, the argument: that is the tray. `call
__fn_double` pushes the return address (the note) and jumps. `double` starts with the
same prologue `main` has: check there is room, push the old `r7`, point `r7` at it.
Then `n` is not *below* `r7` like a variable; it is *above*, at `[r7+2]`, because the
caller put it there before the call. Look at the last four cards: the answer goes into
`r1`, the frame is thrown away, the old `r7` comes back, and `ret` walks back to `main`,
which drops the argument and pushes the answer for `print`.

Now recursion. `fact(n)` (short for *factorial*) multiplies `n` by `fact(n - 1)`, so
`fact(4)` is 4 × 3 × 2 × 1. We print the factorials up to 7, and then stop the machine
at the moment the frame pointer is at its lowest, inside `fact(1)` when `main` asked for
`fact(3)`, and print every word on the stack:

```python
from pebble import run_source

from pycpu.fast import FastMachine
from pycpu.translator import run_pebble, translate

fact = """fn fact(n) {
    if n <= 1 {
        return 1
    }
    return n * fact(n - 1)
}
"""
source = fact + "let i = 1\nwhile i <= 7 {\n    print(fact(i))\n    i = i + 1\n}"
print("Pebble VM:", run_source(source).split())
print("PyCPU:    ", run_pebble(source).output.split())

machine = FastMachine()
machine.load_program(translate(fact + "print(fact(3))").program.words)
deepest = machine.state()
lowest = 4096  # higher than any address, so the first frame is lower
while machine.step():
    state = machine.state()
    if 0 < state.registers[7] < lowest:  # r7 is 0 until main makes its frame
        lowest = state.registers[7]
        deepest = state
for address in range(4095, deepest.sp - 1, -1):
    mark = "  <- r7" if address == deepest.registers[7] else ""
    print(address, deepest.memory[address], mark)
# Output:
# Pebble VM: ['1', '2', '6', '24', '120', '720', '5040']
# PyCPU:     ['1', '2', '6', '24', '120', '720', '5040']
# 4095 0
# 4094 3
# 4093 13
# 4092 4095
# 4091 3
# 4090 2
# 4089 62
# 4088 4092
# 4087 2
# 4086 1
# 4085 62
# 4084 4088   <- r7
```

Read it from the top, the oldest word first. 4095 is `main`'s old `r7` (0: nobody called
`main`). 4094 is the argument 3, and 4093 is the note: the address in `main` to come back
to. 4092 is `fact(3)`'s frame, holding `main`'s `r7`. Below it, `fact(3)` was in the
middle of `n * fact(n - 1)`: its `n` (3) waits on the stack, then the argument 2 for the
next call, then the note, then `fact(2)`'s frame. The same pattern happens once more for
`fact(1)`. Every `fact` call has its own `n`, so they never mix up, and both return
addresses are the same word, 62, because both calls come from the same place in `fact`.

What if a function calls itself forever? Each call of the `f` below takes 3 more words
(its argument, the return address and the old `r7`), and the stack grows down towards
the program. The prologue's room check stops the machine just before it gets there:

```python
from pycpu.translator import run_pebble

run = run_pebble("fn f(n) {\n    return f(n + 1)\n}\nprint(f(0))")
print(repr(run.fault), "at line", run.line)
# Output:
# <Fault.STACK_OVERFLOW: 2> at line 2
```

The machine stopped itself with fault code 2, **stack overflow**, and the translator's
source map points at line 2, where the call `f(n + 1)` that found no room sits. (How
the line is found is told in [What Happens When Things Go
Wrong](what-happens-when-things-go-wrong.md).) Nothing was printed, and nothing
in the program was overwritten. Pebble's own VM keeps its frames in a Python list with
no limit, so on the VM this program just keeps going (we gave up
waiting). PyCPU's memory is only 4,096 words, so it finds out much sooner.

## How It Works

The code lives in `src/pycpu/translator/codegen.py` (the cards) and
`src/pycpu/translator/subset.py` (the checks). The machine already has the two
instructions a function needs, `call` and `ret`, from
[Calling and Returning](calling-and-returning.md). The translator's job is to agree on
*where everything goes*, so that a caller and a function that never see each other's
code still find each other's numbers.

**Step 1: the caller leaves the arguments on the tray.** Pebble's compiler already
pushes the arguments, left to right, before its `CALL` instruction, so on PyCPU they are
simply pushed onto the real stack. Then `call` pushes the return address and jumps to the
function's label. Every function gets a label starting `__fn_`, such as `__fn_double`, so
it can never clash with `main`'s labels or the runtime's.

**Step 2: the function builds its frame.** It runs the same prologue as `main` (from
[Variables in Memory](variables-in-memory.md)): check there is room, push the old `r7`,
set `r7` to the stack pointer, push a zero for each of its own variables. Now everything
is a fixed distance from `r7`. For `fn add3(a, b, c)` with one variable `t`, while
`main` calls `add3(10, 20, 30)`:

```
  address   what is there                 how add3 finds it
  -------   -------------                 -----------------
   4094     a = 10    (pushed first)      [r7+4]
   4093     b = 20                        [r7+3]
   4092     c = 30    (pushed last)       [r7+2]
   4091     return address  (by call)     [r7+1]
   4090     main's r7       (by push r7)  [r7]      <- r7
   4089     t                             [r7-1]
   4088     add3's own stack grows down from here
```

The last argument is nearest to `r7`, because it was pushed last. So parameter `i` of a
function with `N` parameters is at `[r7 + 2 + (N - 1 - i)]`. The offset must fit in the
6 bits of a `load`, which counts up to 31. With 29 parameters the first one sits at
`[r7+30]`, which leaves one word spare, and that is where PyCPU draws the line: a 30th
parameter gets a friendly "more than 29 parameters" error.

**Step 3: the answer goes back in `r1`.** A `return` pops the answer into `r1`. Then
`setsp r7` throws away the variables and the scribbles in one go (the stack pointer
jumps back up to the frame pointer), `pop r7` gives the caller its frame pointer back,
and `ret` pops the return address into the program counter.

**Step 4: the caller tidies the tray.** Back in the caller, the arguments are still on
the stack. `getsp`, `addi` and `setsp` move the stack pointer up past them, and `push r1`
puts the answer where Pebble's next instruction expects it.

```
   caller                                 function
   ------                                 --------
   push 10, 20, 30   (the arguments)
   call __fn_add3  ───────────────────►   check room, push r7, r7 = sp
                                          ... work out the answer ...
                                          pop r1  (the answer)
   getsp r2          ◄──────────────────  setsp r7, pop r7, ret
   addi r2, 3        (step over 3 words)
   setsp r2
   push r1           (the answer)
```

**Step 5: recursion is just more frames.** Nothing in steps 1 to 4 cares *which*
function is calling. When `fact` calls `fact`, the new frame goes below the old one, with
its own `n` at its own `[r7+2]`. That is the pile of frames you printed in Try It.

**Step 6: the room check counts everything.** Before building a frame, the prologue adds
up the words this code could need: 1 for the old `r7`, its variables, the deepest its
Pebble stack gets (the arguments it pushes for a call are part of that), and 9 words for
the runtime routines. A `call` to another Pebble function needs only 1 more word, the
return address, which fits inside those 9. The *called* function then checks its own
frame in its own prologue. So the stack can never grow into the program: endless
recursion ends with `halt 2`, and every word of the program and its text is untouched.
The fault is reported at the line of the call that found no room; [What Happens When
Things Go Wrong](what-happens-when-things-go-wrong.md) shows how that line is found.

**Step 7: the checker works out what each function gives back.** A function that ends
without a `return` gives back **null**, Pebble's word for "nothing", and so does a
function whose `return` is only on some paths. PyCPU has no null, so the checker plays
through every function and sorts it into one of three kinds: it always returns a number,
it never does, or it *maybe* does. Because functions call each other (and themselves),
it keeps going round all of them until no answer changes. Calling a function as a
statement is always fine; but *using* the answer of a function that does not always
return a number is refused:

```
fn f(a) {                 print(f(1))  is refused:
    if a > 0 {            "using the result of a function that does not
        return 1           always return a number is not supported..."
    }
}                         f(1) on a line of its own is fine.
```

A function can only see its own parameters and variables, never the ones in `main`
("variables from outside a function"), and a function cannot be stored in a variable
or made inside another function that uses its variables ("functions used as values").

## Why Does This Matter?

Without frames, a function would need a fixed address for each of its variables, and
it could never call itself: the second `fact` would scribble over the first one's `n`.
Early computers really did work that way, and early languages simply did not allow
recursion. The frame pointer and the stack are what made recursion cheap, and almost
every language today (Python, JavaScript, C, Rust) calls functions the way you just
watched: arguments, a return address, a saved frame pointer, local variables.

It is also why "stack overflow" is a famous error. When you see a deep chain of
function names in an error message (a **stack trace**), it is a list of the frames on
the pile, read from the top. A debugger walks the pile the same way, following each saved
`r7` to the frame below.

## What's Next

`double` used `*`, and `fact` multiplied over and over, yet PyCPU has no multiply
instruction. That `call __mul` is a function call too. Open it up and see how the
machine multiplies and divides with nothing but shifting and adding, in
[Multiply and Divide](multiply-and-divide.md).
