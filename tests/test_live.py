"""Tests for play, pause and the live `machine` events of the Cockpit.

Like listening to a match on the radio: we tune in to `/api/events`, press Play, and
check that the commentator says the right thing at the right moments, to everyone
listening, and goes quiet once Pause is pressed.
"""

import json as json_lib
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, cast

import pytest
from pynet.loop import Task, run, sleep, spawn
from pyweb.messages import JsonValue
from pyweb.sse import EventHub, ServerEvent
from pyweb.testing import TestClient, TestResponse

from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.session import (
    BUSY_MESSAGE,
    MAX_RUN,
    MAX_SPEED,
    TICK_SECONDS,
    Cockpit,
    CockpitBusy,
    CockpitRefusal,
)
from pycpu.computer import StepSize

OK = 200
BAD_REQUEST = 400
CONFLICT = 409
SMALL = 6
PEBBLE_BITS = 8
FAST_TICK = 0.01
QUICK_TICK = 0.05
ONE_PER_QUICK_TICK = 20  # 20 a second x 0.05 seconds = 1 instruction a tick
ONE_PER_FAST_TICK = 100  # 100 a second x 0.01 seconds = 1 instruction a tick
SLOW_SPEED = 1  # 1 a second x 0.1 seconds: nothing runs for the first 9 ticks
FRACTION_SPEED = 3
FRACTION_TICKS = 10
FRACTION_PCS = [0, 0, 0, 1, 1, 1, 2, 2, 2, 3]  # 0.3 a tick, carried
ONE_TICK_PCS = [1, 2, 3, 4]
COUNT_UP = "    addi r1, 1\n" * 30 + "    halt\n"  # pc goes up by 1 per instruction
SAY_A = "    set r1, 0xFFFF\n    li r2, 65\n    store r2, [r1]\n    halt\n"
SAY_A_INSTRUCTIONS = 5  # set is two words: li and lhi
PEBBLE = "let n = 2\nprint(n)\n"
SETTLE = 0.05  # long enough for a few fast ticks
SENTINEL = ServerEvent("the end of this test", event="sentinel")
BAD_SPEED = f"speed must be a whole number from 1 to {MAX_SPEED}"
MAX_TICK_INSTRUCTIONS = 10_000  # MAX_SPEED x TICK_SECONDS
TWO_LISTENERS = 2
TWO_INSTRUCTIONS = 2
GATES_PAST_THE_EDGE = 2  # the first gate step is a clock edge, not a gate


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run one coroutine to the end on a fresh loop."""
    return run(coro)


def _json(response: TestResponse) -> dict[str, Any]:
    """Return a response's JSON body as a dictionary."""
    return cast("dict[str, Any]", response.json())


def _picture(event: ServerEvent) -> dict[str, Any]:
    """Return the machine picture an event carries."""
    return cast("dict[str, Any]", json_lib.loads(event.data))


@dataclass
class Rig:
    """A Cockpit app with its session and event hub in reach of the test."""

    client: TestClient
    session: Cockpit
    hub: EventHub

    async def listen(self, count: int) -> Task[list[ServerEvent]]:
        """Tune in a new listener for `count` events, and wait until it is subscribed."""
        before = self.hub.subscriber_count
        task = spawn(self.client.stream("/api/events", count=count))
        while self.hub.subscriber_count == before:
            await sleep(0)
        return task

    async def post(self, path: str, body: JsonValue = None) -> TestResponse:
        """Send a POST with a JSON body (an empty object when none is given)."""
        return await self.client.post(path, json={} if body is None else body)

    async def machine(self) -> dict[str, Any]:
        """Return the machine picture as `GET /api/machine` answers it."""
        return _json(await self.client.get("/api/machine"))


@pytest.fixture
def rig_maker(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Rig]:
    """Return a builder for a `Rig`, recording the session and hub the app makes."""
    sessions: list[Cockpit] = []
    hubs: list[EventHub] = []

    class RecordingCockpit(Cockpit):
        """A Cockpit that tells the test about itself."""

        def __init__(self, address_bits: int) -> None:
            """Build as usual and record this session."""
            super().__init__(address_bits)
            sessions.append(self)

    class RecordingHub(EventHub):
        """An event hub that tells the test about itself."""

        def __init__(self) -> None:
            """Build as usual and record this hub."""
            super().__init__()
            hubs.append(self)

    monkeypatch.setattr("pycpu.cockpit.app.Cockpit", RecordingCockpit)
    monkeypatch.setattr("pycpu.cockpit.app.EventHub", RecordingHub)

    def make(address_bits: int = SMALL, tick_seconds: float = FAST_TICK) -> Rig:
        """Build the app and hand back its client, session and hub."""
        client = TestClient(create_cockpit(address_bits, tick_seconds=tick_seconds))
        return Rig(client, sessions[-1], hubs[-1])

    return make


class TestEveryMovePublishes:
    """Every route that moves the machine sends one event, the same as its answer."""

    def test_each_move_publishes_exactly_one_event_with_its_answer(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """Steps, rewind, run, loads, play and pause each publish once; refusals publish nothing."""
        rig = rig_maker(PEBBLE_BITS)
        moves: list[tuple[str, JsonValue]] = [
            ("/api/step", {"size": "instruction"}),
            ("/api/step", {"size": "gate", "count": 3}),
            ("/api/rewind", {}),
            ("/api/run", {"instructions": 1}),
            ("/api/program", {"source": COUNT_UP}),
            ("/api/pebble", {"source": PEBBLE}),
            ("/api/step", {"size": "line"}),
            ("/api/play", {"speed": SLOW_SPEED}),
            ("/api/pause", {}),
        ]

        async def main() -> tuple[list[ServerEvent], list[bytes]]:
            """Make every move while listening, then mark the end with a sentinel."""
            listener = await rig.listen(len(moves) + 1)
            answers: list[bytes] = []
            for path, body in moves:
                response = await rig.post(path, body)
                assert response.status == OK, response.text
                answers.append(response.body)
            # Refusals and a pause while paused do not move the machine, so stay quiet.
            assert (await rig.post("/api/step", {"size": "sideways"})).status == BAD_REQUEST
            assert (await rig.post("/api/pause")).status == OK
            assert (await rig.post("/api/play", {"speed": 0})).status == BAD_REQUEST
            rig.hub.publish(SENTINEL)
            return await listener, answers

        events, answers = _run(main())
        assert events[-1] == SENTINEL
        assert [event.event for event in events[:-1]] == ["machine"] * len(moves)
        assert [event.data.encode() for event in events[:-1]] == answers


class TestPlaySpeed:
    """Play runs `speed x tick` instructions a tick, carrying fractions to the next one."""

    def test_speed_20_with_tick_005_runs_one_instruction_a_tick(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """Each tick's event shows pc one further on than the last."""
        rig = rig_maker(SMALL, QUICK_TICK)

        async def main() -> list[ServerEvent]:
            """Play a counting program and hear the play answer and four ticks."""
            await rig.post("/api/program", {"source": COUNT_UP})
            listener = await rig.listen(1 + len(ONE_TICK_PCS))
            await rig.post("/api/play", {"speed": ONE_PER_QUICK_TICK})
            events = await listener
            await rig.post("/api/pause")
            return events

        pictures = [_picture(event) for event in _run(main())]
        assert pictures[0]["pc"] == 0
        assert [picture["pc"] for picture in pictures[1:]] == ONE_TICK_PCS
        assert all(picture["running"] for picture in pictures)

    def test_speed_3_with_tick_01_carries_fractions(self, rig_maker: Callable[..., Rig]) -> None:
        """0.3 instructions a tick: 3 instructions over 10 ticks, never lost to rounding."""
        rig = rig_maker(SMALL, TICK_SECONDS)

        async def main() -> list[ServerEvent]:
            """Play slowly and hear ten ticks."""
            await rig.post("/api/program", {"source": COUNT_UP})
            listener = await rig.listen(1 + FRACTION_TICKS)
            await rig.post("/api/play", {"speed": FRACTION_SPEED})
            events = await listener
            await rig.post("/api/pause")
            return events

        pictures = [_picture(event) for event in _run(main())]
        assert [picture["pc"] for picture in pictures[1:]] == FRACTION_PCS

    def test_the_fastest_tick_is_one_run_of_the_most_instructions(self) -> None:
        """At `MAX_SPEED` a standard tick asks for `MAX_RUN` instructions, the same as Run."""
        assert round(MAX_SPEED * TICK_SECONDS) == MAX_TICK_INSTRUCTIONS == MAX_RUN


class TestPlayToTheEnd:
    """Play that reaches a halt stops by itself, paused, and says so once."""

    def test_play_to_a_halt_ends_paused_with_the_output(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """The last event is not running, is paused, has the output, and nothing follows."""
        rig = rig_maker()

        async def main() -> tuple[list[ServerEvent], dict[str, Any]]:
            """Play a program that prints A and halts; listen past its end."""
            await rig.post("/api/program", {"source": SAY_A})
            listener = await rig.listen(1 + SAY_A_INSTRUCTIONS + 1)
            await rig.post("/api/play", {"speed": ONE_PER_FAST_TICK})
            while rig.session.playing:
                await sleep(FAST_TICK)
            await sleep(SETTLE)  # a loop still running would publish again here
            rig.hub.publish(SENTINEL)
            return await listener, await rig.machine()

        events, machine = _run(main())
        assert events[-1] == SENTINEL
        last = _picture(events[-2])
        assert last["running"] is False
        assert last["paused"] is True
        assert last["halted"] is True
        assert last["output"] == "A"
        assert all(_picture(event)["running"] for event in events[:-2])
        assert machine == last


class TestButtonsWhilePlaying:
    """While playing, only pause and loads may move the machine (Review Focus)."""

    def test_step_rewind_run_and_play_are_409_and_change_nothing(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """Every other move answers 409 with the contract's message, and the picture stays."""
        rig = rig_maker(SMALL, TICK_SECONDS)
        refused: list[tuple[str, JsonValue]] = [
            *(("/api/step", {"size": str(size)}) for size in StepSize),
            ("/api/step", {"size": "gate", "count": 5}),
            ("/api/rewind", {}),
            ("/api/run", {"instructions": 1}),
            ("/api/play", {"speed": SLOW_SPEED}),
        ]

        async def main() -> list[TestResponse]:
            """Start slow play, then press every refused button."""
            await rig.post("/api/program", {"source": COUNT_UP})
            await rig.post("/api/play", {"speed": SLOW_SPEED})
            before = await rig.machine()
            answers = [await rig.post(path, body) for path, body in refused]
            assert await rig.machine() == before
            await rig.post("/api/pause")
            return answers

        for response in _run(main()):
            assert response.status == CONFLICT
            assert _json(response) == {"error": "Conflict", "message": BUSY_MESSAGE}

    def test_a_line_step_while_playing_is_409(self, rig_maker: Callable[..., Rig]) -> None:
        """A Pebble line step is refused the same way."""
        rig = rig_maker(PEBBLE_BITS, TICK_SECONDS)

        async def main() -> TestResponse:
            """Play a Pebble program slowly and press next line."""
            await rig.post("/api/pebble", {"source": PEBBLE})
            await rig.post("/api/play", {"speed": SLOW_SPEED})
            answer = await rig.post("/api/step", {"size": "line"})
            await rig.post("/api/pause")
            return answer

        assert _run(main()).status == CONFLICT

    def test_pause_stops_play_at_a_boundary(self, rig_maker: Callable[..., Rig]) -> None:
        """After pause the machine is paused in the gates and pc stays put."""
        rig = rig_maker()

        async def main() -> tuple[dict[str, Any], dict[str, Any]]:
            """Play for a moment, pause, wait, and look again."""
            await rig.post("/api/program", {"source": COUNT_UP})
            await rig.post("/api/play", {"speed": ONE_PER_FAST_TICK})
            await sleep(SETTLE)
            paused = _json(await rig.post("/api/pause"))
            await sleep(SETTLE)
            return paused, await rig.machine()

        paused, later = _run(main())
        assert paused["running"] is False
        assert paused["paused"] is True
        assert paused["at_boundary"] is True
        assert paused["pc"] > 0
        assert later == paused

    def test_pause_while_paused_answers_the_picture_unchanged(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """Pressing pause with nothing playing changes nothing."""
        rig = rig_maker()

        async def main() -> tuple[dict[str, Any], dict[str, Any]]:
            """Look, then pause."""
            return await rig.machine(), _json(await rig.post("/api/pause"))

        before, after = _run(main())
        assert after == before

    @pytest.mark.parametrize("route", ["/api/program", "/api/pebble"])
    def test_loading_stops_play_first(self, rig_maker: Callable[..., Rig], route: str) -> None:
        """A load while playing stops play, loads, and the old play never moves it again."""
        rig = rig_maker(PEBBLE_BITS)
        source = COUNT_UP if route == "/api/program" else PEBBLE

        async def main() -> tuple[dict[str, Any], dict[str, Any]]:
            """Play, load, wait, and look again."""
            await rig.post("/api/program", {"source": COUNT_UP})
            await rig.post("/api/play", {"speed": ONE_PER_FAST_TICK})
            await sleep(SETTLE)
            loaded = _json(await rig.post(route, {"source": source}))
            await sleep(SETTLE)
            return loaded, await rig.machine()

        loaded, later = _run(main())
        assert loaded["running"] is False
        assert loaded["paused"] is True
        assert loaded["pc"] == 0
        assert later == loaded

    def test_play_again_after_pause_runs_one_loop(self, rig_maker: Callable[..., Rig]) -> None:
        """Pause and play at once: the old loop is gone, so each tick still runs one instruction."""
        rig = rig_maker(SMALL, QUICK_TICK)

        async def main() -> list[ServerEvent]:
            """Play, pause, play again, and hear four ticks."""
            await rig.post("/api/program", {"source": COUNT_UP})
            await rig.post("/api/play", {"speed": ONE_PER_QUICK_TICK})
            await rig.post("/api/pause")
            listener = await rig.listen(1 + len(ONE_TICK_PCS))
            await rig.post("/api/play", {"speed": ONE_PER_QUICK_TICK})
            events = await listener
            await rig.post("/api/pause")
            return events

        pictures = [_picture(event) for event in _run(main())]
        assert [picture["pc"] for picture in pictures[1:]] == ONE_TICK_PCS


class TestPlayRequests:
    """`/api/play` checks its speed like every other number the Cockpit takes."""

    @pytest.mark.parametrize("speed", [0, MAX_SPEED + 1, True, "fast", None, 1.5])
    def test_a_bad_speed_is_400(self, rig_maker: Callable[..., Rig], speed: JsonValue) -> None:
        """Zero, too fast, a boolean, text, missing or a fraction is refused, and nothing plays."""
        rig = rig_maker()
        body: JsonValue = {} if speed is None else {"speed": speed}

        async def main() -> tuple[TestResponse, dict[str, Any]]:
            """Ask to play and look."""
            return await rig.post("/api/play", body), await rig.machine()

        response, machine = _run(main())
        assert response.status == BAD_REQUEST
        assert _json(response)["message"] == BAD_SPEED
        assert machine["running"] is False

    def test_a_body_that_is_not_an_object_is_400(self, rig_maker: Callable[..., Rig]) -> None:
        """A list instead of an object is refused."""
        rig = rig_maker()
        assert _run(rig.post("/api/play", [1])).status == BAD_REQUEST

    def test_play_answers_the_running_picture_at_once(self, rig_maker: Callable[..., Rig]) -> None:
        """The answer to play is the picture from the fast engine, running and not paused."""
        rig = rig_maker(SMALL, TICK_SECONDS)

        async def main() -> dict[str, Any]:
            """Play slowly, then pause."""
            answer = _json(await rig.post("/api/play", {"speed": SLOW_SPEED}))
            await rig.post("/api/pause")
            return answer

        answer = _run(main())
        assert answer["running"] is True
        assert answer["paused"] is False
        assert answer["phase"] == "fetch"


class TestListeners:
    """Every open page hears every event; a page that leaves is forgotten (Review Focus)."""

    def test_two_listeners_hear_every_event_and_one_may_leave_early(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """Both hear the same events; the one that leaves early drops the count by one."""
        rig = rig_maker()
        early = 2

        async def main() -> tuple[list[ServerEvent], list[ServerEvent], int, bool]:
            """Tune in two pages, play to the end, and let one page leave after two events."""
            await rig.post("/api/program", {"source": SAY_A})
            whole = await rig.listen(1 + SAY_A_INSTRUCTIONS)
            part = await rig.listen(early)
            assert rig.hub.subscriber_count == TWO_LISTENERS
            await rig.post("/api/play", {"speed": ONE_PER_FAST_TICK})
            heard_part = await part
            left, still_playing = rig.hub.subscriber_count, rig.session.playing
            return await whole, heard_part, left, still_playing

        whole, part, left, still_playing = _run(main())
        assert part == whole[:early]
        assert left == 1
        assert still_playing
        assert _picture(whole[-1])["halted"] is True
        assert _picture(whole[-1])["running"] is False
        assert rig.hub.subscriber_count == 0


class TestThePictureWhilePlaying:
    """While playing there is no gate detail, and the zoom shows the last paused view."""

    def test_variables_and_last_gate_are_null_and_it_is_at_a_boundary(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """Driven through the real `/api/play`: no variables, no last gate, at a boundary."""
        rig = rig_maker(PEBBLE_BITS, TICK_SECONDS)

        async def main() -> tuple[dict[str, Any], dict[str, Any]]:
            """Step to a line with a variable, then past the clock edge to a gate, then play."""
            await rig.post("/api/pebble", {"source": PEBBLE})
            await rig.post("/api/step", {"size": "line"})
            gates: JsonValue = {"size": "gate", "count": GATES_PAST_THE_EDGE}
            before = _json(await rig.post("/api/step", gates))
            playing = _json(await rig.post("/api/play", {"speed": SLOW_SPEED}))
            await rig.post("/api/pause")
            return before, playing

        before, playing = _run(main())
        assert before["variables"] is not None
        assert before["last_gate"] is not None
        assert before["at_boundary"] is False
        assert playing["variables"] is None
        assert playing["last_gate"] is None
        assert playing["at_boundary"] is True
        assert playing["running"] is True

    def test_the_view_is_the_gate_engine_as_last_paused(
        self, rig_maker: Callable[..., Rig]
    ) -> None:
        """`/api/view` still answers while playing, with the values from the last pause."""
        rig = rig_maker()

        async def main() -> tuple[TestResponse, TestResponse, dict[str, Any]]:
            """Look at the program counter, play on, and look again."""
            await rig.post("/api/program", {"source": COUNT_UP})
            paused = await rig.client.get("/api/view?path=cpu.pc")
            await rig.post("/api/play", {"speed": ONE_PER_FAST_TICK})
            await sleep(SETTLE)
            playing = await rig.client.get("/api/view?path=cpu.pc")
            machine = await rig.machine()
            await rig.post("/api/pause")
            return paused, playing, machine

        paused, playing, machine = _run(main())
        assert playing.status == OK
        assert playing.json() == paused.json()
        assert machine["pc"] > 0


class TestTheSession:
    """`start_playing`, `play_tick` and `stop_playing`, without the web app."""

    def test_start_tick_and_stop(self) -> None:
        """Start resumes, a tick runs on the fast engine, stop pauses in the gates."""
        cockpit = Cockpit(SMALL)
        cockpit.load_assembly(COUNT_UP)
        cockpit.start_playing()
        assert cockpit.playing
        assert not cockpit.computer.paused
        cockpit.note = "old"
        start = cockpit.computer.state()
        assert cockpit.play_tick(TWO_INSTRUCTIONS) is True
        assert cockpit.before == start
        assert cockpit.note is None
        assert cockpit.computer.state().pc == TWO_INSTRUCTIONS
        cockpit.stop_playing()
        assert not cockpit.playing
        assert cockpit.computer.paused

    def test_a_tick_that_halts_says_false(self) -> None:
        """A tick that reaches the halt reports False."""
        cockpit = Cockpit(SMALL)
        cockpit.load_assembly(SAY_A)
        cockpit.start_playing()
        assert cockpit.play_tick(SAY_A_INSTRUCTIONS) is False

    def test_start_while_playing_is_busy_and_a_tick_needs_play(self) -> None:
        """Starting twice is busy; a tick while stopped is refused; stopping twice is fine."""
        cockpit = Cockpit(SMALL)
        with pytest.raises(CockpitRefusal, match="press play first"):
            cockpit.play_tick(1)
        cockpit.start_playing()
        with pytest.raises(CockpitBusy, match=BUSY_MESSAGE):
            cockpit.start_playing()
        cockpit.stop_playing()
        cockpit.stop_playing()
        assert cockpit.computer.paused

    def test_a_load_stops_play(self) -> None:
        """Loading while playing stops play and leaves the new program paused at its start."""
        cockpit = Cockpit(SMALL)
        cockpit.start_playing()
        cockpit.play_tick(1)
        cockpit.load_assembly(SAY_A)
        assert not cockpit.playing
        assert cockpit.computer.paused
        assert cockpit.computer.state().pc == 0
