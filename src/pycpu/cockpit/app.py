"""The Cockpit's web app: routes only, over one `Cockpit` session.

Think of the cockpit's radio to the ground crew: each message is read, passed to the
pilot, and the answer read back. Visitors can freeze the flight, nudge it forward
(`/api/step`), wind it back (`/api/rewind`), let it play (`/api/run`), load a new
program (`/api/program`, or `/api/pebble` for one that comes with its lyric sheet),
read its dials (`/api/machine`) and ask what any part is carrying (`/api/view`).
These routes only parse the request, call the session and answer; every rule lives
in `session.py` and every dial in `picture.py`.
"""

from collections.abc import Generator, Mapping
from contextlib import contextmanager
from importlib import resources

from pebble import PebbleError
from pyweb.app import App
from pyweb.messages import HTTPError, HttpRequest, HttpResponse, JsonValue, html, json

from pycpu.cockpit.picture import machine_picture
from pycpu.cockpit.session import MAX_GATE_STEPS, MAX_RUN, Cockpit, CockpitBusy, CockpitRefusal
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


def _step_request(request: HttpRequest) -> tuple[StepSize, int]:
    """Read a `POST /api/step` body as a step size and a count, or raise a 400."""
    body = _object(request, "a size")
    size = body.get("size")
    if size not in tuple(StepSize):
        sizes = ", ".join(f'"{s}"' for s in StepSize)
        raise HTTPError(BAD_REQUEST, f"size must be one of {sizes}")
    return StepSize(str(size)), _whole_number(body, "count", MAX_GATE_STEPS, 1)


def _text(request: HttpRequest, what: str, complaint: str) -> str:
    """Return the `source` text of a request body, or raise a 400 with `complaint`."""
    source = _object(request, what).get("source")
    if not isinstance(source, str):
        raise HTTPError(BAD_REQUEST, complaint)
    return source


def create_cockpit(address_bits: int = RAM_ADDRESS_BITS, start_example: str | None = None) -> App:
    """Build the Cockpit app around one `Cockpit` session, paused at the demo program's start.

    Args:
        address_bits: How many address wires the RAM has. The real Cockpit uses the
            full 12 (4,096 words), which takes a few seconds to build; tests and the
            docs use 6 (64 words).
        start_example: A file stem in `cockpit/examples/` to load at the start. Not
            available yet: any value other than None raises `ValueError`.

    Returns:
        A PyWeb `App` with the routes `GET /` (the page), `GET /api/machine`,
        `GET /api/view`, `POST /api/step`, `POST /api/rewind`, `POST /api/run`,
        `POST /api/program` and `POST /api/pebble`. See the Cockpit page in the docs
        for each one.

    Raises:
        ValueError: If `start_example` is given.

    """
    if start_example is not None:
        msg = f"no example called {start_example}"
        raise ValueError(msg)
    cockpit = Cockpit(address_bits)
    page = resources.files("pycpu.cockpit").joinpath("page.html").read_text(encoding="utf-8")
    app = App()

    def answer() -> HttpResponse:
        """Answer with the machine picture, as every route that moves the machine does."""
        return json(machine_picture(cockpit))  # pyright: ignore[reportArgumentType]

    @app.get("/")
    def front_page(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Serve the Cockpit page."""
        return html(page)

    @app.get("/api/machine")
    def machine(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Describe the computer as it is now."""
        return answer()

    @app.get("/api/view")
    def view(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Describe the part named by `?path=`, or the whole circuit with no path."""
        path = request.query.get("path", "") or ""
        try:
            described = circuit_view(cockpit.computer.gate.simulator, path)
        except KeyError:
            raise HTTPError(NOT_FOUND, f"No part called {path}") from None
        return json(described)  # pyright: ignore[reportArgumentType]

    @app.post("/api/step")
    def step(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Step by a gate (`count` of them), a clock beat or an instruction."""
        size, count = _step_request(request)
        with _as_http():
            cockpit.step(size, count)
        return answer()

    @app.post("/api/rewind")
    def rewind(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Go back to the start of the current instruction."""
        with _as_http():
            cockpit.rewind()
        return answer()

    @app.post("/api/run")
    def run(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Resume, run some instructions on the fast engine, and pause again."""
        body = _object(request, "a number of instructions")
        instructions = _whole_number(body, "instructions", MAX_RUN, None)
        with _as_http():
            cockpit.run(instructions)
        return answer()

    @app.post("/api/program")
    def program(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Assemble new source and load it, or answer 400 naming the faulty line."""
        source = _text(request, "the assembly text as source", "source must be the assembly text")
        with _as_http():
            cockpit.load_assembly(source)
        return answer()

    @app.post("/api/pebble")
    def pebble(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Translate a Pebble program and load it, or answer 400 naming the line and column."""
        complaint = "source must be the Pebble program's text"
        source = _text(request, "the Pebble program as source", complaint)
        try:
            with _as_http():
                cockpit.load_pebble(source)
        except (PebbleError, UnsupportedFeature) as error:
            return refusal(error)
        return answer()

    return app
