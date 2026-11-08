# Guided Walks

## A Museum Audio Guide

In a big museum you can hire an **audio guide**: a little player with headphones. It
tells you where to stand and what to look at, one sentence at a time. "Stand in front
of the big painting. Look at the dog in the corner." When the tour is over, you can
put it down and wander on your own.

The Cockpit has audio guides too, called **walks**. A walk loads a program, moves the
real machine one step at a time, and says one sentence about each step. At the end it
hands the controls over with a small task, called **Now you try**, such as "Press Step
until n is 0." The Cockpit checks the real machine to see when you have done it.

| In the museum | In the Cockpit |
|---------------|----------------|
| One recorded tour | One walk file, `src/pycpu/cockpit/walks/<name>.toml` |
| The tour's name on the box | `title` |
| The room the tour is about | `example` (an example program) or `source` (the walk's own Pebble) |
| "Read more in the guidebook" | `see_also`, the concept page that explains the same idea |
| "Walk to the next painting" | A step's `do`: the move the machine makes |
| The sentence in your ear | A step's `say` |
| "Look closely at the dog" | A step's `look` (the depth the glass shows) and `show` (what to highlight) |
| The quiz at the end | `[try]`: a `task`, a `check` and a `solution`, and `step = "into"` when the task needs Step into |
| Rewinding the tour to hear a bit again | `Cockpit.go_to_walk(name, step)`, which **replays** the walk from the start |

A step's `do` is one of these **actions**. Each one is a real move, the same as a
button in the Cockpit:

| Action | What it does |
|--------|--------------|
| `start` | Loads the walk's program and pauses at its start. Every walk's first step does this. |
| `step <depth>` | Presses Step once at `line`, `instruction`, `part` or `gate` depth. |
| `step line into` | Presses Step into once: a line step that follows a call into the function it calls. |
| `run to line <n>` | Runs on the fast engine until line *n* is about to start, then pauses. |
| `run <n> instructions` | Presses Run for *n* instructions. |
| `step gate until <part>` | Takes gate steps until a gate inside that part (such as `cpu.alu`) works. |

The `check` is one of `variable <name> == <number>`, `line == <number>`,
`register r<i> == <number>`, `output contains "<text>"` or `halted`.

## Try It

We list the walks, then open the first one on a small machine (256 words of memory, so
it is quick to build). We go through every step and print what the walk says. Then we
open the **Now you try** stage, play the walk's own solution, and print whether it is
done.

```python
from pycpu.cockpit.picture import machine_picture
from pycpu.cockpit.session import Cockpit
from pycpu.cockpit.walks import load_walks

for walk in load_walks():
    print(f"{walk.name}: {walk.title}")

walk = load_walks()[0]
cockpit = Cockpit(8)
for step in range(len(walk.steps)):
    cockpit.go_to_walk(walk.name, step)
    print(f"{step + 1}.", machine_picture(cockpit)["walk"]["say"])

cockpit.go_to_walk(walk.name, len(walk.steps))
picture = machine_picture(cockpit)["walk"]
print("Now you try:", picture["task"], "| done:", picture["done"])
for action in walk.trial.solution:
    cockpit.act(action)
print("after", len(walk.trial.solution), "presses, done:", cockpit.walk.done)
# Output:
# many-instructions: A line of Pebble is many tiny instructions
# where-n-lives: Where does n live? A box in memory
# subtracting-with-gates: How the computer subtracts, down to the gates
# a-call-and-the-stack: What a function call does to the stack
# why-the-clock-ticks: Why the clock ticks
# 1. This is the countdown program, and the marked line is the one that runs next.
# 2. We ran the program to line 5, n = n - 1, which takes 1 away from n.
# 3. Look closer: the CPU runs a line as tiny instructions, and this first one only copied n, which is 5, into r1.
# 4. The next tiny instruction put that 5 on the stack, a pile where the CPU keeps numbers for later.
# 5. Stepping the rest of the line ran 8 more tiny instructions, so n = n - 1 is 10 instructions in all, and n is now 4.
# Now you try: Press Step until n is 0. | done: False
# after 12 presses, done: True
```

Read it from the top:

- There are five walks, one for each idea. The page lists them in this order.
- Each `go_to_walk` call puts the machine at that step, and the picture's `walk` key
  carries the sentence to say. The numbers in the sentences (5, 8, 10, 4) are the
  numbers the real machine shows at that moment; the tests check each one.
- The **Now you try** stage starts with `done` false. The 12 presses of Step at line
  depth go round the loop again and again until `n` is 0, and then `done` is true.
- In Python the try is `walk.trial`, not `walk.try`, because `try` is a word Python
  keeps for itself.

## How It Works

The walk files are read by `src/pycpu/cockpit/walks.py`, and the session in
`src/pycpu/cockpit/session.py` makes the moves.

**1. Reading a file, with no guessing.** Each action and check is split into words and
matched against a short list of shapes, such as `["run", "to", "line", n]`. Anything
else is a `WalkError` that names the file and the problem, such as
`many-instructions.toml: unknown action 'jump about'`. The file's text is never run as
code, so a walk file can only ask for moves the Cockpit already has.

**2. Replay from the start.** `go_to_walk(name, step)` does not remember where you were.
It stops play, loads the program again (the first step is always `start`), and makes
every step's move again, up to the one you asked for:

```text
   go_to_walk("many-instructions", 3)

   step 0   start                 load the countdown, pause      ─┐
   step 1   run to line 5         fast engine, then pause         │  replayed,
   step 2   step instruction      one instruction in the gates    │  for real,
   step 3   step instruction      one more                       ─┘  every time
                                       │
                                       ▼
                         the picture's walk: say step 3's sentence
```

Because every visit to step 3 is made the same way from the same start, the machine is
always in exactly the same state there. That makes **Back** (go to `step - 1`) and
**Back to the walk** (after you wandered off) exact, whatever you did in between.

**3. A fast-forward is a real run.** `run to line 5` does not jump to line 5 or write
numbers into memory. It runs the program on the fast engine, one real instruction after
another, and pauses into the gates when line 5 is next, just like a line step. Here is
the same moment reached by the walk and by pressing Step at line depth by hand. The two
machines match exactly:

```python
from pycpu.cockpit.session import Cockpit, Depth
from pycpu.cockpit.walks import example_source

walked = Cockpit(8)
walked.go_to_walk("many-instructions", 1)
print(walked.happened)

by_hand = Cockpit(8)
by_hand.load_pebble(example_source("countdown"))
presses = 0
while by_hand.translated.line_at(by_hand.computer.instruction_start.pc) != 5:
    by_hand.step_at(Depth.LINE)
    presses += 1
print(
    presses,
    "line steps by hand; same machine:",
    by_hand.computer.state() == walked.computer.state(),
)
# Output:
# Ran 202 instructions to reach line 5.
# 3 line steps by hand; same machine: True
```

**4. Checks are latched.** After every move at the **Now you try** stage, the session
tests the walk's `check` on the real machine. Once it has passed, `done` stays true. So
if you keep pressing Step after `n` reaches 0, all the way to the end of the program,
you have still done it.

The check is tested once at the end of each move. A Step moves a little at a time, so
it never misses a moment. A Run or Play moves many instructions in one go, so a check
that is true for only a moment in the middle of a run can be missed: the session sees
where the run stopped, not every instruction on the way. That is why each task says
"Press Step", and why every walk's solution is made of Steps.

Here is the countdown's try, done and then stepped on past `n == 0` to the very end:


```python
from pycpu.cockpit.session import Cockpit, Depth
from pycpu.cockpit.walks import load_walks

walk = load_walks()[0]
cockpit = Cockpit(8)
cockpit.go_to_walk(walk.name, len(walk.steps))
for action in walk.trial.solution:
    cockpit.act(action)
while not cockpit.computer.state().halted:
    cockpit.step_at(Depth.LINE)
print("halted:", cockpit.computer.state().halted, "| done:", cockpit.walk.done)
# Output:
# halted: True | done: True
```

**5. The last card points at the guidebook.** When the try is done, the bar cheers and,
under the cheer, says **Read about it** with the title of the walk's `see_also` page,
linked to it, to see how the idea is built. The link opens the docs on your own
computer, so start them first with `uv run mkdocs serve` in the `pycpu` folder.

**6. Wandering off.** During a walk's steps, any move of your own (a Step, a Run, a
load) sets `off_script`, and the page offers **Back to the walk**, which is just
`go_to_walk` again. At the **Now you try** stage your Steps are the task, so only
loading a different program counts as wandering off.

The web app has three routes for walks: `GET /api/walks` lists them, `POST /api/walk`
with `{"name", "step"}` opens one and answers the picture, and `POST /api/walk/leave`
puts the guide away. The picture's `walk` key carries the step's `say`, `look` and
`show`, and at the **Now you try** stage the `task`, `done`, and `step_kind`, which is
`"into"` when the page should offer Step into (as the function-call walk does) and
null otherwise. It also carries `see_also`, with the `title` and `url` of the walk's
concept page on the docs server on your own computer, such as
`{"title": "The ALU", "url": "http://127.0.0.1:8000/concepts/the-alu/"}`. A walk name that does not exist gets a 404 that says
"There is no walk called nonsense." in plain words.

## Why Does This Matter?

A screen full of numbers is hard to read if nobody tells you where to look. A walk
points at one thing at a time, so you see an idea happen on the real machine before you
read about it. And because every walk runs the real program, everything it shows you is
true: if a walk says `n` is 4, it is because the machine really worked out 4.

Real software does this too. Many apps open with a short tour that points at one button
at a time. A flight simulator has training lessons that put the plane in the air at the
right moment, then let you fly it yourself.

## What's Next

Every part you zoom to also shows the code that built it. Read
[The Code Behind a Part](the-code-behind-a-part.md) to see how the Cockpit finds that
code, then go back to [What Is a Computer, Really?](../index.md) to see the whole
ladder from one NAND gate to a Pebble program.
