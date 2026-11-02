"""The simulator: Python pretending to be electricity, one falling domino at a time.

Picture a long line of dominoes. Push one and only the dominoes it topples move;
the rest stand still. The `Simulator` works the same way. It keeps the value of
every wire, and when a wire changes it asks only the gates connected to that
wire to think again. The ripple stops by itself when nothing changes any more.

This is the one place in PyCPU that works out a logic result in Python. Every
higher layer is built from NAND gates in a `Circuit` and merely asks this file
to run them.
"""

from array import array
from collections import deque
from collections.abc import Sequence

from pycpu.circuit import Bus, Circuit, Clock, Wire

DEFAULT_MAX_EVENTS = 10_000_000


class OscillationError(Exception):
    """Raised when a circuit keeps changing and never settles, like a swinging pendulum."""


class Simulator:
    """Bring a `Circuit` to life: hold its wire values and ripple changes through it.

    Build one after the circuit is complete. Adding gates to the circuit later
    is not seen by an existing simulator.
    """

    def __init__(self, circuit: Circuit, max_events: int = DEFAULT_MAX_EVENTS) -> None:
        """Take a circuit, build its fanout table, and settle it from power-on.

        Every gate is queued once in the order it was added, so a given circuit
        always starts in the same state.

        Args:
            circuit: The finished circuit to simulate.
            max_events: Give up with `OscillationError` when one `settle` needs
                more gate evaluations than this.

        Raises:
            ValueError: If some wire has no gate driving it. That would read as
                0 without a word, so it is refused. The message gives the count.
            OscillationError: If the circuit never settles at power-on.

        """
        undriven = circuit.undriven_count
        if undriven:
            noun = (
                "wire has no gate driving it"
                if undriven == 1
                else "wires have no gate driving them"
            )
            msg = f"{undriven} {noun}: finish each wire_placeholder with nand_into"
            raise ValueError(msg)
        self._circuit = circuit
        self._max_events = max_events
        self._first, self._second, self._out = circuit.gate_wires
        self._gate_count = len(self._out)
        self._values = bytearray(circuit.wire_count)
        self._values[circuit.high] = 1
        self._queue: deque[int] = deque()
        self._queued = bytearray(self._gate_count)
        self._offsets, self._fanout = self._build_fanout()
        self.events_total = 0
        self._queue.extend(range(self._gate_count))
        self._queued[:] = b"\x01" * self._gate_count
        self.settle()

    @property
    def circuit(self) -> Circuit:
        """Return the circuit being simulated."""
        return self._circuit

    def _build_fanout(self) -> tuple[array[int], array[int]]:
        """Return the fanout table: for each wire, the gates that read it.

        The table is two flat arrays (a compressed layout): the gates reading
        wire `w` are `fanout[offsets[w]:offsets[w + 1]]`. A list per wire would
        cost far more memory in a circuit of half a million gates.
        """
        wires = self._circuit.wire_count
        counts = [0] * (wires + 1)
        for gate in range(self._gate_count):
            a, b = self._first[gate], self._second[gate]
            counts[a] += 1
            if b != a:
                counts[b] += 1
        offsets = array("i", [0]) * (wires + 1)
        for wire in range(wires):
            offsets[wire + 1] = offsets[wire] + counts[wire]
        fanout = array("i", [0]) * offsets[wires]
        cursor = array("i", offsets)
        for gate in range(self._gate_count):
            a, b = self._first[gate], self._second[gate]
            fanout[cursor[a]] = gate
            cursor[a] += 1
            if b != a:
                fanout[cursor[b]] = gate
                cursor[b] += 1
        return offsets, fanout

    def _wake(self, wire: Wire) -> None:
        """Queue every gate that reads `wire`, unless it is already waiting."""
        queue, queued, fanout = self._queue, self._queued, self._fanout
        for i in range(self._offsets[wire], self._offsets[wire + 1]):
            gate = fanout[i]
            if not queued[gate]:
                queued[gate] = 1
                queue.append(gate)

    def set(self, wire: Wire, value: int) -> None:
        """Switch an input wire to 0 or 1; call `settle` afterwards to see the effect.

        Raises:
            ValueError: If `wire` is not an input, or `value` is not 0 or 1.

        """
        if not self._circuit.is_input(wire):
            msg = f"wire {wire} is not an input"
            raise ValueError(msg)
        if value not in (0, 1):
            msg = f"a wire holds 0 or 1, not {value}"
            raise ValueError(msg)
        if self._values[wire] != value:
            self._values[wire] = value
            self._wake(wire)

    def get(self, wire: Wire) -> int:
        """Return the current value, 0 or 1, of any wire."""
        return self._values[wire]

    def set_bus(self, bus: Bus, value: int) -> None:
        """Switch a row of input wires to spell `value`, least significant bit first.

        Raises:
            ValueError: If `value` is negative or too big for the bus.

        """
        if not 0 <= value < 1 << len(bus):
            msg = f"{value} does not fit in {len(bus)} bits"
            raise ValueError(msg)
        for index, wire in enumerate(bus):
            self.set(wire, (value >> index) & 1)

    def get_bus(self, bus: Bus) -> int:
        """Read a row of wires as one number, least significant bit first."""
        return sum(self._values[wire] << index for index, wire in enumerate(bus))

    def poke_pairs(self, pairs: Sequence[tuple[Wire, Wire]], value: int) -> None:
        """Write a bit straight into storage cells: `q` becomes `value`, `qn` its opposite.

        Nothing settles here, so many cells can be written and then settled once.
        The gates reading the changed wires are queued.

        Raises:
            ValueError: If `value` is not 0 or 1.

        """
        if value not in (0, 1):
            msg = f"a wire holds 0 or 1, not {value}"
            raise ValueError(msg)
        values = self._values
        for q, qn in pairs:
            for wire, new in ((q, value), (qn, 1 - value)):
                if values[wire] != new:
                    values[wire] = new
                    self._wake(wire)

    def tick(self, clock: Clock) -> None:
        """Play one beat: pulse `write` up and down, then `clk` up and down.

        The `write` pulse comes first and is over before `clk` rises, so memory
        copies in values while every register still holds this beat's. Each
        change is settled before the next.
        """
        for wire in (clock.write, clock.clk):
            self.set(wire, 1)
            self.settle()
            self.set(wire, 0)
            self.settle()

    def _part_still_changing(self) -> str:
        """Describe where in the circuit a gate is still changing, for the error message.

        Looks through the waiting gates for the first one whose answer would
        differ from its output right now. If none would, the front gate is named.
        """
        values, first, second, out = self._values, self._first, self._second, self._out
        culprit = self._queue[0]
        for gate in self._queue:
            if values[out[gate]] != 1 - (values[first[gate]] & values[second[gate]]):
                culprit = gate
                break
        path = self._circuit.scope_of(culprit)
        return f"still changing in part '{path}'" if path else "still changing at the top level"

    def settle(self) -> int:
        """Ripple every pending change through the circuit until all is still.

        Each gate taken from the queue is worked out from the wire values right
        now. If its output changes, the new value is written at once and the
        gates reading that wire join the queue. Writing at once, rather than
        all together, lets two gates facing each other settle instead of
        swinging forever.

        Returns:
            How many gate evaluations it took (0 if nothing had changed).

        Raises:
            OscillationError: If more than `max_events` evaluations are needed.
                The message names the part of the circuit still changing.

        """
        queue, queued, values = self._queue, self._queued, self._values
        first, second, out = self._first, self._second, self._out
        limit = self._max_events
        done = 0
        while queue:
            if done >= limit:
                part = self._part_still_changing()
                queue.clear()
                queued[:] = bytes(self._gate_count)
                self.events_total += done
                msg = f"circuit did not settle within {limit} gate evaluations ({part})"
                raise OscillationError(msg)
            gate = queue.popleft()
            queued[gate] = 0
            done += 1
            wire = out[gate]
            new = 1 - (values[first[gate]] & values[second[gate]])
            if values[wire] != new:
                values[wire] = new
                self._wake(wire)
        self.events_total += done
        return done
