# Build It, Then Watch It: Design

Status: approved in chat by the owner (2026-11-07). The owner said "yes that matches, write it up as plan 6".
Builds on: the PyCPU spec (`2026-11-01-pycpu-design.md`) and the Cockpit for learners (Plan 5, PR #5).
Becomes: Plan 6. PyStack integration and the first release move to Plan 7.

## Why

After Plan 5 the owner said: "i kind of find this project slightly disconnected from the others.. the others are all about the code and how to build something, this is more a tool to show how somehting works, no?"

They are half right:

- Underneath, PyCPU is a build-it project like the rest of the series. Nearly every concept page builds its part in Python. For example, the half adder in `adding.md` is made of 6 NAND gates.
- Since Plan 5, though, the Cockpit is the front door, so the first thing a learner meets is a viewer. The two halves don't point at each other:
  - The Cockpit shows the ALU subtracting, but it never shows the Python that built the ALU.
  - The docs build each part, but they never say "now go and watch the part you just built".

The owner agreed with this reading.

## Goal

PyCPU reads as the series' "build the machine" project. You build a computer from NAND gates in code, and the Cockpit is where you check what you built and watch it work.

## Goals

1. **The Cockpit shows the code that built each part.**
   - Every CPU part view gets a "The code that built this" panel. It shows the real Python source of that part, read from the running program's own modules, not a copy.
   - The panel also gives the file and line, and names the concept page that explains the part.
   - The registers and RAM get their own part views, as Plan 5's spec asked. Plan 5's Ruling 14 deferred them.
2. **Walks point back to the docs.** A walk's last card names its concept page (the walk's `see_also`) as the place to read how that part is built.
3. **A build path through the docs.** A new page, "Build It Yourself", walks the existing concept pages in order, from NAND to running Pebble. Each step names:
   - what you build;
   - the function that builds it;
   - the concept page;
   - the test that checks it;
   - where to watch it in the Cockpit, if it can be watched there.
4. **The story leads with building.** The README, `index.md` and `from-scratch.md` open with "build a computer from NAND gates", and present the Cockpit as the place to check and watch what you built.

## Non-goals

- No change to what the machine computes. The pinned gate and wire counts stay the same: 15,525 gates and 15,529 wires at 6 address bits.
- No exercises where the learner writes their own parts and the machine grades them. The owner was offered that deeper change and chose this one.
- No PyStack, no release, no tag, no docs site, no series listing, and no links from other projects. Nothing is exposed until the owner says so.

## Anti-goals

- **A copy of the code that can drift.** The panel must show the source that actually built the circuit on screen, so it reads the live module.
- **A build path that is just the nav pasted again.** Each step must say what you build and how you know it works.

## Constraints

Everything in the PyCPU spec, the repo CLAUDE.md and Plan 5's Learners' Contract still binds:

- NAND is the only primitive, and the gate view is never faked.
- Docs come first and are written for a curious 12-year-old. Every figure is printed or pinned.
- The page stays one self-contained HTML file, with no `innerHTML` for server text and no external URLs.
- The page must not scroll at 1280×720.

## Calls I made (owner may override)

- **Where the docs link goes.** No docs site is published, so "read about it" links point at a docs server on your own computer, `http://127.0.0.1:8000/concepts/<page>/`, which `uv run mkdocs serve` starts. The panel says so in one sentence. The code itself shows inside the Cockpit, so the link is a bonus, not the bridge.
- **Which code to show.** The panel shows the builder function's source. When a builder method builds several parts (for example `_build_write_back` builds both write-back and the stack pointer), it shows only the `with c.scope("<part>"):` block for the part being viewed.
- **Registers and RAM views** show their real wires. For the registers, those are which register is being read and written, the value written, and the two values read out. For RAM, they are the address, the data in, the write wire and the data out. They show no list of every stored word: the glass already shows memory.
