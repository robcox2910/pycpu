# Watching It Run

## Live Radio Commentary of a Match

Imagine a football match you cannot see, because you are stuck at home. You could ring
a friend at the ground every minute: "What's the score?" "Still nil-nil." "What's the
score?" "Still nil-nil." That is tiring for both of you, and you would still miss the
goal that went in between two calls.

So instead you turn on the **radio**. The commentator talks whenever something happens:
a pass, a shot, a goal. Nobody has to keep ringing up to ask the score; the news comes
to you the moment it happens, and everyone with a radio hears the same words at the same
time. And when something exciting happens and you want a proper look, the TV has a
**replay camera**: it freezes the match on one moment, so you can study where every
player is standing.

The Cockpit works the same way. Pressing **Play** lets the computer run on its own, and
the server is the commentator: several times a second it tells every open page what the
machine looks like now, without the page asking. These live messages are called
**events**. Pressing **Pause** is the replay camera: the machine freezes just before an
instruction, inside the gate engine, so you can zoom into any wire and gate again.

| At the match | In PyCPU |
|--------------|----------|
| The match carrying on by itself | Play: `POST /api/play` with `{"speed": n}`, which calls `Cockpit.start_playing` |
| How fast the match runs | `speed`: instructions a second, from 1 to `MAX_SPEED` (100,000) |
| How often the commentator speaks | A **tick**: every `TICK_SECONDS` (a tenth of a second) |
| What happens on the pitch between two comments | `Cockpit.play_tick`: one slice of instructions on the fast engine |
| One thing the commentator says | One `machine` event: a `ServerEvent` holding the whole machine picture |
| Switching your radio on | `GET /api/events`, an `EventStream` |
| The studio that talks to every radio at once | An `EventHub`, which the Cockpit publishes to |
| The replay camera | Pause: `POST /api/pause`, which calls `Cockpit.stop_playing` and loads the gate engine |
| "No replays while the ball is in play" | While playing, `/api/view` gives the last *paused* view of the gates, never a live one |

`ServerEvent`, `EventStream` and `EventHub` come from PyWeb, the web server in this
series; its page [Server-Sent Events](https://robcox2910.github.io/pyweb/concepts/server-sent-events/)
explains how the radio itself is built.

## Try It

We start a Cockpit with its little demo program (the countdown that prints `321`) and
press Play at 50 instructions a second. To keep the example quick we make each tick a
hundredth of a second (`tick_seconds=0.01`) instead of the usual tenth. Then we switch
the radio on, listen to the first three events, and press Pause.

```python
import json

from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit


async def watch() -> None:
    client = TestClient(create_cockpit(address_bits=6, tick_seconds=0.01))
    machine = (await client.post("/api/play", json={"speed": 50})).json()
    print("play:   pc", machine["pc"], "running", machine["running"])
    for event in await client.stream("/api/events", count=3):
        picture = json.loads(event.data)
        pc, running, text = picture["pc"], picture["running"], picture["instruction"]["text"]
        print(event.event, "event: pc", pc, "running", running, "next:", text)
    machine = (await client.post("/api/pause")).json()
    print("pause:  pc", machine["pc"], "running", machine["running"])
    print("paused in the gates:", machine["paused"], "at a boundary:", machine["at_boundary"])


run(watch())
# Output:
# play:   pc 0 running True
# machine event: pc 0 running True next: li r1, 255
# machine event: pc 1 running True next: lhi r1, 255
# machine event: pc 1 running True next: lhi r1, 255
# pause:  pc 1 running False
# paused in the gates: True at a boundary: True
```

Pressing Play answers straight away with the picture, `running` now true. Then the
events arrive, one a tick. At 50 instructions a second and 100 ticks a second, each tick
owes **half** an instruction. The first tick owes a half, so it runs nothing and `pc`
stays at 0. The second tick owes another half, which makes one whole instruction: it
runs `li r1, 255`, and `pc` moves to 1. The third tick owes a half again, and runs
nothing. Pause then stops play and puts the machine back in the gates, just before
`lhi r1, 255`, ready to look inside.

(`set r1, 0xFFFF` in the demo program is two instructions, `li` and `lhi`, which is why
the instruction texts are not the line you wrote; see
[Assembly Language](assembly-language.md).)

## How It Works

### Slices, not one long run

The code is in `src/pycpu/cockpit/app.py` (the routes and the play loop) and
`src/pycpu/cockpit/session.py` (the rules: `start_playing`, `play_tick`,
`stop_playing`).

A computer that simply ran until it finished would never let anyone else speak: no
pause button, no live pictures, and a program that loops forever would hang the
Cockpit for good. So play runs in small **slices**, one a tick:

```text
  POST /api/play {"speed": 50}
        |
        |  start_playing(): resume() finishes any half-done instruction in the
        |  gates, then copies everything to the fast engine; playing = True
        v
  +-------------------- the play loop (one per Cockpit) ---------------------+
  |                                                                          |
  |   owed = owed + speed x tick      (50 x 0.01 = 0.5 instructions)         |
  |   run the whole part of owed on the fast engine:  play_tick(n)           |
  |   keep the fraction for next time                                        |
  |   halted?  -> stop_playing() first: loads the gate engine, running false |
  |   publish the picture as one "machine" event  ---->  every open page     |
  |   halted?  -> stop (that event was the last one)                         |
  |   otherwise: sleep one tick, and go round again while still playing      |
  +--------------------------------------------------------------------------+
        |
        |  POST /api/pause:  stop_playing(): pause() copies everything into
        |  the gate engine, just before the next instruction; playing = False
        v
  paused in the gates, every wire real again
```

Each slice is `speed x tick` instructions, and that is often not a whole number. At 3
instructions a second and a tenth-of-a-second tick, a tick owes 0.3 of an instruction.
Rounding each tick down would run nothing, ever; rounding up would run 10 a second
instead of 3. So the loop keeps what it owes, like pocket money saved up: 0.3, 0.6,
0.9, then 1.2, so it runs 1 and keeps 0.2. Over 10 ticks it runs exactly 3. (The sums
use exact fractions, Python's `Fraction`, because a computer's 0.1 is not quite a
tenth.) At the fastest speed, 100,000 a second, a tick runs 10,000 instructions, the
same as one press of **Run**.

### Fast engine while playing, gates at the end

Every slice runs on the **fast engine** (from [Two Engines](two-engines.md)), because
the gate engine is far too slow to watch a program go by. Play goes through `resume`
and `pause` from [Pausing and Rewinding](pausing-and-rewinding.md), never around them:
`resume` once at the start and `pause` once at the end. So the gate engine is loaded
only when play stops, whether by Pause, by a load, or by the program reaching its
`halt`.

### One loop, one thread

The play loop is a **task** on the same event loop as the web routes (PyNet's
`spawn`), not a separate thread. A task only lets others run when it reaches an
`await`, here the `sleep` between ticks. So a request is never handled half-way
through a slice, and the computer is only ever touched by one thing at a time. Pause
cancels the sleeping loop, so pressing Pause and then Play straight away can never
leave two loops both moving the machine.

### Buttons pressed while playing

While play is on, the only buttons that may move the machine are **Pause** and
**loading a program**. A step, rewind, run, line step or a second Play gets the answer
409 ("conflict") with the message `the computer is running: press pause first`, and
the machine is left alone. Loading a program stops play first, then loads, so the old
program can never carry on running inside the new one.

### Every move is news

Not only play talks on the radio. Every route that moves the machine (a step, rewind,
run, load, play or pause) answers with the picture *and* publishes exactly the same
picture as a `machine` event. So two tabs open on the same Cockpit both see every
change, whichever tab pressed the button. A tab that closes simply stops listening: the
hub forgets it, and play carries on to its end or to Pause for everyone else.

### Why looking inside waits for Pause

While playing, the **gate engine is not running at all**: the fast engine is doing the
work. The wires in the gate engine still hold the values from the last time it was
paused. Showing those as if they were live would be faking it, and this project never
fakes the gate view. So while playing, the picture's `variables` and `last_gate` are
`null`, and `at_boundary` is always true (the fast engine only stops between
instructions). If anyone asks `/api/view` while playing, the answer is the gate engine
**as it was last paused**, never something made up. The Cockpit page does not even ask:
while playing, its zoom panel just says "Pause to look inside the gates". Press Pause,
and every wire is real again.

## Why Does This Matter?

Without play, watching a program means pressing **Run** over and over and guessing what
happened in between. Without events, the page would have to keep asking "anything new?"
many times a second, and two tabs would disagree about what the machine is doing. With
both, you can sit back and watch the program counter race through the listing, the
registers flicker and the output appear, and then press Pause at the moment something
looks interesting and drop straight into the gates.

Real tools do the same. A debugger's **continue** and **break** buttons are play and
pause: the program runs at full speed, and only when it stops can you inspect every
variable. Live football scores, chat apps and stock tickers push news to your screen
the moment it happens, often with exactly these server-sent events, instead of making
your phone ask over and over.

## What's Next

You can now step the machine a gate, an instruction or a Pebble line at a time, or let
it play while you watch, and pause it to look inside. The Cockpit page puts all of
these buttons and pictures on one screen: go back to
[The Cockpit](the-cockpit.md) to see its layout, every pane and every route, or to
[Stepping a Pebble Line](stepping-a-pebble-line.md) to walk a program line by line.
