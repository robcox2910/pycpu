"""Tests for the Cockpit session: every method of `Cockpit`, checked without the web app."""

import pytest

from pycpu.cockpit.session import (
    MAX_GATE_STEPS,
    MAX_PEBBLE_CHARACTERS,
    Cockpit,
    CockpitBusy,
    CockpitRefusal,
)
from pycpu.computer import StepSize

SMALL = 6
PEBBLE_BITS = 8
BAD_LINE = "    li r1, 1\n    frobnicate r2\n"
BAD_LINE_NUMBER = "line 2"
SHORT_RUN = 5
COUNTDOWN = "let n = 2\nprint(n)\n"
GATE_BATCH = 7
BUSY = "the computer is running: press pause first"
STACK_BITS = 7
STACK_PRINTS = 3


class TestLoading:
    """Loading assembly or Pebble changes the machine only when the text is accepted."""

    def test_refused_assembly_names_the_line_and_changes_nothing(self) -> None:
        """A bad line raises CockpitRefusal naming it and leaves the machine as it was."""
        cockpit = Cockpit(SMALL)
        assembly, state = cockpit.assembly, cockpit.computer.state()
        with pytest.raises(CockpitRefusal, match=BAD_LINE_NUMBER):
            cockpit.load_assembly(BAD_LINE)
        assert cockpit.computer.state() == state
        assert cockpit.assembly == assembly

    def test_good_assembly_is_loaded_and_paused(self) -> None:
        """Loaded assembly replaces the listing text and clears any Pebble program."""
        cockpit = Cockpit(SMALL)
        cockpit.load_assembly("halt")
        assert cockpit.assembly == "halt"
        assert cockpit.translated is None
        assert cockpit.computer.paused

    def test_pebble_load_keeps_the_translation(self) -> None:
        """A Pebble program is translated, loaded, and its assembly is kept."""
        cockpit = Cockpit(PEBBLE_BITS)
        cockpit.load_pebble(COUNTDOWN)
        assert cockpit.translated is not None
        assert cockpit.assembly == cockpit.translated.assembly


class TestMoves:
    """Every move sets `before` first and clears the note and the last gate."""

    def test_a_gate_step_records_before_and_the_gate(self) -> None:
        """`before` is the state ahead of the step; the gate step is remembered."""
        cockpit = Cockpit(SMALL)
        start = cockpit.computer.state()
        cockpit.note = "old"
        cockpit.step(StepSize.GATE, GATE_BATCH)
        assert cockpit.before == start
        assert cockpit.note is None
        assert cockpit.last_gate is not None

    def test_an_instruction_step_clears_the_last_gate(self) -> None:
        """Only a gate step leaves a last gate behind."""
        cockpit = Cockpit(SMALL)
        cockpit.step(StepSize.GATE)
        cockpit.step(StepSize.INSTRUCTION)
        assert cockpit.last_gate is None

    def test_rewind_sets_before(self) -> None:
        """Rewind remembers the state it left."""
        cockpit = Cockpit(SMALL)
        cockpit.step(StepSize.GATE, GATE_BATCH)
        moved = cockpit.computer.state()
        cockpit.rewind()
        assert cockpit.before == moved

    def test_run_resumes_and_pauses_again(self) -> None:
        """Run moves the machine on the fast engine and leaves it paused."""
        cockpit = Cockpit(SMALL)
        start = cockpit.computer.state()
        assert cockpit.run(SHORT_RUN) == SHORT_RUN
        assert cockpit.computer.paused
        assert cockpit.before == start
        assert cockpit.computer.state() != start

    def test_counts_are_checked(self) -> None:
        """A bad count, or a count with a cycle step, is refused."""
        cockpit = Cockpit(SMALL)
        with pytest.raises(CockpitRefusal, match="count must be"):
            cockpit.step(StepSize.GATE, MAX_GATE_STEPS + 1)
        with pytest.raises(CockpitRefusal, match="only for gate steps"):
            cockpit.step(StepSize.CYCLE, 2)
        with pytest.raises(CockpitRefusal, match="instructions must be"):
            cockpit.run(0)

    def test_playing_refuses_moves_but_not_loads(self) -> None:
        """While playing, moves raise CockpitBusy (a CockpitRefusal) and loads still work."""
        cockpit = Cockpit(SMALL)
        cockpit.playing = True
        with pytest.raises(CockpitBusy, match="press pause first"):
            cockpit.rewind()
        cockpit.load_assembly("halt")


class TestBusyAndLoads:
    """While playing only loads are allowed; every move, loads included, resets the notes."""

    def test_every_move_is_busy_while_playing_and_changes_nothing(self) -> None:
        """Each step size and run raise CockpitBusy with the exact message."""
        cockpit = Cockpit(SMALL)
        cockpit.playing = True
        state = cockpit.computer.state()
        for size in StepSize:
            with pytest.raises(CockpitBusy) as caught:
                cockpit.step(size)
            assert str(caught.value) == BUSY
        with pytest.raises(CockpitBusy, match=BUSY):
            cockpit.run(1)
        assert cockpit.computer.state() == state
        assert cockpit.before == state

    def test_loads_are_allowed_while_playing(self) -> None:
        """Both loads work while the session says it is playing."""
        cockpit = Cockpit(PEBBLE_BITS)
        cockpit.playing = True
        cockpit.load_assembly("halt")
        cockpit.load_pebble(COUNTDOWN)
        assert cockpit.translated is not None

    def test_loads_set_before_and_clear_notes(self) -> None:
        """A load records the state it replaced and clears the note and last gate."""
        cockpit = Cockpit(PEBBLE_BITS)
        for load in (cockpit.load_assembly, cockpit.load_pebble):
            source = "halt" if load == cockpit.load_assembly else COUNTDOWN
            cockpit.step(StepSize.GATE)
            cockpit.note = "old"
            old = cockpit.computer.state()
            load(source)
            assert cockpit.before == old
            assert cockpit.note is None
            assert cockpit.last_gate is None

    def test_pebble_refusals_change_nothing(self) -> None:
        """Too long, too big and no room for the stack all raise CockpitRefusal."""
        cases = [
            (Cockpit(PEBBLE_BITS), "x" * (MAX_PEBBLE_CHARACTERS + 1), "at most"),
            (Cockpit(SMALL), COUNTDOWN, "needs"),
            (Cockpit(STACK_BITS), "print(1)\n" * STACK_PRINTS, "room for its stack"),
        ]
        for cockpit, source, message in cases:
            state, assembly = cockpit.computer.state(), cockpit.assembly
            with pytest.raises(CockpitRefusal, match=message):
                cockpit.load_pebble(source)
            assert cockpit.computer.state() == state
            assert cockpit.assembly == assembly
            assert cockpit.translated is None
