"""The netlist: a plain list of wires and the NAND gates that join them.

Think of a model railway layout drawn on paper before any track is laid. The
drawing says which stations exist and which lines join them, but no train runs
on it. A `Circuit` is that drawing for electronics: it records wires and gates
and never works out a single value. The `Simulator` is the one who runs trains.

NAND is the only kind of gate there is. Each gate is stored as three whole
numbers (first input wire, second input wire, output wire) in compact arrays, so
a circuit of half a million gates fits comfortably in memory.

Gates can also be filed into named parts, like rooms inside a house inside a
street. A part is a *scope*, written as a dotted path such as `alu.adder.bit1`,
and the empty path `""` is the whole circuit. Each gate remembers its scope with
one more whole number, which costs just 4 bytes a gate.
"""

from array import array
from collections.abc import Generator
from contextlib import contextmanager

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
        self._scope_of = array("i")  # the scope id of each gate, 4 bytes apiece
        self._scope_paths: list[str] = [""]  # scope id -> dotted path; id 0 is the root
        self._scope_ids: dict[str, int] = {"": 0}
        self._scope_children: dict[str, list[str]] = {"": []}
        self._scope_gates = [0]  # scope id -> number of gates directly in it
        self._scope_uses: dict[tuple[int, str], int] = {}
        self._current_scope = 0

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
        self._scope_of.append(self._current_scope)
        self._scope_gates[self._current_scope] += 1

    def is_input(self, wire: Wire) -> bool:
        """Return True if `wire` is one made by `input` or `bus_input`."""
        return 0 <= wire < self._wire_count and bool(self._is_input[wire])

    @contextmanager
    def scope(self, name: str) -> Generator[None]:
        """Label every gate made inside the `with` block as a named part.

        Scopes nest, so the parts of a part get dotted paths like `alu.adder`.
        Using the same name again under the same parent numbers the repeat:
        the first is `xor`, the second `xor#1`, the third `xor#2`.

        Args:
            name: The part's name. It must not be empty or contain a dot.

        Raises:
            ValueError: If the name is empty or contains a dot.

        """
        if not name or "." in name:
            msg = f"a scope name must be non-empty and have no dots: {name!r}"
            raise ValueError(msg)
        parent = self._current_scope
        uses = self._scope_uses.get((parent, name), 0)
        self._scope_uses[parent, name] = uses + 1
        unique = name if uses == 0 else f"{name}#{uses}"
        parent_path = self._scope_paths[parent]
        path = f"{parent_path}.{unique}" if parent_path else unique
        scope_id = len(self._scope_paths)
        self._scope_paths.append(path)
        self._scope_gates.append(0)
        self._scope_ids[path] = scope_id
        self._scope_children[path] = []
        self._scope_children[parent_path].append(unique)
        self._current_scope = scope_id
        try:
            yield
        finally:
            self._current_scope = parent

    def has_scope(self, path: str) -> bool:
        """Return True if `path` names a part of the circuit (`""` is the whole)."""
        return path in self._scope_ids

    def _scope_id(self, path: str) -> int:
        """Return the id of a scope, or raise `KeyError` naming the missing path."""
        try:
            return self._scope_ids[path]
        except KeyError:
            msg = f"no such scope: {path!r}"
            raise KeyError(msg) from None

    def children(self, path: str) -> list[str]:
        """Return the names of the parts directly inside `path`, in the order made.

        Raises:
            KeyError: If `path` is not a scope.

        """
        self._scope_id(path)
        return list(self._scope_children[path])

    def gates_in(self, path: str) -> list[int]:
        """Return the gates that sit directly in `path`, not those in its sub-parts.

        Raises:
            KeyError: If `path` is not a scope.

        """
        scope_id = self._scope_id(path)
        return [gate for gate, owner in enumerate(self._scope_of) if owner == scope_id]

    def gate_count_in(self, path: str) -> int:
        """Return how many gates are in `path`, counting every part nested inside it.

        Raises:
            KeyError: If `path` is not a scope.

        """
        self._scope_id(path)
        prefix = f"{path}." if path else ""
        return sum(
            self._scope_gates[scope_id]
            for scope_id, other in enumerate(self._scope_paths)
            if other == path or other.startswith(prefix)
        )

    def scope_of(self, gate: int) -> str:
        """Return the dotted path of the part that gate number `gate` belongs to."""
        return self._scope_paths[self._scope_of[gate]]
