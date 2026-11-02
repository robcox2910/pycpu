"""The circuit view: a street map you can zoom, drawn from the real circuit.

A good map app lets you start with the whole country, tap a town, then tap a
street, then a single house. Nothing on the map is a drawing made up for show;
it is the real place, just shown at a different size. `circuit_view` does that
for a circuit. Ask for `""` and you see the biggest parts. Ask for `"alu"` and
you see the parts inside it. Keep zooming until you reach individual NAND
gates, each shown with the values on its wires right now.

The view reads the very same wire values the `Simulator` is using. It keeps no
copy and works nothing out, so it cannot disagree with the circuit it shows.
"""

from pycpu.simulator import Simulator


def circuit_view(sim: Simulator, path: str) -> dict[str, object]:
    """Describe one part of a running circuit, at the zoom level of `path`.

    Args:
        sim: The simulator whose live circuit to look at.
        path: The dotted path of the part, such as `"alu.adder"`. Use `""` for
            the whole circuit.

    Returns:
        A dictionary with three keys. `path` is the path asked for. `children`
        lists the parts inside it as `{"name", "gate_count"}`, where the count
        includes everything nested deeper. `gates` lists the NAND gates sitting
        directly in it as `{"id", "a", "b", "out", "value_a", "value_b",
        "value_out"}`: the three wires of the gate and the 0 or 1 on each.

    Raises:
        KeyError: If no part of the circuit has that path.

    """
    circuit = sim.circuit
    names = circuit.children(path)  # raises KeyError for an unknown path
    prefix = f"{path}." if path else ""
    children = [
        {"name": name, "gate_count": circuit.gate_count_in(f"{prefix}{name}")} for name in names
    ]
    first, second, out = circuit.gate_wires
    gates = [
        {
            "id": gate,
            "a": first[gate],
            "b": second[gate],
            "out": out[gate],
            "value_a": sim.get(first[gate]),
            "value_b": sim.get(second[gate]),
            "value_out": sim.get(out[gate]),
        }
        for gate in circuit.gates_in(path)
    ]
    return {"path": path, "children": children, "gates": gates}
