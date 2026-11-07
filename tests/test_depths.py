"""Tests for the four depths and the one Step button that follows them."""

from dataclasses import replace
from typing import Any, cast

from pynet.loop import run as run_loop
from pyweb.testing import TestClient, TestResponse

from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.picture import _PART_FOR_OPCODE, PART_NAMES, machine_picture  # pyright: ignore[reportPrivateUsage]
from pycpu.cockpit.session import (
    FINISHED_NOTE,
    NO_LINES_NOTE,
    Cockpit,
    CockpitBusy,
    Depth,
)
from pycpu.computer import StepSize

BITS = 8
OK = 200
BAD_REQUEST = 400
CONFLICT = 409
SOME_GATES = 5
COUNTDOWN = "let n = 2\nwhile n > 0 {\n    n = n - 1\n}\n"
SUB_PROGRAM = "li r1, 2\nli r2, 1\nsub r1, r1, r2\nhalt\n"
NOTHING_CHANGED: dict[str, object] = {
    "registers": [],
    "pc": False,
    "sp": False,
    "flags": [],
    "memory": [],
}
OUTSIDE = 1 << 12  # a pc far outside a small memory
STORE_PROGRAM = "li r1, 2\nstore r1, [r2]\nhalt\n"


def _pebble() -> Cockpit:
    """Return a small Cockpit with the countdown loaded."""
    cockpit = Cockpit(BITS)
    cockpit.load_pebble(COUNTDOWN)
    return cockpit


def _assembly(source: str) -> Cockpit:
    """Return a small Cockpit with the assembly `source` loaded."""
    cockpit = Cockpit(BITS)
    cockpit.load_assembly(source)
    return cockpit


def _body(response: TestResponse) -> dict[str, Any]:
    """Read a response body as a JSON object."""
    return cast("dict[str, Any]", response.json())


class TestStepAt:
    """Each depth moves exactly as the older move it is mapped to."""

    def test_instruction_depth_is_an_instruction_step(self) -> None:
        """Depth instruction and `step(INSTRUCTION)` give equal pictures."""
        one, two = _pebble(), _pebble()
        one.step_at(Depth.INSTRUCTION)
        two.step(StepSize.INSTRUCTION)
        assert machine_picture(one) == machine_picture(two)

    def test_part_depth_is_a_cycle_step(self) -> None:
        """Depth part and `step(CYCLE)` give equal pictures."""
        one, two = _pebble(), _pebble()
        one.step_at(Depth.PART)
        two.step(StepSize.CYCLE)
        assert machine_picture(one) == machine_picture(two)

    def test_gate_depth_is_a_gate_step(self) -> None:
        """Depth gate and `step(GATE)` give equal pictures."""
        one, two = _pebble(), _pebble()
        one.step_at(Depth.GATE)
        two.step(StepSize.GATE)
        assert machine_picture(one) == machine_picture(two)

    def test_line_depth_is_a_line_step_over(self) -> None:
        """Depth line and `step_line(into=False)` give equal pictures."""
        one, two = _pebble(), _pebble()
        one.step_at(Depth.LINE)
        two.step_line(into=False)
        assert machine_picture(one) == machine_picture(two)

    def test_line_depth_after_gate_steps_finishes_the_instruction(self) -> None:
        """Gate steps first, then a line step: it ends where a line step from the start ends."""
        steady = _pebble()
        steady.step_at(Depth.LINE)
        mixed = _pebble()
        for _ in range(SOME_GATES):
            mixed.step_at(Depth.GATE)
        mixed.step_at(Depth.LINE)
        assert mixed.computer.state().pc == steady.computer.state().pc
        assert machine_picture(mixed)["pebble"] == machine_picture(steady)["pebble"]
        assert mixed.computer.gate.at_boundary

    def test_line_depth_on_assembly_changes_nothing(self) -> None:
        """A line step on machine code says so and leaves the state alone."""
        cockpit = _assembly(SUB_PROGRAM)
        start = cockpit.computer.state()
        cockpit.step_at(Depth.LINE)
        assert cockpit.computer.state() == start
        assert cockpit.note == NO_LINES_NOTE
        assert cockpit.last_gate is None
        assert machine_picture(cockpit)["changed"] == NOTHING_CHANGED

    def test_every_depth_on_a_halted_machine_changes_nothing(self) -> None:
        """Once halted, each depth gives the finished note and no movement."""
        for depth in Depth:
            for cockpit in (_assembly("halt\n"), _pebble()):
                cockpit.run(10_000)
                halted = cockpit.computer.state()
                assert halted.halted
                cockpit.step_at(depth)
                assert cockpit.computer.state() == halted
                assert cockpit.note == FINISHED_NOTE
                assert cockpit.last_gate is None
                assert machine_picture(cockpit)["changed"] == NOTHING_CHANGED

    def test_a_step_while_playing_is_busy(self) -> None:
        """Step at any depth is refused while playing."""
        cockpit = _pebble()
        cockpit.start_playing()
        try:
            for depth in Depth:
                try:
                    cockpit.step_at(depth)
                except CockpitBusy:
                    continue
                raise AssertionError(depth)
        finally:
            cockpit.stop_playing()


class TestLabels:
    """The picture's `steps` labels name the part that does the instruction's work."""

    def test_labels_for_a_sub(self) -> None:
        """On a `sub`, the part button says ALU; the others are fixed."""
        cockpit = _assembly(SUB_PROGRAM)
        cockpit.step_at(Depth.INSTRUCTION)
        cockpit.step_at(Depth.INSTRUCTION)
        assert machine_picture(cockpit)["steps"] == {
            "line": "Step one line ▸",
            "instruction": "Step one instruction ▸",
            "part": "Step one ALU beat ▸",
            "gate": "Step one gate ▸",
        }

    def test_label_for_a_store(self) -> None:
        """On a `store`, the part button says memory address."""
        cockpit = _assembly(STORE_PROGRAM)
        cockpit.step_at(Depth.INSTRUCTION)
        steps = cast("dict[str, str]", machine_picture(cockpit)["steps"])
        assert steps["part"] == "Step one memory address beat ▸"

    def test_the_part_label_says_cpu_when_there_is_no_instruction(self) -> None:
        """A pc outside memory has no word, so the part button names the whole CPU."""
        cockpit = Cockpit(BITS)
        cockpit.computer.resume()
        cockpit.computer.fast.load_state(replace(cockpit.computer.fast.state(), pc=OUTSIDE))
        cockpit.computer.pause()
        steps = cast("dict[str, str]", machine_picture(cockpit)["steps"])
        assert steps["part"] == "Step one CPU beat \u25b8"

    def test_every_zoom_part_has_a_name_and_is_a_real_scope(self) -> None:
        """Each part in the zoom table is named, and every name is a scope in the circuit."""
        assert set(_PART_FOR_OPCODE.values()) <= set(PART_NAMES)
        circuit = Cockpit(BITS).computer.gate.simulator.circuit
        for path in PART_NAMES:
            assert circuit.has_scope(path), path


class TestLoadsMarkNothing:
    """After a load, nothing is marked changed."""

    def test_load_pebble_marks_nothing_changed(self) -> None:
        """A Pebble load after some steps leaves `changed` empty."""
        cockpit = Cockpit(BITS)
        cockpit.step_at(Depth.INSTRUCTION)
        cockpit.load_pebble(COUNTDOWN)
        assert machine_picture(cockpit)["changed"] == NOTHING_CHANGED

    def test_load_assembly_marks_nothing_changed(self) -> None:
        """An assembly load after some steps leaves `changed` empty."""
        cockpit = Cockpit(BITS)
        cockpit.step_at(Depth.INSTRUCTION)
        cockpit.load_assembly(SUB_PROGRAM)
        changed = cast("dict[str, Any]", machine_picture(cockpit)["changed"])
        assert changed["registers"] == []
        assert changed["memory"] == []


class TestRoute:
    """`POST /api/step` takes a depth, or a size, never both."""

    @staticmethod
    def _post(client: TestClient, body: dict[str, object]) -> TestResponse:
        """Post `body` to the step route."""
        return run_loop(client.post("/api/step", json=body))  # pyright: ignore[reportArgumentType]

    def test_each_depth_is_accepted(self) -> None:
        """All four depths answer with a picture carrying the step labels."""
        client = TestClient(create_cockpit(address_bits=BITS, start_example="countdown"))
        for depth in Depth:
            response = self._post(client, {"depth": depth.value})
            assert response.status == OK
            assert "steps" in _body(response)

    def test_both_keys_or_an_unknown_depth_is_a_400(self) -> None:
        """A body with both keys, an unknown depth or a depth with a count is refused."""
        client = TestClient(create_cockpit(address_bits=BITS))
        bodies: list[dict[str, object]] = [
            {"depth": "line", "size": "gate"},
            {"depth": "brick"},
            {"depth": 3},
            {"depth": "gate", "count": 2},
            {"depth": "gate", "count": True},
            {"depth": "gate", "count": 1.0},
        ]
        for body in bodies:
            assert self._post(client, body).status == BAD_REQUEST

    def test_a_depth_while_playing_is_a_409(self) -> None:
        """Step by depth is refused with 409 while the computer is playing."""
        app = create_cockpit(address_bits=BITS)
        client = TestClient(app)
        assert run_loop(client.post("/api/play", json={"speed": 1})).status == OK  # pyright: ignore[reportArgumentType]
        response = self._post(client, {"depth": "gate"})
        assert response.status == CONFLICT
        run_loop(client.post("/api/pause", json={}))  # pyright: ignore[reportArgumentType]

    def test_a_depth_with_a_count_says_so_plainly(self) -> None:
        """The 400 for a count names the rule in plain words."""
        client = TestClient(create_cockpit(address_bits=BITS))
        response = self._post(client, {"depth": "gate", "count": 2})
        assert "takes no count" in _body(response)["message"]

    def test_size_still_works(self) -> None:
        """The Plan 4 body keeps working."""
        client = TestClient(create_cockpit(address_bits=BITS))
        assert self._post(client, {"size": "instruction"}).status == OK

    def test_line_on_assembly_is_a_note_not_an_error(self) -> None:
        """A line depth on the assembly demo answers 200 with the plain note."""
        client = TestClient(create_cockpit(address_bits=BITS))
        response = self._post(client, {"depth": "line"})
        assert response.status == OK
        assert _body(response)["note"] == NO_LINES_NOTE
