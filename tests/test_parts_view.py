"""Tests for part views: a CPU part's inputs and outputs, read from its real wires."""

from dataclasses import replace
from functools import cache
from typing import Any, cast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pynet.loop import run as run_loop
from pyweb.testing import TestClient, TestResponse

from pycpu.circuit import Bus
from pycpu.cockpit.app import create_cockpit
from pycpu.cockpit.picture import PART_NAMES, part_picture
from pycpu.cockpit.session import BUSY_MESSAGE, Cockpit, CockpitBusy, Depth
from pycpu.cpu import GateMachine, Phase
from pycpu.isa import Opcode, encode
from pycpu.simulator import Simulator
from pycpu.state import WORD_MASK, Flags, program_state

SMALL = 4  # a 16-word machine is plenty for one instruction and a halt
BITS = 8
OK = 200
NOT_FOUND = 404
CONFLICT = 409
SLOW_SPEED = 1
REGISTERS = 8
FN_COUNT = 8
SOME_BEATS = 12
# The CPU's size measured before any tap was recorded (6 address bits). Taps only name
# wires the CPU already has, so these numbers must never move because of them.
GATES_AT_6_BITS = 15525
WIRES_AT_6_BITS = 15529
PINNED_BITS = 6
ALU_INPUTS = ("a", "b")
ALU_OUTPUTS = ("result", "flags")
COUNTDOWN = "let n = 2\nwhile n > 0 {\n    n = n - 1\n}\n"


@cache
def _machine() -> GateMachine:
    """Return one small gate machine, shared: each example loads its own state."""
    return GateMachine(SMALL)


def _read_bits(sim: Simulator, bus: Bus) -> int:
    """Read a bus the slow, plain way: each wire through `simulator.get`, then add them up."""
    return sum(sim.get(wire) << bit for bit, wire in enumerate(bus))


def _body(response: TestResponse) -> dict[str, Any]:
    """Read a response body as a JSON object."""
    return cast("dict[str, Any]", response.json())


def _countdown() -> Cockpit:
    """Return a Cockpit with a little countdown loaded and paused at its start."""
    cockpit = Cockpit(BITS)
    cockpit.load_pebble(COUNTDOWN)
    return cockpit


class TestTaps:
    """The taps name real wires the CPU already has, and add nothing."""

    def test_every_part_except_the_whole_cpu_has_a_tap(self) -> None:
        """The taps cover exactly the parts in PART_NAMES, leaving out `cpu`."""
        assert set(_machine().taps) == set(PART_NAMES) - {"cpu"}

    def test_every_tapped_wire_is_a_real_driven_wire(self) -> None:
        """Each tapped wire is a gate's output or the always-0 or always-1 wire."""
        machine = _machine()
        circuit = machine.circuit
        driven = {*circuit.gate_wires[2], circuit.low, circuit.high}
        for part, buses in machine.taps.items():
            for name, bus in buses.items():
                assert bus, f"{part}.{name} has no wires"
                assert set(bus) <= driven, f"{part}.{name} names a wire nothing drives"

    def test_the_alu_has_a_b_result_and_flags(self) -> None:
        """The ALU's taps are the contract's four, with result and flags as its outputs."""
        machine = _machine()
        assert tuple(machine.taps["cpu.alu"]) == (*ALU_INPUTS, *ALU_OUTPUTS)
        assert machine.tap_outputs["cpu.alu"] == ALU_OUTPUTS

    def test_every_part_has_inputs_and_outputs(self) -> None:
        """Each part's outputs are some of its taps, and at least one tap is an input."""
        machine = _machine()
        assert set(machine.tap_outputs) == set(machine.taps)
        for part, outputs in machine.tap_outputs.items():
            names = set(machine.taps[part])
            assert outputs
            assert set(outputs) < names, part

    def test_taps_add_no_gate_and_no_wire(self) -> None:
        """The CPU has exactly the gates and wires it had before taps were recorded."""
        circuit = GateMachine(PINNED_BITS).circuit
        assert circuit.gate_count == GATES_AT_6_BITS
        assert circuit.wire_count == WIRES_AT_6_BITS


class TestAluTapsAreTheRealAnswer:
    """At an ALU execute, the taps carry the operands and the answer that lands in rd."""

    @given(
        fn=st.integers(0, FN_COUNT - 1),
        rd=st.integers(0, REGISTERS - 1),
        ra=st.integers(0, REGISTERS - 1),
        rb=st.integers(0, REGISTERS - 1),
        values=st.lists(st.integers(0, WORD_MASK), min_size=REGISTERS, max_size=REGISTERS),
    )
    def test_result_is_what_rd_holds_after_the_instruction(
        self, fn: int, rd: int, ra: int, rb: int, values: list[int]
    ) -> None:
        """After the fetch beat `a`, `b`, `result` and `flags` match the finished instruction."""
        machine = _machine()
        start = program_state([encode(Opcode.ALU, rd=rd, ra=ra, rb=rb, fn=fn)], machine.words)
        machine.load_state(replace(start, registers=tuple(values)))
        machine.step_cycle()
        assert machine.phase == Phase.EXECUTE
        sim, taps = machine.simulator, machine.taps["cpu.alu"]
        seen = {name: _read_bits(sim, bus) for name, bus in taps.items()}
        machine.step_cycle()
        after = machine.state()
        assert seen["a"] == values[ra]
        assert seen["b"] == values[rb]
        assert seen["result"] == after.registers[rd]
        flags = Flags(*((seen["flags"] >> bit) & 1 for bit in range(len(Flags._fields))))
        assert flags == after.flags


class TestPartPicture:
    """`part_picture` names a part and reads each of its buses off the paused gates."""

    def test_the_alu_picture_has_its_name_inputs_and_outputs(self) -> None:
        """The picture's keys are the contract's, with inputs and outputs in tap order."""
        picture = part_picture(_countdown(), "cpu.alu")
        assert picture["path"] == "cpu.alu"
        assert picture["name"] == PART_NAMES["cpu.alu"]
        inputs = cast("list[dict[str, object]]", picture["inputs"])
        outputs = cast("list[dict[str, object]]", picture["outputs"])
        assert tuple(bus["name"] for bus in inputs) == ALU_INPUTS
        assert tuple(bus["name"] for bus in outputs) == ALU_OUTPUTS

    def test_every_value_is_its_wires_read_one_by_one(self) -> None:
        """Beat after beat, every part's every value equals its bits read through `get`."""
        cockpit = _countdown()
        gate = cockpit.computer.gate
        for _ in range(SOME_BEATS):
            cockpit.step_at(Depth.PART)
            for part, buses in gate.taps.items():
                picture = part_picture(cockpit, part)
                inputs = cast("list[dict[str, object]]", picture["inputs"])
                outputs = cast("list[dict[str, object]]", picture["outputs"])
                shown = [*inputs, *outputs]
                assert {bus["name"]: bus["value"] for bus in shown} == {
                    name: _read_bits(gate.simulator, bus) for name, bus in buses.items()
                }

    def test_an_unknown_part_is_a_key_error(self) -> None:
        """A path with no taps, the whole `cpu` included, raises KeyError."""
        cockpit = _countdown()
        for path in ("cpu", "nonsense", ""):
            with pytest.raises(KeyError):
                part_picture(cockpit, path)

    def test_while_playing_there_are_no_live_wires(self) -> None:
        """A playing session refuses with CockpitBusy and the busy message."""
        cockpit = _countdown()
        cockpit.start_playing()
        with pytest.raises(CockpitBusy, match=BUSY_MESSAGE):
            part_picture(cockpit, "cpu.alu")


class TestPartRoute:
    """`GET /api/part?path=` answers the part picture, 404 or 409."""

    def test_the_route_answers_the_part_picture(self) -> None:
        """The route's body is the same as `part_picture` for the same moment."""

        async def main() -> TestResponse:
            """Ask for the ALU's view at the start of the countdown."""
            client = TestClient(create_cockpit(address_bits=BITS, start_example="countdown"))
            return await client.get("/api/part?path=cpu.alu")

        response = run_loop(main())
        assert response.status == OK
        body = _body(response)
        assert body["name"] == PART_NAMES["cpu.alu"]
        assert [bus["name"] for bus in body["outputs"]] == list(ALU_OUTPUTS)

    def test_an_unknown_path_is_404(self) -> None:
        """An unknown path, the whole cpu, and no path at all are each a 404."""

        async def main() -> list[TestResponse]:
            """Ask for parts that have no taps."""
            client = TestClient(create_cockpit(address_bits=SMALL))
            paths = ("/api/part?path=nonsense", "/api/part?path=cpu", "/api/part")
            return [await client.get(path) for path in paths]

        for response in run_loop(main()):
            assert response.status == NOT_FOUND

    def test_while_playing_the_route_is_409(self) -> None:
        """While playing the route answers 409 with the busy message."""

        async def main() -> TestResponse:
            """Play slowly, ask for the ALU, then pause."""
            client = TestClient(create_cockpit(address_bits=BITS, start_example="countdown"))
            await client.post("/api/play", json={"speed": SLOW_SPEED})
            answer = await client.get("/api/part?path=cpu.alu")
            await client.post("/api/pause")
            return answer

        response = run_loop(main())
        assert response.status == CONFLICT
        assert _body(response) == {"error": "Conflict", "message": BUSY_MESSAGE}
