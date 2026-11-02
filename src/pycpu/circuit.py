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
one more whole number (4 bytes). The parts themselves cost about 200 bytes each:
a measured 500,010-gate circuit with 197,229 parts used about 59 MB in all, under
40 MB of it for part bookkeeping. Each part keeps its running gate total, so
asking how big a part is takes no searching.
"""

from array import array
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass

type Wire = int
type Bus = tuple[Wire, ...]

LOW: Wire = 0
HIGH: Wire = 1
_FIRST_FREE_WIRE = 2


@dataclass(frozen=True)
class Clock:
    """The two beat wires of the machine: `write` first, then `clk`.

    Registers step when `clk` rises. Memory copies a value in while `write` is
    high. `Simulator.tick` pulses `write` and then `clk`, so memory always
    writes while every register still holds this beat's address and data.
    """

    clk: Wire
    write: Wire


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
        self._state_pairs: list[tuple[str, Wire, Wire]] = []
        # Scope tables: arrays indexed by scope id, with id 0 the root. A path
        # is only stored once, as a key of `_scope_ids`.
        self._scope_of = array("i")  # the scope id of each gate
        self._scope_names = [""]  # scope id -> its own name, such as "xor#1"
        self._scope_parent = array("i", [-1])
        self._scope_repeats = array("i", [1])  # times this name has been used under its parent
        self._scope_direct = array("i", [0])  # gates sitting directly in the scope
        self._scope_total = array("i", [0])  # gates in the scope and everything nested in it
        self._scope_first_child = array("i", [-1])
        self._scope_last_child = array("i", [-1])
        self._scope_next_sibling = array("i", [-1])
        self._scope_ids: dict[str, int] = {"": 0}
        self._current_scope = 0
        self._by_scope = array("i")  # gate ids grouped by scope, built when first needed
        self._by_scope_start = array("i")
        self._index_valid = False

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

    @property
    def undriven_count(self) -> int:
        """Return how many wires have no input, constant or gate driving them.

        These are `wire_placeholder` wires still waiting for their `nand_into`.
        """
        return len(self._driven) - sum(self._driven)

    @property
    def first_undriven(self) -> Wire:
        """Return the lowest-numbered undriven wire, or -1 if every wire is driven."""
        return self._driven.find(0)

    @property
    def state_pairs(self) -> tuple[tuple[str, Wire, Wire], ...]:
        """Return every registered storage cell as `(name, q, q_n)`, in the order made."""
        return tuple(self._state_pairs)

    def state_pair(self, name: str, q: Wire, qn: Wire) -> None:
        """Register a storage cell: two wires that hold a bit and its opposite.

        `Simulator.poke_pairs` can then write the cell directly, which is how a
        saved state is loaded without ticking the clock. The cell is filed under
        the path of the part being built, such as `r.bit0.master`.

        Args:
            name: A label for the cell, unique within the current part.
            q: The wire that holds the bit.
            qn: The wire that holds the opposite of the bit.

        """
        for wire in (q, qn):
            self._check(wire)
        path = self.scope_path(self._current_scope)
        self._state_pairs.append((f"{path}.{name}" if path else name, q, qn))

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
        scope_id = self._current_scope
        self._scope_direct[scope_id] += 1
        while scope_id >= 0:  # every part up to the root counts this gate too
            self._scope_total[scope_id] += 1
            scope_id = self._scope_parent[scope_id]
        self._index_valid = False

    def is_input(self, wire: Wire) -> bool:
        """Return True if `wire` is one made by `input` or `bus_input`."""
        return 0 <= wire < self._wire_count and bool(self._is_input[wire])

    @contextmanager
    def scope(self, name: str) -> Generator[None]:
        """Label every gate made inside the `with` block as a named part.

        Scopes nest, so the parts of a part get dotted paths like `alu.adder`.
        Repeated names under one parent get numbered: the first use of `xor`
        stays `xor`, the second becomes `xor#1`, the third `xor#2`, so every
        path names exactly one part.

        Args:
            name: The part's name. It must not be empty or contain a dot.

        Raises:
            ValueError: If the name is empty or contains a dot.

        """
        if not name or "." in name:
            msg = f"a scope name must be non-empty and have no dots: {name!r}"
            raise ValueError(msg)
        parent = self._current_scope
        parent_path = self.scope_path(parent)
        base = f"{parent_path}.{name}" if parent_path else name
        first = self._scope_ids.get(base)
        if first is None:
            unique, path = name, base
        else:
            uses = self._scope_repeats[first]
            self._scope_repeats[first] = uses + 1
            unique = f"{name}#{uses}"
            path = f"{parent_path}.{unique}" if parent_path else unique
        scope_id = len(self._scope_names)
        self._scope_names.append(unique)
        self._scope_parent.append(parent)
        self._scope_repeats.append(1)
        self._scope_direct.append(0)
        self._scope_total.append(0)
        self._scope_first_child.append(-1)
        self._scope_last_child.append(-1)
        self._scope_next_sibling.append(-1)
        self._scope_ids[path] = scope_id
        self._index_valid = False
        last = self._scope_last_child[parent]
        if last < 0:
            self._scope_first_child[parent] = scope_id
        else:
            self._scope_next_sibling[last] = scope_id
        self._scope_last_child[parent] = scope_id
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

    def scope_path(self, scope_id: int) -> str:
        """Return the dotted path of scope number `scope_id` (the root is `""`)."""
        names: list[str] = []
        while scope_id > 0:
            names.append(self._scope_names[scope_id])
            scope_id = self._scope_parent[scope_id]
        return ".".join(reversed(names))

    def children(self, path: str) -> list[str]:
        """Return the names of the parts directly inside `path`, in the order made.

        Raises:
            KeyError: If `path` is not a scope.

        """
        names: list[str] = []
        child = self._scope_first_child[self._scope_id(path)]
        while child >= 0:
            names.append(self._scope_names[child])
            child = self._scope_next_sibling[child]
        return names

    def _build_index(self) -> None:
        """Group the gate ids by scope (a counting sort), so a part finds its gates fast.

        Built once, the first time a part's gates are asked for after the
        circuit last changed. It costs one pass over the gates and 4 bytes a gate.
        """
        starts = array("i", [0]) * (len(self._scope_names) + 1)
        for scope_id, count in enumerate(self._scope_direct):
            starts[scope_id + 1] = starts[scope_id] + count
        cursor = array("i", starts)
        ordered = array("i", [0]) * len(self._scope_of)
        for gate, scope_id in enumerate(self._scope_of):
            ordered[cursor[scope_id]] = gate
            cursor[scope_id] += 1
        self._by_scope, self._by_scope_start = ordered, starts
        self._index_valid = True

    def gates_in(self, path: str) -> list[int]:
        """Return the gates that sit directly in `path`, not those in its sub-parts.

        Raises:
            KeyError: If `path` is not a scope.

        """
        scope_id = self._scope_id(path)
        if not self._index_valid:
            self._build_index()
        return list(
            self._by_scope[self._by_scope_start[scope_id] : self._by_scope_start[scope_id + 1]]
        )

    def gate_count_in(self, path: str) -> int:
        """Return how many gates are in `path`, counting every part nested inside it.

        Raises:
            KeyError: If `path` is not a scope.

        """
        return self._scope_total[self._scope_id(path)]

    def scope_of(self, gate: int) -> str:
        """Return the dotted path of the part that gate number `gate` belongs to."""
        return self.scope_path(self._scope_of[gate])
