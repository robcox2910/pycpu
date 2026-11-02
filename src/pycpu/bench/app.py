"""The Bench's web app: one real ALU, a page to look at it, and two small routes.

Think of a workshop with a single radio on the bench. Visitors can turn its dial
(`/api/inputs`) and ask what any part is carrying (`/api/view`), but the radio is
always the same real one. Here the radio is an ALU built from NAND gates, and the
answers come from its simulator, never from a copy.
"""

from collections.abc import Mapping
from importlib import resources

from pyweb.app import App
from pyweb.messages import HTTPError, HttpRequest, HttpResponse, html, json

from pycpu.arithmetic import AluOp, alu
from pycpu.circuit import Circuit
from pycpu.simulator import Simulator
from pycpu.view import circuit_view

WORD_BITS = 16
OP_BITS = 3
MAX_WORD = (1 << WORD_BITS) - 1
BAD_REQUEST = 400
NOT_FOUND = 404


def _read_number(body: Mapping[str, object], name: str, largest: int) -> int:
    """Return `body[name]` as a whole number from 0 to `largest`, or raise a 400.

    Booleans are refused even though Python counts them as numbers, because
    `true` is not what anyone means by the number 1 on a dial.
    """
    value = body.get(name)
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= largest:
        msg = f"{name} must be a whole number from 0 to {largest}"
        raise HTTPError(BAD_REQUEST, msg)
    return value


def create_bench() -> App:
    """Build the Bench app, with a fresh ALU switched on and all inputs at 0.

    Returns:
        A PyWeb `App` with three routes: `GET /` (the page), `GET /api/view`
        (look inside a part) and `POST /api/inputs` (turn the dial).

    """
    circuit = Circuit()
    a = circuit.bus_input("a", WORD_BITS)
    b = circuit.bus_input("b", WORD_BITS)
    op = circuit.bus_input("op", OP_BITS)
    out = alu(circuit, a, b, op)
    sim = Simulator(circuit)
    sim.settle()
    page = resources.files("pycpu.bench").joinpath("page.html").read_text(encoding="utf-8")
    app = App()

    @app.get("/")
    def front_page(_request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Serve the Bench page."""
        return html(page)

    @app.get("/api/view")
    def view(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Describe the part named by `?path=`, or the whole circuit with no path."""
        path = request.query.get("path", "") or ""
        try:
            described = circuit_view(sim, path)
        except KeyError:
            raise HTTPError(NOT_FOUND, f"No part called {path}") from None
        return json(described)  # pyright: ignore[reportArgumentType]

    @app.post("/api/inputs")
    def inputs(request: HttpRequest) -> HttpResponse:  # pyright: ignore[reportUnusedFunction]
        """Set a, b and op, let the gates settle, and report the result and flags."""
        body = request.json()
        if not isinstance(body, dict):
            raise HTTPError(BAD_REQUEST, "send a JSON object with a, b and op")
        fields = body
        first = _read_number(fields, "a", MAX_WORD)
        second = _read_number(fields, "b", MAX_WORD)
        setting = _read_number(fields, "op", len(AluOp) - 1)
        sim.set_bus(a, first)
        sim.set_bus(b, second)
        sim.set_bus(op, setting)
        sim.settle()
        return json(
            {
                "result": sim.get_bus(out.result),
                "zero": sim.get(out.zero),
                "negative": sim.get(out.negative),
                "carry": sim.get(out.carry),
                "overflow": sim.get(out.overflow),
            }
        )

    return app
