# Calling and Returning

## A Bookmark on the Pile

You are reading a story, and at the bottom of page 12 it says "to find out who the
stranger was, read chapter 9 first". So you take a bookmark, write "page 12" on it, put
it on the pile of bookmarks beside you, and go off to read chapter 9. When chapter 9
ends with "now go back to where you were", you pick up the **top** bookmark from the
pile, read "page 12" on it, and carry on from there.

The clever part is the pile. Suppose chapter 9 itself says "first read the footnote on
page 80". You put a second bookmark, "chapter 9, page 3", on top of the first, and go.
When the footnote ends you pick up the top bookmark and land back in chapter 9, and when
chapter 9 ends the next bookmark takes you back to page 12. However deep the detours
go, the top bookmark is always the right way home.

A piece of program that does one job and can be used from anywhere is called a
**function** (some people say *subroutine*). Jumping into a function while leaving a
bookmark is a **call**. The bookmark is the **return address**: the address of the
instruction just after the call, where the program should carry on. Picking up the top
bookmark and going back there is a **return**. And the pile of bookmarks is the
[stack](the-stack.md) from the last page.

| The book | In PyCPU |
|----------|----------|
| A chapter you can be sent to from anywhere | A **function**: instructions starting at a label |
| "Read chapter 9 first" | `CALL addr`: push `pc`, then `pc = addr` |
| The bookmark | The **return address**: the `pc` value the call pushes |
| The pile of bookmarks | The stack, with `sp` on the top |
| "Now go back to where you were" | `RET`: pop the top word into `pc` |
| Reading the bookmark | `ram.out` going into `pc` through the `next_pc` chooser |
| Writing the bookmark | The `ram_data` chooser sending `pc` to the RAM |

## Try It

The program below has two functions. `double` adds `r1` to itself. `times4` calls
`double` twice, so a function calls a function. We run it on the gate computer and,
after every instruction, print `pc`, `sp` and the bookmark on top of the stack.
(`disassemble` shows each call's target as a plain address: `times4` is at 3 and
`double` is at 6.)

```python
from pycpu.assembler import assemble, disassemble
from pycpu.cpu import GateMachine

source = """
    li r1, 3
    call times4     ; go to times4, leaving a bookmark
    halt
times4:
    call double     ; a function can call another function
    call double
    ret
double:
    add r1, r1, r1  ; r1 = r1 + r1
    ret
"""
machine = GateMachine(address_bits=6)
machine.load_program(assemble(source, words=machine.words).words)

while not machine.state().halted:
    before = machine.state()
    text = disassemble(before.memory[before.pc], before.pc)
    machine.step()
    after = machine.state()
    top = after.memory[after.sp] if after.sp < machine.words else "nothing"
    print(f"{text:15} pc = {after.pc}, sp = {after.sp}, top = {top}")
print("r1 =", machine.state().registers[1])
# Output:
# li r1, 3        pc = 1, sp = 64, top = nothing
# call 3          pc = 3, sp = 63, top = 2
# call 6          pc = 6, sp = 62, top = 4
# add r1, r1, r1  pc = 7, sp = 62, top = 4
# ret             pc = 4, sp = 63, top = 2
# call 6          pc = 6, sp = 62, top = 5
# add r1, r1, r1  pc = 7, sp = 62, top = 5
# ret             pc = 5, sp = 63, top = 2
# ret             pc = 2, sp = 64, top = nothing
# halt            pc = 3, sp = 64, top = nothing
# r1 = 12
```

Read it like the book. The first `call 3` sits at address 1, so it leaves the bookmark
2 (the `halt` after it) and jumps to `times4`. Inside `times4`, `call 6` leaves a second
bookmark, 4, on top of the first, and jumps to `double`. When `double` says `ret`, the
top bookmark sends it back to 4 and comes off the pile, and the bookmark 2 is on top
again. The second `call 6` leaves 5, and its `ret` comes back to 5. Finally `times4`'s
own `ret` finds the bookmark 2, and the program halts with `r1 = 3 × 4 = 12`.

`double` was used twice, from two different places, and went back to the right one
each time. It never knew who called it: the bookmark knew.

## How It Works

`CALL` and `RET` live in `GateMachine` in `src/pycpu/cpu.py`. They reuse everything the
stack page built (`sp_minus_1`, `sp_plus_1`, the `address_mux` and `next_sp`) and add
two choosers. Each takes one execute beat, like every other instruction.

**1. The return address is already in `pc`.** On the fetch beat of a `CALL`, `pc`
moved on by one, as it always does (see
[Fetch, Decode, Execute](fetch-decode-execute.md)). So by the execute beat `pc`
already holds the address of the instruction after the call. That is exactly the
bookmark we want. No sum is needed.

**2. A call is a push and a jump at once.** On the execute beat of `CALL`:

- The `address_mux` sends `sp - 1` to the RAM, the same spot a `PUSH` would use.
- A new chooser, `ram_data`, sends `pc` to the RAM's data wires instead of window `b`.
  (For `STORE` and `PUSH` it still sends window `b`.)
- The RAM's write wire is raised, so on the `write` pulse the return address goes into
  memory at `sp - 1`.
- At the clock's rise, `sp` loads `sp - 1` (the finger moves down onto the new
  bookmark) and `pc` loads the 12-bit address from the instruction, the same wires
  that `JMP` uses.

All of that happens together because the old `pc` and the old `sp` are still sitting in
their registers during the `write` pulse; the new values only arrive at the clock's rise
(see [The Clock](the-clock.md)).

**3. A return is a pop into `pc`.** On the execute beat of `RET`, the `address_mux`
sends `sp` to the RAM, so `ram.out` shows the top bookmark. The `next_pc` chooser has a
new input: for `RET` it picks `ram.out`. At the clock's rise `pc` loads the bookmark and
`sp` loads `sp + 1`. The next fetch beat then fetches the instruction after the call.

```
                 ┌────────────┐   new pc
   pc + 1 ──────►│            │
   pc + off9 ───►│  next_pc   ├──────────►  pc  (loads for JMP, CALL, RET,
   addr12 ──────►│  chooser   │                  or BR when its condition holds)
   ram.out ─────►│            │  ◄── RET picks ram.out: the bookmark
                 └────────────┘

                 ┌────────────┐   data
   window b ────►│  ram_data  ├──────────►  RAM  (written for STORE, PUSH, CALL)
   pc ──────────►│  chooser   │  ◄── CALL picks pc: the bookmark
                 └────────────┘
```

**4. Is it safe to feed `ram.out` into `pc`?** [RAM](ram.md) taught a rule: a RAM
cell is a latch, so the RAM's address and data must never depend on `ram.out`, or a
write could chase its own tail. `RET` does not break it. `ram.out` only goes to `pc`'s
*input*, and `pc` is a register: it ignores its input until the clock rises, and on a
`RET` beat the RAM is not being written at all. On the next beat, `pc` drives the
address, but by then it is a register holding a settled number.

**5. Faults.** A `CALL` with `sp` at 0 would write the bookmark to `0xFFFF`, and a
`RET` with `sp` at the end of memory would read past it. Both fault with
`Fault.BAD_ADDRESS` and change nothing else: `pc` stays one past the instruction,
`sp` and memory are untouched. That is the same rule as for `PUSH` and `POP`.

**6. `RET` trusts the pile.** `RET` does not check that the top word really is a
bookmark. If a function pushes a number and forgets to pop it, `RET` jumps to that
number as if it were an address. That is a real kind of bug, and a dangerous one in real
computers, so the tests check that both of our engines jump to exactly the same wrong
place.

## Why Does This Matter?

Without calls and returns, every time a program wanted to double a number it would need
its own copy of the doubling instructions, or a `JMP` back to a place fixed in advance,
which only works from one caller. Functions let you write a job once, give it a name,
and use it from anywhere, including from inside other functions. Big programs are built
almost entirely out of functions calling functions.

Because each bookmark sits on a pile, a function can even call itself, so long as it
stops eventually: each call gets its own bookmark. That trick, called *recursion*, is
how many programs search mazes, sort lists and draw fractals (pictures made of smaller
copies of themselves). The chips in most laptops (called x86) have `CALL` and `RET`
instructions that use the stack just like ours. The chips in most phones (called ARM)
keep the newest bookmark in a register first, and push it onto the stack when a
function calls another. And the "stack overflow" error that programmers know so well
usually means a function called itself so many times that the pile of bookmarks ran
out of room.

## What's Next

The computer can now run real programs with functions in them. To look inside the parts
we have built, gate by gate, continue with [The Bench](the-bench.md).
