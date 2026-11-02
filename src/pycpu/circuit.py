"""The netlist: a plain list of wires and the NAND gates that join them.

Think of a model railway layout drawn on paper before any track is laid. The
drawing says which stations exist and which lines join them, but no train runs
on it. A `Circuit` is that drawing for electronics: it records wires and gates
and never works out a single value. The `Simulator` is the one who runs trains.

NAND is the only kind of gate there is. Each gate is stored as three whole
numbers (first input wire, second input wire, output wire) in compact arrays, so
a circuit of half a million gates fits comfortably in memory.
"""

from array import array

type Wire = int
type Bus = tuple[Wire, ...]

LOW: Wire = 0
HIGH: Wire = 1
_FIRST_FREE_WIRE = 2


class Circuit:
    """A drawing of wires and NAND gates, with nothing yet switched on.

    Every circuit starts with two built-in wires: `low`, which is always 0, and
    `high`, which is always 1. Build the rest with `input`, `bus_input` and
    `nand`, then hand the circuit to a `Simulator` to bring it to life.
    """

    def __init__(self) -> None:
        """Make an empty circuit holding only the `low` and `high` wires."""
        self.low: Wire = LOW
        self.high: Wire = HIGH
        self._wire_count = _FIRST_FREE_WIRE
        self._first = array("i")
        self._second = array("i")
        self._out = array("i")
        self._driven = bytearray(b"\x01\x01")  # 1 when something already sets this wire
        self._is_input = bytearray(_FIRST_FREE_WIRE)  # 1 for wires made by `input`
        self._input_names: dict[str, Wire] = {}

    @property
    def gate_count(self) -> int:
        """Return how many NAND gates the circuit holds."""
        return len(self._out)

    @property
    def wire_count(self) -> int:
        """Return how many wires the circuit holds, counting `low` and `high`."""
        return self._wire_count

    @property
    def gate_wires(self) -> tuple[array[int], array[int], array[int]]:
        """Return the gate table: first inputs, second inputs and outputs.

        Gate `i` reads `first[i]` and `second[i]` and drives `out[i]`. The arrays
        are the circuit's own, shared for speed, so treat them as read-only.
        """
        return self._first, self._second, self._out

    def _new_wire(self, *, driven: bool, is_input: bool = False) -> Wire:
        """Add one wire; `driven` says whether an input or constant already owns it."""
        wire = self._wire_count
        self._wire_count += 1
        self._driven.append(1 if driven else 0)
        self._is_input.append(1 if is_input else 0)
        return wire

    def _check(self, wire: Wire) -> None:
        """Raise unless `wire` names a wire in this circuit."""
        if not 0 <= wire < self._wire_count:
            msg = f"no such wire: {wire}"
            raise ValueError(msg)

    def input(self, name: str) -> Wire:
        """Add a wire that a person (or a test) can switch on and off.

        Args:
            name: A label for the wire. Each label may be used once.

        Returns:
            The new wire.

        """
        if name in self._input_names:
            msg = f"input name already used: {name}"
            raise ValueError(msg)
        wire = self._new_wire(driven=True, is_input=True)
        self._input_names[name] = wire
        return wire

    def bus_input(self, name: str, width: int) -> Bus:
        """Add a row of input wires that together hold one number.

        Args:
            name: A label for the row; wire `i` is labelled `name[i]`.
            width: How many wires (bits) the row has.

        Returns:
            The wires, least significant bit first.

        """
        return tuple(self.input(f"{name}[{i}]") for i in range(width))

    def nand(self, a: Wire, b: Wire) -> Wire:
        """Add a NAND gate reading wires `a` and `b`, and return its output wire.

        The output is 0 only when both inputs are 1; otherwise it is 1.
        """
        out = self.wire_placeholder()
        self.nand_into(a, b, out)
        return out

    def wire_placeholder(self) -> Wire:
        """Add a wire with no gate driving it yet, so a loop can be closed later.

        A gate cannot read a wire that does not exist, so a circuit that feeds
        its own output back to its input first makes the wire, then connects the
        gate that drives it with `nand_into`.
        """
        return self._new_wire(driven=False)

    def nand_into(self, a: Wire, b: Wire, out: Wire) -> None:
        """Add a NAND gate reading `a` and `b` that drives the existing wire `out`.

        Raises:
            ValueError: If a wire does not exist, or `out` is already driven by
                an input, a constant or another gate.

        """
        for wire in (a, b, out):
            self._check(wire)
        if self._driven[out]:
            msg = f"wire {out} is already driven"
            raise ValueError(msg)
        self._driven[out] = 1
        self._first.append(a)
        self._second.append(b)
        self._out.append(out)

    def is_input(self, wire: Wire) -> bool:
        """Return True if `wire` is one made by `input` or `bus_input`."""
        return 0 <= wire < self._wire_count and bool(self._is_input[wire])
