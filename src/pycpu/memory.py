"""Memory made of gates: a latch, a flip-flop and a register.

Think of a classroom whiteboard. Chalk on the board stays until someone wipes it,
so the board remembers. A gate on its own is like a puff of smoke: it shows its
answer and then it is gone. This file shows how to build a whiteboard out of
smoke, by sending a gate's answer back round to listen to itself.

A latch holds one bit. A flip-flop holds one bit and changes only on the beat of
the clock. A register is a row of flip-flops holding one whole number. Every
piece is made of NAND gates and nothing else; the one thing outside the gates is
`Register.poke`, which writes a starting value straight into the storage wires.
"""

from pycpu.circuit import Bus, Circuit, Clock, Wire
from pycpu.logic import in_own_scope, mux_bus, not_
from pycpu.simulator import Simulator


def make_clock(c: Circuit) -> Clock:
    """Add the two clock wires, `clk` and `write`, as inputs and return them.

    Drive them with `Simulator.tick`, which pulses `write` and then `clk`.
    """
    return Clock(clk=c.input("clk"), write=c.input("write"))


def _latch_into(c: Circuit, data: Wire, enable: Wire, q: Wire, qn: Wire) -> None:
    """Build a D latch whose output wires `q` and `qn` already exist as placeholders.

    Two NANDs gate `data` with `enable`; two more are the cross-coupled loop.
    The loop gate for `qn` is added first, so with quiet inputs the cell powers
    on holding 0. That guarantee holds only if `enable` is low at power-on; with
    `enable` high the latch follows `data` instead.
    """
    set_n = c.nand(data, enable)
    reset_n = c.nand(set_n, enable)
    # q_n's gate goes first so that, at power-on, a latch settles to 0, not 1.
    c.nand_into(reset_n, q, qn)
    c.nand_into(set_n, qn, q)


@in_own_scope
def d_latch(c: Circuit, data: Wire, enable: Wire) -> tuple[Wire, Wire]:
    """Add a latch that copies `data` while `enable` is 1 and holds it while 0.

    Four NAND gates. Returns `(q, q_n)`: the held bit and its opposite.
    """
    q, qn = c.wire_placeholder(), c.wire_placeholder()
    _latch_into(c, data, enable, q, qn)
    return q, qn


def _flip_flop_into(
    c: Circuit, data: Wire, clk: Wire, not_clk: Wire, q: Wire
) -> tuple[tuple[Wire, Wire], tuple[Wire, Wire]]:
    """Build a master-slave flip-flop that drives the existing wire `q`.

    The master is open while `clk` is low; the slave is open while it is high.
    Both cells are registered as state pairs so they can be poked, and returned
    as `(master, slave)`, each a `(q, q_n)` pair.
    """
    m_q, m_qn = c.wire_placeholder(), c.wire_placeholder()
    s_qn = c.wire_placeholder()
    with c.scope("master"):
        _latch_into(c, data, not_clk, m_q, m_qn)
    with c.scope("slave"):
        _latch_into(c, m_q, clk, q, s_qn)
    c.state_pair("master", m_q, m_qn)
    c.state_pair("slave", q, s_qn)
    return (m_q, m_qn), (q, s_qn)


@in_own_scope
def d_flip_flop(c: Circuit, data: Wire, clk: Wire) -> Wire:
    """Add a bit that copies `data` only as `clk` rises, and holds it otherwise.

    Two latches (master and slave) and one NOT: nine NAND gates. `clk` must be
    a primary clock wire (an input), because the flip-flop relies on its NOT being
    exactly one gate away from it.
    """
    q = c.wire_placeholder()
    _flip_flop_into(c, data, clk, not_(c, clk), q)
    return q


class Register:
    """A row of flip-flops holding one number, with a `load` switch.

    On each `clk` beat the register takes `data` if `load` is 1, and keeps its
    old number if `load` is 0. Each bit lives in its own part, `bit0` upwards,
    inside a part named after the register.
    """

    def __init__(
        self, c: Circuit, width: int, data: Bus, load: Wire, clock: Clock, name: str
    ) -> None:
        """Add the register's gates to the circuit.

        Args:
            c: The circuit to build in.
            width: How many bits the register holds.
            data: The wires to copy when loading; they may be placeholders.
            load: A wire that is 1 when the register should take `data`.
            clock: The clock whose `clk` wire steps the register.
            name: The name of the part that holds the register (no dots).

        Raises:
            ValueError: If `data` is not `width` wires wide.

        """
        if len(data) != width:
            msg = f"bus width mismatch: register of {width} bits given {len(data)} wires"
            raise ValueError(msg)
        self.q: Bus = tuple(c.wire_placeholder() for _ in range(width))
        self._cells: list[tuple[tuple[Wire, Wire], tuple[Wire, Wire]]] = []
        with c.scope(name):
            chosen = mux_bus(c, load, self.q, data)  # load 0 keeps q, load 1 takes data
            not_clk = not_(c, clock.clk)
            for i in range(width):
                with c.scope(f"bit{i}"):
                    self._cells.append(_flip_flop_into(c, chosen[i], clock.clk, not_clk, self.q[i]))

    def peek(self, sim: Simulator) -> int:
        """Read the number the register holds, from its output wires."""
        return sim.get_bus(self.q)

    def poke(self, sim: Simulator, value: int) -> None:
        """Write a number straight into the register, with no clock beat.

        Both the master and the slave of every bit are written, or the master
        would still hold the old bit. The circuit is settled afterwards.

        Raises:
            ValueError: If `value` is negative or too big for the register.

        """
        width = len(self._cells)
        if not 0 <= value < 1 << width:
            msg = f"{value} does not fit in {width} bits"
            raise ValueError(msg)
        for i, (master, slave) in enumerate(self._cells):
            sim.poke_pairs([master, slave], (value >> i) & 1)
        sim.settle()
