# The Cockpit for Learners: Design

Status: draft, awaiting owner approval (2026-11-04).
Builds on: `2026-11-01-pycpu-design.md` (the PyCPU spec) and the Cockpit merged in Plan 4 (PR #4).
Becomes: Plan 5. PyStack integration and the first release move to Plan 6.

## Why

The owner checked the Plan 4 Cockpit in a real browser. Everything worked, but they found it confusing and unclear. Three causes:

1. **Things happen out of sight.** A button changes something below the fold. The owner was told to click and look, but the result needed scrolling to find.
2. **Too many choices before you understand them.** There are five step sizes (Gate, Cycle, Instruction, Line, Line into), plus Run and a count, all at once.
3. **Numbers without meaning.** The page shows true values, but nothing says in words what just happened.

The deeper point, in the owner's words: "a 12 year old would need help here... this is quite a complex thing we are trying to show and explain." A tidy screen is not enough on its own. A learner needs a guide.

## What success looks like

A curious 12-year-old opens the Cockpit for the first time, alone, and in about five minutes and two guided walks can:

- say that one line of Pebble becomes several machine instructions;
- say that a variable like `n` is a box in memory, having watched it change;
- make that happen again themselves, using Step.

Nothing they see is ever faked (the PyCPU rule stands: the glass draws the real circuit computing the real value).

## Goals

- **One screen, nothing out of sight.** The page never scrolls at desktop size. Whatever a click or step changes is visible on that screen.
- **Layout C (owner's choice): program plus magnifying glass.**
  - The left half always shows the learner's program: Pebble, the running line marked, that line's machine instructions listed under it, and the variables and output.
  - The right half is the magnifying glass, showing the one thing being studied, large.
- **A trail that works as a ladder.** Along the top of the glass is a trail such as `Pebble line 5 › subtract › ALU › gates`. Every crumb can be clicked to climb back up. The learner can always get out.
- **One Step button that follows depth.** It steps at the level the glass is showing, and its label says what it will do:
  - on the program (Pebble) level, a line;
  - on machine code, an instruction;
  - on a CPU part, a beat (cycle);
  - on gates, a gate.
  - For example: "Step one ALU beat ▸".
- **A "What just happened" sentence** after every step, in plain words, such as "The ALU took 1 away from 2. The answer, 1, is on its way to r1."
- **Only the newest change glows.** This replaces "mark everything that differs".
- **Guided walks are the front door.**
  - On opening, the learner sees a short list of walks, not the controls.
  - Each walk teaches one idea in about two minutes.
  - A walk drives the screen: it moves the glass, highlights the one thing to look at, and shows one sentence per Next press.
  - Each walk ends with "Now you try": one small task the page can detect, such as "press Step until `n` is 0", with a cheer when it is done.
- **Starter set of walks** (the exact wording is for the builder; the ideas are fixed):
  1. A line of Pebble is many tiny instructions.
  2. Where does `n` live? A box in memory.
  3. How the computer subtracts, down to the gates.
  4. What a function call does to the stack.
  5. Why the clock ticks.
- **Free exploring stays.** After (or instead of) the walks, the learner can use the full Cockpit in layout C, with Play/Pause, the one Step button, Rewind and loading examples or their own Pebble.
- **Docs and Cockpit link up.** Each concept page that has a matching walk gets a "See it in the Cockpit" link that opens that walk.

## Non-goals

- No new machine features. The CPU, translator, Pebble subset and gate engine are unchanged.
- No accounts, progress saving across visits, scores or badges.
- No PyStack integration and no release. Those are Plan 6.
- **Nothing is exposed until the owner is happy to show people** (owner, 2026-11-04). That means:
  - no docs site, GitHub Pages or series listing;
  - no tag, release or PyPI publish;
  - no links or integration from the other learning-series projects (PyStack included);
  - nothing posted to the web.

  All the work stays inside the PyCPU repo.

## Anti-goals (failure even if it technically works)

- **Faking anything to make a walk smoother.** Walks show the real machine running the real program. If a walk wants a value at a moment, it steps the real machine there.
- **A screen that needs scrolling** at a normal laptop size to see the effect of the button just pressed.
- **A walk that is just the docs page pasted in.** Walks show, in motion, one sentence at a time.
- **Losing the expert path.** Someone who wants Gate/Cycle/Instruction/Line exactly must still be able to get it, for example by moving the glass to that depth.

## Constraints

- Everything in the PyCPU spec and repo CLAUDE.md still binds:
  - NAND is the single primitive;
  - never fake the gate view;
  - 4K words of real-gate RAM;
  - docs first, for a curious 12-year-old;
  - every figure in the docs printed or pinned;
  - strict typing, coverage floor and series standards.
- The Plan 4 HTTP API (routes, picture keys, contract) is the base. Extend it where needed (for example the "What just happened" sentence and the newest change); don't break what tests pin without updating them.
- The page stays a single self-contained HTML file served by PyWeb, with no external URLs, working in dark mode and at phone width. At phone width one column is acceptable; the glass may then sit above the program, but the effect of a step must still be visible without scrolling.

## Decided with the owner

- Layout C (program plus magnifying glass), refined as above.
- One Step button that follows depth, the "What just happened" sentence, only the newest change glowing, and the trail as a ladder.
- Guided walks as the front door, ending in "Now you try".
- This must be finished before the first release: it becomes Plan 5, and PyStack and the release become Plan 6.

## Calls I made (owner may override)

- **Five starter walks**, listed above.
- **Where the sentences come from.** "What just happened" sentences are written by the server (Python), not the page, so they can be tested and pinned like every other doc figure.
- **Where the walks live.** Walks are data (a small file per walk: the program, the steps, the sentences and the "Now you try" check), not code in the page, so they are testable and easy to add.
- **"Newest change" means** what the last step changed, at the glass's depth.

### Settled after the builder check (my calls)

- **Levels.** There are four depths, from the top:
  1. **Pebble line.**
  2. **Instruction.** A crumb such as "subtract".
  3. **CPU part.** A crumb such as "ALU". Its Step is one beat.
  4. **Gates.**

  The CPU parts that get their own view are the ones in Plan 4's zoom table, plus registers and RAM:
  - ALU;
  - write-back;
  - address mux;
  - next-pc;
  - next-sp;
  - halt;
  - registers;
  - RAM.
- **Moving and stepping.**
  - Climbing or descending the trail never moves the machine.
  - Step at a higher level, started part-way through a lower one, first finishes the lower one. Plan 4 already does this for instructions and lines.
- **Getting a walk to a moment.**
  - A walk may fast-forward with a real run, for example "run to this line" or "run N instructions". This uses the fast engine and then pauses into the gates, exactly as Plan 4's Run and line steps do. It is a real run, not a fake.
  - Only the steps the learner watches are taken one by one.
- **Extending the picture.**
  - Read-only additions to the picture are allowed, such as per-line instruction ranges and per-beat descriptions.
  - A walk is cut only if the machine truly cannot show it.
  - "No new machine features" means no change to what the machine computes.
- **"What just happened" sentences** are generated from the real change, for any program, not hand-written per walk, because free exploring needs them too:
  - **Instruction level:** one template per opcode, with the real operand values, for example "The ALU took 1 away from 2".
  - **CPU-part level:** one sentence per beat of that part.
  - **Gate level:** a short generic sentence naming the gate and its new output, or the clock-wire note from Plan 4.
  - Every template is pinned by tests.
- **Newest change** at the gate level is exactly what that one gate step changed.
- **No scrolling** is measured at 1280×720. A headless-browser layout check is acceptable as a slow-marked dev test, if the builder wants one.
- **Walk files.**
  - "Now you try" checks are declarative predicates on the real machine state, for example `variable n == 0` or `line == 6`. The server evaluates them.
  - "See it in the Cockpit" links point at the local Cockpit, `http://127.0.0.1:8765/#walk=<name>`, because nothing is published.
- **Leaving a walk.**
  - If the learner steps off script, climbs the trail or loads a program, the walk pauses and shows "Back to the walk".
  - "Now you try" cannot be failed. If the learner overshoots, the page offers Rewind and the task stays open.
- **Expert path.** The five Plan 4 step sizes stay in an "Expert" drawer. Their tests stay, updated where the page markup changes.

## Left to the builder

- The exact visual design, the wording of each walk sentence, and how the glass draws each CPU part.
- The exact predicate syntax in walk files.
- How many tasks Plan 5 has and in what order.
