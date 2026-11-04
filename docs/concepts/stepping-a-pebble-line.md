# Stepping a Pebble Line

## Reading Aloud With a Bookmark

Imagine reading a story aloud to someone, with a bookmark. You can read one *word* at a
time, very slowly, pointing at each letter: that is how the gate engine works, and it is
wonderful for looking closely but far too slow for getting anywhere. Or you can say
"next line": you read the rest of the line at your normal speed, then put the bookmark at
the start of the next line and stop, ready to look closely again.

Now imagine the story has **footnotes**: a little number in the middle of a sentence
that sends you to the bottom of the page and then back again. When you say "next line"
and the line has a footnote, you have a choice. You can **step over** it: read the whole
footnote and come back, and put the bookmark on the next line of the *story*. Or you can
**step into** it: follow the footnote, and put the bookmark on the footnote's first line.

In a Pebble program, a footnote is a **function**. The Cockpit has two new buttons that
do exactly this. **Next line** (step over) runs to the next line of the code you are
in, running any function it calls all the way through. **Step into** follows a call and
stops on the first line inside the function.

| Reading aloud | In PyCPU |
|---------------|----------|
| The bookmark | The pause: the machine stops in the gate engine, just before an instruction |
| Reading word by word, pointing at each letter | Stepping a gate, a beat or an instruction on the gate engine |
| Reading a line at normal speed | Running instructions on the fast engine (from [Two Engines](two-engines.md)) |
| Saying "next line" | `POST /api/step` with `{"size": "line"}`: `Cockpit.step_line(into=False)` |
| Following a footnote | `POST /api/step` with `{"size": "line_into"}`: `Cockpit.step_line(into=True)` |
| A footnote | A function call, with its own **frame** |
| Which page of footnotes you are on | `r7`, the **frame pointer** (from [Variables in Memory](variables-in-memory.md)) |
| The printed margin notes nobody reads aloud | The ready-made routines (`__print_int` and friends), which have no Pebble line |
| "This line never ends!" | `MAX_LINE_INSTRUCTIONS`: a line step gives up after 10,000 instructions |
| A sticky note saying why you stopped | `note` in the machine picture |

## Try It

We load the countdown from [The Cockpit](the-cockpit.md) into a Cockpit with 256 words
of memory, and press "next line" until the program finishes. After each step we print the
line the Pebble pane marks, the `note` that says how far the step ran, and `r7`, the
frame pointer. When the program has finished, we press it once more.

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit

COUNTDOWN = """\
let n = 2
while n > 0 {
    print(n)
    n = n - 1
}
"""


async def step_lines() -> None:
    client = TestClient(create_cockpit(address_bits=8))
    machine = (await client.post("/api/pebble", json={"source": COUNTDOWN})).json()
    print("loaded: line", machine["pebble"]["line"], "with r7 =", machine["registers"][7])
    while not machine["halted"]:
        machine = (await client.post("/api/step", json={"size": "line"})).json()
        if not machine["halted"]:
            print("line", machine["pebble"]["line"], "with r7 =", machine["registers"][7], end=": ")
        print(machine["note"])
    print("printed", repr(machine["output"]))
    machine = (await client.post("/api/step", json={"size": "line"})).json()
    print(machine["note"])


run(step_lines())
# Output:
# loaded: line 1 with r7 = 0
# line 2 with r7 = 255: Ran 14 instructions to reach line 2.
# line 3 with r7 = 255: Ran 13 instructions to reach line 3.
# line 4 with r7 = 255: Ran 174 instructions to reach line 4.
# line 2 with r7 = 255: Ran 10 instructions to reach line 2.
# line 3 with r7 = 255: Ran 14 instructions to reach line 3.
# line 4 with r7 = 255: Ran 174 instructions to reach line 4.
# line 2 with r7 = 255: Ran 10 instructions to reach line 2.
# Ran 17 instructions, and then the program stopped.
# printed '2\n1\n'
# The program has finished, so there is no next line.
```

The first step costs 14 instructions, more than you might expect for `let n = 2`. When
the program is loaded, the machine is about to *make main's frame* (the room for `n`),
and the translator files those words under line 1 too. While they run, the frame
pointer `r7` changes from 0 (no frame at all) to 255 (main's frame). Ten instructions
make the frame, and four more put 2 into `n`; then line 2 is next, and the step stops.

Each note counts the instructions of the line just finished, as the fast engine ran
them: "Ran 174 instructions to reach line 4" is the price of line 3, `print(n)`. The
second Try It on [The Cockpit](the-cockpit.md) splits that up, one instruction at a
time: 4 instructions of the line's own, then 170 inside the ready-made printing routine.
That routine has no Pebble line of its own, so the step carries on through it without
stopping. The second check of `while n > 0` takes one
more instruction than the first (14, not 13). The jump at the bottom of the loop, back
up to the check, was made by the `while` line, so the translator filed it under line 2:
the step from line 4 stops just before that jump, and the next step runs the jump and
then the check. The last step checks `while n > 0` one final time, finds `n` is 0, and
runs to the `halt`. Pressing it again does nothing, and the note says why.

Now a program with a function, a footnote:

```python
from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit

DOUBLE = """\
fn double(n) {
    return n * 2
}
let x = 3
print(double(x))
"""


async def into_and_over() -> None:
    client = TestClient(create_cockpit(address_bits=8))
    for size in ("line_into", "line"):
        await client.post("/api/pebble", json={"source": DOUBLE})
        machine = (await client.post("/api/step", json={"size": "line"})).json()
        print("on line", machine["pebble"]["line"], "with r7 =", machine["registers"][7])
        machine = (await client.post("/api/step", json={"size": size})).json()
        print(size, "->", machine["note"])
        if machine["halted"]:
            print("   the program printed", repr(machine["output"]))
        else:
            frame = machine["variables"]
            print("   inside", frame["function"], "with r7 =", frame["frame_pointer"])
            for name in frame["names"]:
                print("  ", name["kind"], name["name"], "=", name["value"])


run(into_and_over())
# Output:
# on line 5 with r7 = 255
# line_into -> Ran 12 instructions to reach line 2.
#    inside double with r7 = 251
#    parameter n = 3
# on line 5 with r7 = 255
# line -> Ran 223 instructions, and then the program stopped.
#    the program printed '6\n'
```

Both times we first press "next line" once, which makes main's frame, runs `let x = 3`
and stops on line 5, `print(double(x))`. (Line 1, `fn double(n) {`, only names the
function; main's own code starts at line 4.) Then "step into" follows the call: 12
instructions later the machine is paused on line 2, `return n * 2`, inside `double`, with
its own frame (`r7` is 251, lower down the stack than main's 255) and its parameter `n`
holding 3. "Next line" from the same place steps *over* the call: it runs `double`, the
multiply routine, the printing routine and the program's end, 223 instructions, without
ever stopping inside `double`. The line after `print(double(x))` is the end of the
program, so it halts with `6` printed.

## How It Works

### A line is many instructions

One Pebble line becomes many machine instructions, and the Try It shows it: 14, 13,
174, 10. Over the 15 test programs in `tests/pebble_programs/`, run to the end on the
project laptop on 2026-11-03, the middle-sized line step (the **median**: half are
smaller, half bigger) ran 22 instructions.

On the gate engine every one of those instructions is thousands of gate steps. Measured
on the same laptop at full size (4K words), the median line step of the countdown is
490,376 gate steps, more than a second of waiting, and a `print` line is about 6.7
million gate steps, about 15 seconds. That is far too slow for a button. So a line step
does what the reader with a bookmark does: it reads at normal speed, on the **fast
engine**, and only puts the bookmark down, into the **gate engine**, at the next line.
Then every dial, wire and gate in the Cockpit is real again, ready to zoom into.

### The steps

The code is `Cockpit.step_line` in `src/pycpu/cockpit/session.py`.

```text
   paused in the gates, maybe part-way through an instruction
        |
        |  1. remember where we start: start_line = the line of this instruction,
        |     start_fp = r7 at the start of this instruction
        |     (if no frame is ready here, start_fp waits for the first ready word)
        |  2. computer.resume(): finish the instruction in the gates,
        |     copy everything to the fast engine
        v
   +---------------------------------------------------------------+
   |  fast engine, before each instruction:                        |
   |                                                               |
   |   halted?  ---------------------------------> stop "halted"   |
   |   first ready word, and start_fp still waiting? set it to r7  |
   |   word has a ready frame, and a Pebble line, and              |
   |     (line != start_line or r7 != start_fp), and               |
   |     (step into, or r7 >= start_fp)  ------> stop "line"       |
   |   already ran 10,000? ------------------------> stop "limit"  |
   |   otherwise: run one instruction, and look again              |
   +---------------------------------------------------------------+
        |
        |  3. computer.pause(): copy everything back into the gates
        v
   paused in the gates, just before the first instruction of the next line
```

Step 2 matters when you have been stepping gate by gate. Say you pressed **100 gates**
in the middle of an `add`. The step first finishes that `add` in the gates, exactly as
it would have gone on, and only then hands over to the fast engine. Nothing is skipped
and nothing is done twice; this is the same `resume` and `pause` from
[Pausing and Rewinding](pausing-and-rewinding.md). The "Ran N instructions" in the note
counts only what the fast engine ran, so that finished `add` is not part of N. Whatever
happens inside the loop, the step always ends with `pause`, so the Cockpit is never left
running on the fast engine.

### Which word counts as "a line"

The translator keeps two notes for every word of machine code: the Pebble line it came
from (the **source map**, `TranslatedProgram.line_at`) and the frame `r7` points at just
before it runs (`TranslatedProgram.frames`, from the Cockpit page's Variables). A step
stops only on a word that has both:

- **A line.** The ready-made routines for multiply, divide and print have no Pebble
  line, like the printed margin notes. A step always runs through them and counts
  their instructions toward the line that called them.
- **A ready frame.** While a function is *making* its frame (its first few words, the
  **prologue**), and on the `ret` that leaves it, `r7` is changing over from one frame to
  the other. Stopping there would show the wrong variables, so those words never stop a
  step.

What if the step *starts* on one of those words? That happens just after a load, when
main is about to make its frame, or after you have pressed **1 instruction** into a
function's prologue. Then the start has no frame of its own yet: `r7` still points at
the old one. So the step waits, and takes `start_fp` from the first ready word it
reaches, the moment the new frame is made. From there it stops at the next *different*
line. That is why the first press after a load lands on line 2 and not on line 1 again,
and why a step over begun in `double`'s prologue (which the translator files under line
2) runs `double` to the end and stops back on line 5, in main.

### Step over and the frame pointer

Every function call makes a new frame lower down the stack (the stack grows down, from
[The Stack](the-stack.md)), so a callee's `r7` is always *smaller* than its caller's.
That one fact is all step over needs:

```text
  r7 = 255   main         print(double(x))      <- start: start_fp = 255
  r7 = 251     double       return n * 2        <- r7 < 255: a call, step over runs on
  r7 = 255   main         (back again)          <- r7 >= 255: step over may stop here
```

Step over only stops where `r7` is the start's or bigger: the same frame, or a caller's.
Step into stops at the first located, ready word whose line or frame differs, which
is the callee's first line.

Comparing frames, and not only lines, is what makes **recursion** work, where a function
calls itself. Take `return f(n - 1)` on its own line. When `f` calls itself, the new
copy of `f` reaches that same line again, in a new frame. A step over that only looked at
line numbers would stop there, inside the callee. Because the new frame's `r7` is
smaller, step over runs on, through every deeper call, until it is back in the caller's
frame. And because the first words of each new `f` (its prologue) have no ready frame,
it can never stop half-way through making one.

### A line that never ends

`while true { }` written on one line never reaches another line. If a step simply waited
for the next line, the request would never be answered and the page would hang. So a
step gives up after `MAX_LINE_INSTRUCTIONS`, 10,000 instructions, pauses wherever it got
to, and its note says that it gave up and why. You can press it again, or look inside to
see what the loop is doing.

## Why Does This Matter?

Without line steps, following a Pebble program in the Cockpit means pressing **1
instruction** hundreds of times, and losing your place inside the printing routine. With
them, you move through your own code at the speed you think in, a line at a time, and
can still stop and drop down to the gates whenever a line surprises you.

Every real debugger has these same buttons. In Python's debugger, `pdb`, `next` is step
over and `step` is step into; in the C debugger `gdb` they have the same names, and code
editors draw them as little arrows. Under the hood they do what `step_line` does: run the
machine at full speed, check the program counter against the compiler's line table, and
compare the frame (or stack) pointer to tell "a deeper call" from "back in my own code".
And they too need a way out when a line never ends: you press pause.

## What's Next

You can now walk through a Pebble program a line at a time, follow a call or step over
it, and drop into the gates at any line. The next part of the Cockpit is play and pause:
letting the program run on its own while you watch, in
[Watching It Run](watching-it-run.md).
