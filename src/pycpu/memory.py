"""Memory made of gates: a latch, a flip-flop and a register.

Think of a classroom whiteboard. Chalk on the board stays until someone wipes it,
so the board remembers. A gate on its own is like a puff of smoke: it shows its
answer and then it is gone. This file shows how to build a whiteboard out of
smoke, by sending a gate's answer back round to listen to itself.

A latch holds one bit. A flip-flop holds one bit and changes only on the beat of
the clock. A register is a row of flip-flops holding one whole number. RAM is a
wall of numbered lockers, each a row of latches, with an address to pick one.
Every piece is made of NAND gates and nothing else; the one thing outside the
gates is `poke`, which writes a starting value straight into the storage wires.
"""

from collections.abc import Sequence

from pycpu.circuit import Bus, Circuit, Clock, Wire
from pycpu.logic import and_, decoder, in_own_scope, mux_bus, not_, or_many
from pycpu.simulator import Simulator

RAM_ADDRESS_BITS = 12
RAM_WORDS = 1 << RAM_ADDRESS_BITS
WORD_BITS = 16


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


class Ram:
    """A wall of numbered lockers, each holding one 16-bit word.

    Give it an address and `out` shows that word. Raise `write_enable` and tick
    the clock and the word at the address becomes `data`. Every bit is a D latch
    (four NAND gates); the address is split in half and each half is decoded,
    and a word's line is one row line AND one column line, so changing the
    address stirs only a few gates. Word `N` lives in part `word<N>`, its bits in
    `bit<M>` inside it, all inside a part named after the RAM.

    Each cell is a level-sensitive latch: it follows `data` for as long as its
    word's write line is up. So `data` and `address` must not depend on
    `ram.out` while a write happens (for example `data = ram.out + 1` never
    settles, and an address taken straight from `ram.out` can send the write to
    the wrong words). Pass such a value through a `Register` first.
    """

    def __init__(
        self,
        c: Circuit,
        address: Bus,
        data: Bus,
        write_enable: Wire,
        clock: Clock,
        name: str = "ram",
    ) -> None:
        """Add the RAM's gates to the circuit.

        Args:
            c: The circuit to build in.
            address: The wires choosing a word; there are `2 ** len(address)` words.
            data: Sixteen wires to copy into the chosen word when writing.
            write_enable: A wire that is 1 when the beat should write `data`.
            clock: The clock whose `write` pulse times the write.
            name: The name of the part that holds the RAM (no dots).

        Raises:
            ValueError: If `data` is not 16 wires wide, or `address` is empty.

        """
        if len(data) != WORD_BITS:
            msg = f"bus width mismatch: RAM words are {WORD_BITS} bits, given {len(data)} wires"
            raise ValueError(msg)
        if not address:
            msg = "RAM needs at least one address wire"
            raise ValueError(msg)
        low_bits = len(address) // 2
        self._words = 1 << len(address)
        self._cells: list[list[tuple[Wire, Wire]]] = []
        with c.scope(name):
            write_pulse = and_(c, write_enable, clock.write)
            with c.scope("decoder"):
                columns = decoder(c, address[:low_bits])
                rows = decoder(c, address[low_bits:])
            picked: list[list[Wire]] = [[] for _ in range(WORD_BITS)]
            for word in range(self._words):
                row, column = divmod(word, len(columns))
                with c.scope(f"word{word}"):
                    # Gates are added directly (not via and_) to keep scopes few.
                    word_line = not_(c, c.nand(rows[row], columns[column]))
                    write_line = not_(c, c.nand(word_line, write_pulse))
                    cells: list[tuple[Wire, Wire]] = []
                    for bit in range(WORD_BITS):
                        with c.scope(f"bit{bit}"):
                            q, qn = c.wire_placeholder(), c.wire_placeholder()
                            _latch_into(c, data[bit], write_line, q, qn)
                            c.state_pair("cell", q, qn)
                            picked[bit].append(not_(c, c.nand(word_line, q)))
                            cells.append((q, qn))
                    self._cells.append(cells)
            outputs: list[Wire] = []
            for bit in range(WORD_BITS):
                with c.scope(f"read{bit}"):
                    outputs.append(or_many(c, picked[bit]))
        self.out: Bus = tuple(outputs)

    def peek(self, sim: Simulator, address: int) -> int:
        """Read the word stored at `address` straight from its latches."""
        self._check_address(address)
        return sum(sim.get(q) << bit for bit, (q, _) in enumerate(self._cells[address]))

    def poke(self, sim: Simulator, address: int, value: int) -> None:
        """Write a word straight into its latches, with no clock beat and no settling.

        Settle the simulator afterwards (or use `load`) to see it on `out`.

        Raises:
            ValueError: If `address` is out of range or `value` does not fit in 16 bits.

        """
        self._check_address(address)
        if not 0 <= value < 1 << WORD_BITS:
            msg = f"{value} does not fit in {WORD_BITS} bits"
            raise ValueError(msg)
        for bit, pair in enumerate(self._cells[address]):
            sim.poke_pairs([pair], (value >> bit) & 1)

    def load(self, sim: Simulator, words: Sequence[int]) -> None:
        """Poke a whole list of words, starting at address 0, then settle once.

        Raises:
            ValueError: If there are more words than the RAM holds.

        """
        if len(words) > self._words:
            msg = f"{len(words)} words do not fit in a RAM of {self._words} words"
            raise ValueError(msg)
        for address, value in enumerate(words):
            self.poke(sim, address, value)
        sim.settle()

    def _check_address(self, address: int) -> None:
        """Raise `ValueError` unless `address` names a word."""
        if not 0 <= address < self._words:
            msg = f"address {address} is outside the RAM's {self._words} words"
            raise ValueError(msg)
