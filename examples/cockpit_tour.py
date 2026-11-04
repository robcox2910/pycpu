"""Follow one Pebble line all the way down to a single NAND gate, and back up again.

Like following one letter through the post: it goes into the postbox, through the
sorting office, onto the right van, down the right street and through the right door,
and finally lands on the doormat. Here the letter is the Pebble line `n = n - 1` of the
countdown example. We step to that line, then to its `sub` instruction, then gate by
gate until a gate inside the adder works, read that gate's wires, and step on until
the variable `n` has changed from 2 to 1.

Run this with: uv run python examples/cockpit_tour.py
"""

from typing import Any, cast

from pynet.loop import run
from pyweb.testing import TestClient

from pycpu.cockpit.app import create_cockpit

ADDRESS_BITS = 8  # a 256-word Cockpit: big enough for the countdown, and quick to build
THE_LINE = "n = n - 1"  # the Pebble line we follow down to a gate
N_BEFORE = 2  # follow the line on the loop round where n goes from 2 to 1


def current_line(machine: dict[str, Any]) -> str:
    """Return the text of the Pebble line the machine is about to run, without its indent."""
    pebble = machine["pebble"]
    return pebble["source"][pebble["line"] - 1].strip()


def variable_n(machine: dict[str, Any]) -> dict[str, Any]:
    """Return the variables pane's entry for `n`, the countdown's only variable."""
    return next(name for name in machine["variables"]["names"] if name["name"] == "n")


async def post(client: TestClient, path: str, body: dict[str, Any]) -> dict[str, Any]:
    """Press a button: POST `body` to `path` and return the machine picture it answers."""
    return cast("dict[str, Any]", (await client.post(path, json=body)).json())


async def step(client: TestClient, size: str) -> dict[str, Any]:
    """Step the machine by one line, instruction or gate, and return the new picture."""
    return await post(client, "/api/step", {"size": size})


async def tour() -> None:
    """Walk the countdown from its line down to one gate, then on to the next line."""
    client = TestClient(create_cockpit(address_bits=ADDRESS_BITS))
    examples = cast("list[dict[str, str]]", (await client.get("/api/examples")).json())
    countdown = next(example["source"] for example in examples if example["name"] == "countdown")
    machine = await post(client, "/api/pebble", {"source": countdown})

    lines = 0
    while not (current_line(machine) == THE_LINE and variable_n(machine)["value"] == N_BEFORE):
        machine = await step(client, "line")
        lines += 1
    print(f"{lines} line steps: about to run line {machine['pebble']['line']}, {THE_LINE}")
    print("n is", variable_n(machine)["value"])

    while not machine["instruction"]["text"].startswith("sub"):
        print("   instruction:", machine["instruction"]["text"])
        machine = await step(client, "instruction")
    print("next instruction:", machine["instruction"]["text"])
    print("its part:", machine["parts"]["instruction"])

    gates = 0
    while not (machine["last_gate"] or {"path": ""})["path"].startswith("cpu.alu.adder"):
        machine = await step(client, "gate")
        gates += 1
    gate = machine["last_gate"]
    print(f"{gates} gate steps: gate {gate['id']} in {gate['path']}")

    seen = cast(
        "dict[str, Any]", (await client.get("/api/view", query={"path": gate["path"]})).json()
    )
    wires = next(each for each in seen["gates"] if each["id"] == gate["id"])
    print("its wires: in", wires["value_a"], "and", wires["value_b"], "out", wires["value_out"])

    machine = await step(client, "line")
    print(machine["note"])
    n = variable_n(machine)
    print(f"n is now {n['value']}, marked changed: {n['address'] in machine['changed']['memory']}")


def main() -> None:
    """Run the tour and print each stop on the way."""
    run(tour())


if __name__ == "__main__":
    main()
