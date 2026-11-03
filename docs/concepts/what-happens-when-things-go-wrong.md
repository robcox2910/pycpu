# What Happens When Things Go Wrong

## The Referee's Whistle

In a football match, when a player does something against the rules, the referee blows
the whistle. The game stops *at once*. Nobody carries on playing as if nothing happened.
Then the referee tells everybody two things: what went wrong ("handball") and where it
happened ("just outside the penalty area").

A computer needs a referee too. Some things a program asks for cannot be done: dividing
by zero, using more memory than the machine has, or going on for ever. If the machine
simply guessed an answer and carried on, a tiny mistake would quietly turn into a
huge, confusing one. So PyCPU blows a whistle instead. It **halts** (stops completely,
the way the `halt` instruction from [Machine Code](machine-code.md) does) and leaves a
number behind that says why. That number is the **halt code**. When it is not 0, it is a
**fault**: the machine's way of saying "I stopped because something went wrong".

| At the match | In PyCPU |
|--------------|----------|
| The whistle | The `halt` instruction |
| What went wrong ("handball") | The **fault**: `Fault.DIVIDE_BY_ZERO`, `Fault.STACK_OVERFLOW` or `Fault.BAD_ADDRESS`, held as a halt code (3, 2 or 1) |
| The referee's notebook | The **source map**: which Pebble line made each machine word |
| "Just outside the penalty area" | `PebbleRun.line`, the Pebble line that was running |
| The referee's announcement | `PebbleRun.describe()`, one friendly sentence |
| A match that never ends | The program is still running when we stop watching it: `halted` is `False` |

## Try It

The program below has three functions that call each other. The last one divides by
zero. We run it on Pebble's own VM (the program that runs Pebble directly) and then on
PyCPU, and print what each says. After that we make a stack overflow and an endless loop
on purpose.

```python
from pebble import PebbleError, run_source

from pycpu.fast import FastMachine
from pycpu.isa import Fault
from pycpu.translator import PebbleRun, run_pebble, translate

source = """fn c(n) {
    return 10 // n
}
fn b(n) {
    return c(n)
}
fn a(n) {
    return b(n)
}
print(1)
print(a(0))"""

try:
    run_source(source)
except PebbleError as error:
    print("Pebble VM:", error)

run = run_pebble(source)
print("PyCPU:    ", run.describe())
print("printed so far:", run.output.split(), "| fault:", run.fault.name, "| line:", run.line)

lines = translate(source).assembly.splitlines()
start = lines.index("    ; line 2: FLOOR_DIVIDE")
print("\n".join(lines[start + 3 : start + 6]))

endless_recursion = "fn f(n) {\n    return f(n + 1)\n}\nprint(f(0))"
print(run_pebble(endless_recursion).describe())
endless_loop = "let i = 0\nwhile i < 1 {\n    i = i + 0\n}"
print(run_pebble(endless_loop, max_steps=5000).describe())
print(run_pebble("print(7)").describe())
small_program = translate("print(1)")
small = FastMachine(words=small_program.memory_needed - 1)
small.load_program(small_program.program.words)
steps = small.run(1000)
small_run = PebbleRun.from_state(small_program, small.state(), steps)
print(f"{small.words} words of memory, {small_program.memory_needed} needed:", small_run.describe())
broken = PebbleRun("", True, Fault.BAD_ADDRESS, 3, 1)
print(broken.describe())
# Output:
# Pebble VM: Division by zero at line 2, column 15
# PyCPU:     Division by zero at line 2
# printed so far: ['1'] | fault: DIVIDE_BY_ZERO | line: 2
#     cmp  r2, r0             ; is the divisor 0?
#     br   ne, __fn_c_divisor_ok_2 ; no: go ahead and divide
#     halt 3                  ; yes: DIVIDE_BY_ZERO
# The stack ran out of room at line 2 (the call on that line found no room for another frame; does a function keep calling itself?)
# The program was still running after 5000 steps
# The program finished
# 121 words of memory, 122 needed: The program needs more stack room than there is at line 1
# The program used a memory address that does not exist at line 3
```

Both machines name line 2, even though the mistake happened three calls deep and `a(0)`
is on line 11. The `1` was printed before the whistle, and nothing after it was. The
`describe()` lines for the other endings say what stopped the machine in plain
words. The next one is the happy ending: no fault, so there is nothing to explain. The
"needs more stack room" sentence comes next, and the paragraph after this one explains it.
The final sentence is for a bad address. Our translated programs do not normally reach one, so we
build the ending by hand (a `PebbleRun` made up for the purpose) just to show what it
says.

**"The program needs more stack room than there is."** This is a different sentence from
"The stack ran out of room". That one blames a call. This one appears when *no call is to
blame*: the top of the program could not even fit its own first frame. On the full
4,096-word computer, `translate` refuses such a program before it runs (it is "too big"), so
you will only meet this sentence on a computer with less memory, like a small Cockpit. The
Try It makes one: `print(1)` needs 122 words (`memory_needed`, the program plus its top
frame), so we give a `FastMachine` 121. The stack is empty and the first frame still
does not fit, so there is no return address and no call to point at, and the sentence names
the first line of the program. A test pins the 122.

## How It Works

There are three steps, and each one is built from the layer below.

**1. The machine stops and leaves a number.** Three things can end a run with a fault.
Every one is a `halt` with a different halt code, defined as `Fault` in
`src/pycpu/isa.py`:

```
 what went wrong                who blows the whistle                 halt code
 --------------------------     ---------------------------------     ---------
 divisor is 0                   `halt 3` written next to the divide    3  DIVIDE_BY_ZERO
 stack would hit the program    `halt 2` at the top of every function  2  STACK_OVERFLOW
 an address that is not RAM     the machine itself, mid-fetch/execute  1  BAD_ADDRESS
```

The two whistles in the first two rows are ordinary instructions that the translator
writes. Look at the cards in Try It: before every `//` or `%` it writes `cmp r2, r0`
("is the divisor 0?"), a branch that skips over the whistle when the answer is no, and
`halt 3` for when it is yes. And each function begins by checking that there is room
for its frame (see [How a Function Call Really Works](how-a-function-call-really-works.md)),
and runs `halt 2` if there is not. Both checks happen *before* any damage is done, which
is why a stack overflow never overwrites your program. Only the third whistle, a bad
address, is blown by the machine itself, and the programs the translator writes do not
normally reach it.

**2. The machine says which word it was on.** After the whistle, the machine's
**program counter** (the register that points at the next instruction) has already
moved on. A fault caused by *carrying out* an instruction (every `halt` is one) leaves
the counter one past the word that did it, so the word to look at is `pc - 1`. A fault
caused by *fetching* (the counter pointing outside memory) leaves the counter on the bad
address itself, so the word is `pc`. `run_pebble` makes this choice in
`src/pycpu/translator/program.py`.

**Which line does a stack overflow name?** Not the line where the function starts, but
the line of the **call** that needed one more frame than the stack had room for. The
machine finds it from a note the call itself left behind. The `halt 2` check runs
*before* the new frame pushes anything, so the top of the stack still holds the **return
address** that `call` pushed (see [Calling and Returning](calling-and-returning.md)).
The `call` instruction is the word just before that address, and the source map knows
its line. In the endless `f` of Try It, the call `f(n + 1)` is on line 2, so the sentence
names line 2. If the function body had been spread over several lines, the line of its
`return f(y)` would be named. If the very first call from the top of the program does not
fit, that call's line is named. The one exception is the top level of the program having
no room even for its own frame, where nobody called anybody, so the line is the first
line of the program.

**3. The source map turns the word into a Pebble line.** When the translator wrote the
assembly, every card began with a comment such as `; line 2: FLOOR_DIVIDE`. It kept a
list, one entry per machine word, of the Pebble line that word came from. That list is
the **source map**, stored as `TranslatedProgram.pebble_lines` and read with
`line_at(address)`. Words that belong to ready-made routines (like `__divmod`) or to
text data have no Pebble line, so their entry is `None`.

```
   halt 3 sits at address 42          (the machine stops with pc = 43)
        |
        v   pc - 1
   source map[42]  ---->  line 2      "Division by zero at line 2"
```

Because the whistle sits on the divide's own card, it carries the divide's own line.
It does not matter that three functions were waiting to hand the answer back: the map
points at the line where the trouble *started*, which is what you want when hunting a
bug. (The addresses 42 and 43 are what this exact program gives; a pinned test checks
them.)

**Why does PyCPU not print Pebble's message?** Pebble's VM is a Python program, so when
it goes wrong it can raise a Python error with a message that was written for that
exact mistake, including a column. PyCPU's machine only has a number between 0 and 255.
Everything friendly has to be rebuilt from that number and the source map. That is what
`PebbleRun.describe()` does: it looks at `fault`, `line` and `halted` and writes one
sentence. The two machines agree on the *line*, not the wording.

**What about a program that never stops?** Nothing in the program is wrong, so no
whistle blows. The program just goes round and round. When we ask `run_pebble` to run
for at most `max_steps` instructions, it stops watching after that many and reports
`halted` as `False`, with no fault and no line, because the machine did not decide
anything: *we* gave up. It is like a coach saying "ten more minutes and then we go
home".

Pebble's own VM seems to have no limit on recursion. We ran the same endless recursion on it
and stopped it after a long wait, with no error at all. On PyCPU the stack is a
fixed amount of RAM, so the whistle blows almost at once, after about 24 thousand steps
(a test pins the exact number). A real computer is the same: memory is finite, so endless recursion always
ends in an overflow, never in an endless run.

## Why Does This Matter?

Without faults, a broken program would not stop. It would keep going on wrong numbers,
and you would see a strange answer far away from where the mistake was made. A halt code
plus a source map turns "something is wrong somewhere" into "line 2". The same trick is
how real programs report crashes: a bad-address fault, which the operating system reports as a
"segmentation fault". A crash report with a line number comes from a map like ours,
linking the machine's words back to the programmer's source. Debuggers read exactly this kind of
map to show you your own code while the machine is running something else.

It is also why the machine must stop *by itself*: a program cannot be trusted to check
its own mistakes, so the check is built into the machine and into the cards the
translator writes.

## What's Next

You have now seen a whole Pebble program travel down to NAND gates and, when it goes
wrong, back up to the right line. The finale is to do all of this with buttons and
watch the whole running computer, on [The Cockpit](the-cockpit.md).
