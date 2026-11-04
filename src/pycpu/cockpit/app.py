"""The Cockpit's web app: routes only, over one `Cockpit` session.

Think of the cockpit's radio to the ground crew: each message is read, passed to the
pilot, and the answer read back. Visitors can freeze the flight, nudge it forward
(`/api/step`: one gate, a beat, an instruction or a whole Pebble line), wind it back
(`/api/rewind`), run it a set distance (`/api/run`), let it fly on its own and stop
it (`/api/play`, `/api/pause`), load a new program (`/api/program`, or `/api/pebble`
for one that comes with its lyric sheet), read its dials (`/api/machine`) and ask what
any part is carrying (`/api/view`). `/api/events` is the radio left switched on: after
every move, and every slice of play, the new picture goes out to every open page. These
routes only parse the request, call the session and answer; every rule lives in
`session.py` and every dial in `picture.py`.
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from fractions import Fraction
from importlib import resources
from typing import Literal

from pebble import PebbleError
from pynet.loop import Task, current_task, sleep, spawn
from pyweb.app import App
from pyweb.messages import HTTPError, HttpRequest, HttpResponse, JsonValue, html, json
from pyweb.sse import EventHub, EventStream, ServerEvent

from pycpu.cockpit.picture import listing, machine_picture
from pycpu.cockpit.session import (
    MAX_GATE_STEPS,
    MAX_RUN,
    MAX_SPEED,
    TICK_SECONDS,
    Cockpit,
    CockpitBusy,
    CockpitRefusal,
)
from pycpu.computer import StepSize
from pycpu.memory import RAM_ADDRESS_BITS
from pycpu.translator import UnsupportedFeature
from pycpu.view import circuit_view

BAD_REQUEST = 400
NOT_FOUND = 404
CONFLICT = 409


# The route checks type and range too so the 400 bodies stay byte-identical; the session
# re-checks so direct callers are safe.
def _whole_number(body: Mapping[str, object], name: str, largest: int, default: int | None) -> int:
    """Return `body[name]` as a whole number from 1 to `largest`, or raise a 400.

    A missing value takes `default` when there is one. Booleans are refused even
    though Python counts them as numbers, because `true` is not what anyone means
    by "run 1 instruction".
    """
    value = body.get(name, default)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= largest:
        msg = f"{name} must be a whole number from 1 to {largest}"
        raise HTTPError(BAD_REQUEST, msg)
    return value


def _object(request: HttpRequest, what: str) -> Mapping[str, object]:
    """Return the request's JSON body as an object, or raise a 400 saying what to send."""
    body = request.json()
    if not isinstance(body, dict):
        raise HTTPError(BAD_REQUEST, f"send a JSON object with {what}")
    return body


def refusal(error: PebbleError | UnsupportedFeature) -> HttpResponse:
    """Answer 400 with the error's message and the line and column it points at.

    The body has the same `error` and `message` as every other 400 from the Cockpit,
    plus `line` and `column` (1-based, or null when nobody knows) so the page could
    point at the place.
    """
    body: dict[str, JsonValue] = {
        "error": "Bad Request",
        "message": str(error),
        "line": error.line,
        "column": error.column,
    }
    return json(body, BAD_REQUEST)


class _ConflictError(HTTPError):
    """A 409 whose body says "Conflict": PyWeb has no reason phrase of its own for 409."""

    def __init__(self, message: str) -> None:
        """Store the 409 and the session's message."""
        super().__init__(CONFLICT, message)

    def to_response(self, request: HttpRequest) -> HttpResponse:  # noqa: ARG002
        """Answer with the usual `error` and `message` body, naming the status "Conflict"."""
        return json({"error": "Conflict", "message": self.message}, CONFLICT)


@contextmanager
def _as_http() -> Generator[None]:
    """Turn a session refusal into the HTTP error a route answers: 409 if busy, else 400."""
    try:
        yield
    except CockpitRefusal as error:
        if isinstance(error, CockpitBusy):
            raise _ConflictError(str(error)) from None
        raise HTTPError(BAD_REQUEST, str(error)) from None


# A line step's size, mapped to whether it steps into calls (True) or over them (False).
type LineSize = Literal["line", "line_into"]
LINE_SIZES: dict[LineSize, bool] = {"line": False, "line_into": True}


def _size(value: object) -> StepSize | LineSize | None:
    """Return `value` as a step size or a line size, or None if it is neither."""
    match value:
        case "line":
            return "line"
        case "line_into":
            return "line_into"
        case str() if value in tuple(StepSize):
            return StepSize(value)
        case _:
            return None


def _step_request(request: HttpRequest) -> tuple[StepSize | LineSize, int]:
    """Read a `POST /api/step` body as a step size (or a line size) and a count, or raise a 400."""
    body = _object(request, "a size")
    size = _size(body.get("size"))
    if size is None:
        sizes = ", ".join(f'"{s}"' for s in (*StepSize, *LINE_SIZES))
        raise HTTPError(BAD_REQUEST, f"size must be one of {sizes}")
    count = _whole_number(body, "count", MAX_GATE_STEPS, 1)
    if not isinstance(size, StepSize) and count != 1:
        raise HTTPError(BAD_REQUEST, "count is only for gate steps")
    return size, count


def _step(cockpit: Cockpit, size: StepSize | LineSize, count: int) -> None:
    """Make one step request's move: a gate, beat or instruction step, or a line step."""
    if isinstance(size, StepSize):
        cockpit.step(size, count)
    else:
        cockpit.step_line(into=LINE_SIZES[size])


def _text(request: HttpRequest, what: str, complaint: str) -> str:
    """Return the `source` text of a request body, or raise a 400 with `complaint`."""
    source = _object(request, what).get("source")
    if not isinstance(source, str):
        raise HTTPError(BAD_REQUEST, complaint)
    return source


class _Slicer:
    """Cut play into whole-instruction slices, carrying the leftover fraction to the next.

    At `speed` instructions a second and a tick of `tick_seconds`, each tick owes
    `speed x tick_seconds` instructions, which is often not a whole number (3 a
    second at 0.1 seconds is 0.3 a tick). Each slice runs the whole part of what is
    owed and keeps the rest, so nothing is lost to rounding. The sums use exact
    fractions, because floating-point 0.1 is not quite a tenth.
    """

    def __init__(self, speed: int, tick_seconds: float) -> None:
        """Work out the exact share of instructions each tick owes."""
        self.per_tick = speed * Fraction(repr(tick_seconds))
        self.owed = Fraction(0)

    def next(self) -> int:
        """Return how many whole instructions this tick runs, keeping the fraction."""
        self.owed += self.per_tick
        whole = int(self.owed)
        self.owed -= whole
        return whole


class _Live:
    """The Cockpit's commentator: the session, the event hub and the one play loop.

    Every route that moves the machine answers through `moved`, which also publishes
    the same picture to every listener. Play is a task on the routes' own event loop,
    so the computer is only ever touched from one thread, and a route never runs
    half-way through a slice.
    """

    def __init__(self, cockpit: Cockpit, tick_seconds: float) -> None:
        """Start with nobody listening and nothing playing."""
        self.cockpit = cockpit
        self.tick_seconds = tick_seconds
        self.hub = EventHub()
        # The play loop that may be running. A new play or a pause cancels it, so a
        # pause and a quick play again can never leave two loops moving the machine.
        self.player: Task[None] | None = None

    def answer(self) -> HttpResponse:
        """Answer with the machine picture, without telling anyone else (nothing moved)."""
        return json(machine_picture(self.cockpit))  # pyright: ignore[reportArgumentType]

    def moved(self) -> HttpResponse:
        """Answer with the machine picture, and publish the same JSON to every listener."""
        response = self.answer()
        self.hub.publish(ServerEvent(response.body.decode(), event="machine"))
        return response

    def _cancel_player(self) -> None:
        """Cancel the play loop if one is still waiting for its next tick."""
        if self.player is not None:
            self.player.cancel()
            self.player = None

    def play(self, speed: int) -> HttpResponse:
        """Start playing at `speed` instructions a second, and answer the running picture.

        Raises:
            CockpitBusy: If it is already playing.

        """
        self.cockpit.start_playing()
        self._cancel_player()
        self.player = spawn(self._loop(_Slicer(speed, self.tick_seconds)), name="cockpit play")
        return self.moved()

    def pause(self) -> HttpResponse:
        """Stop play at the next instruction boundary; if not playing, change nothing."""
        if not self.cockpit.playing:
            return self.answer()
        self._cancel_player()
        self.cockpit.stop_playing()
        return self.moved()

    async def _loop(self, slicer: _Slicer) -> None:
        """Run one slice a tick and publish it, until paused, loaded over, or halted."""
        cockpit = self.cockpit
        try:
            while cockpit.playing:
                going = cockpit.play_tick(slicer.next())
                if not going:
                    cockpit.stop_playing()  # loads the gate engine, at the halt
                self.moved()  # the one event for this tick; after a halt, the last
                if not going:
                    return
                await sleep(self.tick_seconds)
        finally:
            # Forget this loop once it ends, unless a newer play has already replaced it.
            if self.player is current_task():
                self.player = None


def create_cockpit(
    address_bits: int = RAM_ADDRESS_BITS,
    start_example: str | None = None,
    *,
    tick_seconds: float = TICK_SECONDS,
) -> App:
    """Build the Cockpit app around one `Cockpit` session, paused at the demo program's start.

    Args:
        address_bits: How many address wires the RAM has. The real Cockpit uses the
            full 12 (4,096 words), which takes a few seconds to build; tests and the
            docs use 6 (64 words).
        start_example: A file stem in `cockpit/examples/` to load at the start. Not
            available yet: any value other than None raises `ValueError`.
        tick_seconds: How long play waits between two slices; tests and the docs
            make it shorter to stay quick.

    Returns:
        A PyWeb `App` with the routes `GET /` (the page), `GET /api/machine`,
        `GET /api/listing`, `GET /api/view`, `GET /api/events`, `POST /api/step`,
        `POST /api/rewind`, `POST /api/run`, `POST /api/play`, `POST /api/pause`,
        `POST /api/program` and `POST /api/pebble`. See the Cockpit pages in the
        docs for each one.

    Raises:
        ValueError: If `start_example` is given.

    """
    if start_example is not None:
        msg = f"no example called {start_example}"
        raise ValueError(msg)
    live = _Live(Cockpit(address_bits), tick_seconds)
    app = App()
    _reading_routes(app, live)
    _moving_routes(app, live)
    _play_routes(app, live)
    return app


def _reading_routes(app: App, live: _Live) -> None:
    """Add the routes that only look: the page, the picture, the listing, the view, events."""
    cockpit = live.cockpit
    page = resources.files("pycpu.cockpit").joinpath("page.html").read_text(encoding="utf-8")

    @app.get("/")
    def front_page(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Serve the Cockpit page."""
        return html(page)

    @app.get("/api/machine")
    def machine(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Describe the computer as it is now."""
        return live.answer()

    @app.get("/api/listing")
    def rows(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """List every word of the loaded program, with its source line and labels."""
        return json(listing(cockpit))  # pyright: ignore[reportArgumentType]

    @app.get("/api/view")
    def view(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Describe the part named by `?path=`, or the whole circuit with no path.

        While playing this is the gate engine as it was last paused: the gates are
        not running then, and the fast engine has no wires to show.
        """
        path = request.query.get("path", "") or ""
        try:
            described = circuit_view(cockpit.computer.gate.simulator, path)
        except KeyError:
            raise HTTPError(NOT_FOUND, f"No part called {path}") from None
        return json(described)  # pyright: ignore[reportArgumentType]

    @app.get("/api/events")
    def events(_request: HttpRequest) -> EventStream:  # pyright: ignore[reportUnusedFunction]
        """Tune in to the live pictures: one `machine` event after every move and tick."""
        return EventStream(live.hub.subscribe())


def _moving_routes(app: App, live: _Live) -> None:
    """Add the routes that move the machine or load it; each publishes its answer."""
    cockpit = live.cockpit

    @app.post("/api/step")
    def step(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Step by a gate (`count` of them), a clock beat, an instruction or a Pebble line."""
        size, count = _step_request(request)
        with _as_http():
            _step(cockpit, size, count)
        return live.moved()

    @app.post("/api/rewind")
    def rewind(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Go back to the start of the current instruction."""
        with _as_http():
            cockpit.rewind()
        return live.moved()

    @app.post("/api/run")
    def run(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Resume, run some instructions on the fast engine, and pause again."""
        body = _object(request, "a number of instructions")
        instructions = _whole_number(body, "instructions", MAX_RUN, None)
        with _as_http():
            cockpit.run(instructions)
        return live.moved()

    @app.post("/api/program")
    def program(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Assemble new source and load it (stopping play first), or answer 400."""
        source = _text(request, "the assembly text as source", "source must be the assembly text")
        with _as_http():
            cockpit.load_assembly(source)
        return live.moved()

    @app.post("/api/pebble")
    def pebble(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Translate a Pebble program and load it (stopping play first), or answer 400."""
        complaint = "source must be the Pebble program's text"
        source = _text(request, "the Pebble program as source", complaint)
        try:
            with _as_http():
                cockpit.load_pebble(source)
        except (PebbleError, UnsupportedFeature) as error:
            return refusal(error)
        return live.moved()


def _play_routes(app: App, live: _Live) -> None:
    """Add play and pause."""

    @app.post("/api/play")
    def play(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Let the computer run on its own at `speed` instructions a second."""
        speed = _whole_number(_object(request, "a speed"), "speed", MAX_SPEED, None)
        with _as_http():
            return live.play(speed)

    @app.post("/api/pause")
    def pause(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Stop play just before the next instruction; if not playing, change nothing."""
        return live.pause()
