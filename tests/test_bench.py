"""Tests for the Bench: the local page for looking inside the ALU."""

import json
from collections.abc import Coroutine
from typing import Any, cast

import pytest
from pynet.loop import run
from pyweb.aserver import AsyncServer
from pyweb.testing import TestClient, TestResponse

from pycpu import __main__ as entry
from pycpu.__main__ import HOST, banner, open_bench
from pycpu.bench.app import create_bench

OK = 200
BAD_REQUEST = 400
NOT_FOUND = 404
MAX_POSITIVE = 0x7FFF
SIGN_BIT_SET = 0x8000
TOO_BIG = 70000
FOUR = 4
SCOPE = "alu.adder.bit0"


def _run[T](job: Coroutine[Any, Any, T]) -> T:
    """Run one async test body to the end and hand back its result."""
    return run(job)


def _json(response: TestResponse) -> dict[str, Any]:
    """Read a response body as a JSON object."""
    return cast("dict[str, Any]", response.json())


def _output_wires(client: TestClient, path: str) -> list[int]:
    """Collect every gate output under a scope, walking all the scopes inside it."""

    async def walk(where: str) -> list[int]:
        """Read one scope's gates, then each child scope's gates."""
        view = _json(await client.get("/api/view", query={"path": where}))
        values = [gate["value_out"] for gate in view["gates"]]
        for child in view["children"]:
            values += await walk(f"{where}.{child['name']}")
        return values

    return _run(walk(path))


def test_adding_the_biggest_positive_number_and_one_overflows() -> None:
    """0x7FFF + 1 gives 0x8000 and lights the overflow flag."""

    async def body() -> dict[str, Any]:
        client = TestClient(create_bench())
        return _json(await client.post("/api/inputs", json={"a": MAX_POSITIVE, "b": 1, "op": 0}))

    answer = _run(body())
    assert answer["result"] == SIGN_BIT_SET
    assert answer["overflow"] == 1


def test_three_plus_one_is_four() -> None:
    """The guided tour's sum comes out right."""

    async def body() -> dict[str, Any]:
        client = TestClient(create_bench())
        return _json(await client.post("/api/inputs", json={"a": 3, "b": 1, "op": 0}))

    assert _run(body())["result"] == FOUR


def test_the_view_shows_real_wires_that_change_with_the_inputs() -> None:
    """Gate values inside a bit differ between 1 + 1 and 0 + 0."""
    client = TestClient(create_bench())

    async def set_inputs(a: int, b: int) -> None:
        response = await client.post("/api/inputs", json={"a": a, "b": b, "op": 0})
        assert response.status == OK

    async def top() -> int:
        return (await client.get("/api/view", query={"path": SCOPE})).status

    _run(set_inputs(0, 0))
    assert _run(top()) == OK
    quiet = _output_wires(client, SCOPE)
    _run(set_inputs(1, 1))
    busy = _output_wires(client, SCOPE)
    assert quiet
    assert len(quiet) == len(busy)
    assert quiet != busy


def test_an_unknown_part_is_a_friendly_404() -> None:
    """Asking for a scope that does not exist says so, rather than crashing."""

    async def body() -> TestResponse:
        client = TestClient(create_bench())
        return await client.get("/api/view", query={"path": "alu.nope"})

    response = _run(body())
    assert response.status == NOT_FOUND
    assert "No part called alu.nope" in response.text


def test_a_number_too_big_for_sixteen_bits_is_a_400() -> None:
    """A = 70000 does not fit in a word, so the Bench refuses it."""

    async def body() -> int:
        client = TestClient(create_bench())
        return (await client.post("/api/inputs", json={"a": TOO_BIG, "b": 0, "op": 0})).status

    assert _run(body()) == BAD_REQUEST


def test_other_bad_inputs_are_400s() -> None:
    """Missing fields, a bad op, text, a boolean and broken JSON are all refused."""
    bad: list[object] = [
        {"a": 1, "b": 1},
        {"a": 1, "b": 1, "op": 8},
        {"a": -1, "b": 1, "op": 0},
        {"a": "1", "b": 1, "op": 0},
        {"a": True, "b": 1, "op": 0},
        [1, 2, 3],
    ]

    async def body() -> list[int]:
        client = TestClient(create_bench())
        statuses = [(await client.post("/api/inputs", json=item)).status for item in bad]  # pyright: ignore[reportArgumentType]
        statuses.append((await client.post("/api/inputs", body=b"{nope")).status)
        return statuses

    assert _run(body()) == [BAD_REQUEST] * (len(bad) + 1)


def test_the_front_page_is_the_bench_html() -> None:
    """GET / serves the page, which mentions the three inputs."""

    async def body() -> TestResponse:
        return await TestClient(create_bench()).get("/")

    response = _run(body())
    assert response.status == OK
    assert "text/html" in (response.headers.get("Content-Type") or "")
    assert "Bench" in response.text


def test_the_whole_circuit_view_lists_alu() -> None:
    """With no path the view is the top of the circuit, holding the alu."""

    async def body() -> dict[str, Any]:
        return _json(await TestClient(create_bench()).get("/api/view"))

    view = _run(body())
    assert [child["name"] for child in view["children"]] == ["alu"]
    json.dumps(view)


def test_the_bench_opens_on_this_computer_only() -> None:
    """open_bench listens on 127.0.0.1, and the banner names the real address."""

    async def body() -> tuple[str, int]:
        server = await open_bench(0)
        try:
            return banner(server), server.port
        finally:
            await server.close()

    text, port = _run(body())
    assert HOST == "127.0.0.1"
    assert port > 0
    assert f"http://127.0.0.1:{port}" in text
    assert "Ctrl+C" in text


def test_main_closes_quietly_on_ctrl_c(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Pressing Ctrl+C while serving prints a goodbye instead of a traceback."""

    def interrupted(job: Coroutine[Any, Any, None]) -> None:
        job.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(entry, "run", interrupted)
    entry.main()
    assert "closed" in capsys.readouterr().out


def test_serve_prints_the_banner_and_shuts_the_server_down(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Serve opens the Bench, prints where it is, and closes it when serving ends."""

    async def finish(_self: AsyncServer) -> None:
        """Stand in for serving forever by returning at once."""

    monkeypatch.setattr(AsyncServer, "serve_forever", finish)
    monkeypatch.setattr(entry, "PORT", 0)
    _run(entry.serve())
    assert "The Bench is open at http://127.0.0.1:" in capsys.readouterr().out
