"""The CPU built from gates: a cook who picks up a card on one drum beat and obeys it on the next.

A drummer beats a slow drum in the kitchen. On the first beat the cook picks up
the recipe card the finger points at and slides the finger to the next card
(fetch). On the second beat the cook reads the card and does what it says
(decode and execute). Pick up, do; pick up, do. That two-beat habit, wired from
the registers, the ALU, the control unit's parts and the real RAM, is a whole
computer.

Everything that thinks here is NAND gates: the choosers, the adders, the
decoder and every register. The Python in `GateMachine` only drives the clock,
reads and writes the storage cells (`peek` and `poke`), and plays the part of
the screen plugged into the output port, which listens to the CPU's real
`port_write` wire and never decides anything for it.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import IntEnum

from pycpu.arithmetic import AluOutput, alu, ripple_adder
from pycpu.circuit import Bus, Circuit, Wire
from pycpu.cpu_parts import RegisterFile, condition_met, opcode_lines, outside_ram, sign_extend
from pycpu.isa import (
    ADDR12_BITS,
    IMM8_BITS,
    OFF6_BITS,
    OFF9_BITS,
    OPCODE_SHIFT,
    RA_SHIFT,
    RB_SHIFT,
    RD_SHIFT,
    WORD_MASK,
    Fault,
    Opcode,
)
from pycpu.logic import and_, buffer_into, is_zero, mux_bus, not_, not_bus, or_, or_many
from pycpu.memory import RAM_ADDRESS_BITS, WORD_BITS, Ram, Register, make_clock
from pycpu.simulator import NOTHING_WAITING, Simulator
from pycpu.state import HALT_CODE_MAX, Flags, MachineState, power_on, program_state, validate_state

HALT_CODE_BITS = HALT_CODE_MAX.bit_length()
FIELD_BITS = 3
FLAG_COUNT = len(Flags._fields)
LAST_STAGE = 8  # the gates that ripple after `clk` falls: the end of a clock cycle
WRITE_RISE = 1  # the stage at which the `write` wire goes up


class Phase(IntEnum):
    """Which beat comes next: picking up a card (fetch) or obeying it (execute)."""

    FETCH = 0
    EXECUTE = 1


@dataclass(frozen=True)
class MicroStep:
    """One tiny movement of the machine: one gate thinking, or one clock wire moving.

    Attributes:
        kind: `"gate"` for one gate evaluation, `"edge"` for a clock wire going up
            or down, `"end"` when an instruction has just finished.
        gate: The id of the gate that was evaluated, or -1 when it was not a gate.
        wire: The clock wire that moved (`"write"` or `"clk"`) for an edge, else `""`.
        value: The gate's new output, or the clock wire's new value; 0 for `"end"`.
        phase: The beat the movement belongs to.

    """

    kind: str
    gate: int
    wire: str
    value: int
    phase: Phase


# The four clock edges of one cycle, in the order `Simulator.tick` makes them.
_EDGES = (("write", 1), ("write", 0), ("clk", 1), ("clk", 0))


def _placeholders(c: Circuit, width: int) -> Bus:
    """Make `width` wires now that a gate will drive later (see `_drive`).

    A register's data and `load` wires are needed when the register is built,
    but the values that feed them are worked out from registers built later.
    """
    return tuple(c.wire_placeholder() for _ in range(width))


def _drive(c: Circuit, source: Bus, target: Bus) -> None:
    """Make every placeholder in `target` a copy of the matching wire in `source`."""
    for wire, placeholder in zip(source, target, strict=True):
        buffer_into(c, wire, placeholder)


def _constant(c: Circuit, value: int, width: int) -> Bus:
    """Spell a fixed number with the circuit's always-1 and always-0 wires."""
    return tuple(c.high if (value >> bit) & 1 else c.low for bit in range(width))


def _field(word: Bus, shift: int, width: int) -> Bus:
    """Take the `width` wires of a field starting at bit `shift`: a field is just wires."""
    return word[shift : shift + width]


@dataclass
class _Wires:
    """The named wires one build step hands to the next while the CPU is wired up.

    Fields after `address` are filled in by the later steps.
    """

    line: Bus
    imm8: Bus
    fetch: Wire
    execute: Wire
    running: Wire
    memory_op: Wire
    bank: RegisterFile
    write_back: Bus
    register_write: Wire
    out: AluOutput
    met: Wire
    sp_down: Bus
    sp_up: Bus
    pushes: Wire
    pops: Wire
    address: Bus
    outside: Wire = -1
    go: Wire = -1
    act: Wire = -1
    ram_write: Wire = -1
    ram_data: Bus = ()


class GateMachine:
    """A whole computer made of NAND gates: the CPU wired to the real RAM.

    One clock cycle is one beat. On a fetch beat the instruction register `ir`
    takes the word at `pc`, and `pc` takes `pc + 1`. On an execute beat the
    instruction in `ir` is decoded and obeyed, and its results load at the
    clock's rise. `step` runs one whole instruction, `step_cycle` one beat, and
    `micro_step` one gate or one clock edge. The state goes in and out as the
    same `MachineState` the fast engine uses, so the two can be compared.

    Attributes:
        words: How many words of RAM the machine has.
        circuit: The circuit: the CPU in part `cpu`, the RAM in part `ram`.
        simulator: The simulator running the circuit.
        port_write: The wire that is 1 when this beat stores to the output port.
        port_data: The 16 wires carrying the word a `STORE` would write.
        taps: For each part of the CPU (such as `"cpu.alu"`), its inputs and then
            its outputs, each a name for a row of wires the CPU already has. They are
            recorded while the CPU is wired up and only read after that; a tap never
            adds a gate or a wire.
        tap_outputs: For each part in `taps`, which of its names are outputs.
        builders: For each part in `taps`, the function or method whose code built it,
            and the name of the `with c.scope(...)` block to show (None means the part's
            own last path segment). The Cockpit reads that live source for its code panel.

    """

    def __init__(self, address_bits: int = RAM_ADDRESS_BITS) -> None:
        """Build the CPU and its RAM from gates, then switch the machine on.

        Args:
            address_bits: How many address wires the RAM has; it holds
                `2 ** address_bits` words.

        Raises:
            ValueError: If `address_bits` is below 1, or so big that the RAM would
                reach the output port's address.

        """
        if not 1 <= address_bits < WORD_BITS:
            msg = f"address_bits must be from 1 to {WORD_BITS - 1}, not {address_bits}"
            raise ValueError(msg)
        self.words = 1 << address_bits
        # Registers whose input placeholders still wait for a driver (see `_feed`).
        self._pending: dict[str, tuple[Bus, Wire]] = {}
        self.taps: dict[str, dict[str, Bus]] = {}
        self.tap_outputs: dict[str, tuple[str, ...]] = {}
        self.builders: dict[str, tuple[Callable[..., object], str | None]] = {}
        c = Circuit()
        self.circuit = c
        self._clock = make_clock(c)
        ram_address = _placeholders(c, address_bits)
        ram_data = _placeholders(c, WORD_BITS)
        (ram_write,) = _placeholders(c, 1)
        self._ram = Ram(c, ram_address, ram_data, ram_write, self._clock)
        self._tap(
            "ram",
            {"address": ram_address, "data": ram_data, "write": (ram_write,)},
            {"out": self._ram.out},
            Ram.__init__,
        )
        with c.scope("cpu"):
            address, data, write = self._build_cpu(c, address_bits)
            with c.scope("ram_wires"):
                _drive(c, address[:address_bits], ram_address)
                _drive(c, data, ram_data)
                _drive(c, (write,), (ram_write,))
        self.simulator = Simulator(c)
        self._gate_outputs = c.gate_wires[2]
        self._output: list[int] = []
        self._stage = 0
        self._cycle_phase = Phase.FETCH
        self.load_state(power_on(self.words))

    def _build_cpu(self, c: Circuit, address_bits: int) -> tuple[Bus, Bus, Wire]:
        """Add the CPU's gates; return the RAM's address, data and write wires.

        The registers come first, with placeholders on their inputs, because
        the logic that feeds them reads their own outputs. Every placeholder is
        driven before this returns; a register still waiting in `_pending` is a
        wiring mistake, caught here by name (the `Simulator` would only count
        the undriven wires).
        """
        self._phase = self._register(c, "phase", 1)
        self._ir = self._register(c, "ir", WORD_BITS, data=self._ram.out)
        self._pc = self._register(c, "pc", WORD_BITS)
        self._sp = self._register(c, "sp", WORD_BITS)
        self._flags = self._register(c, "flags", FLAG_COUNT)
        with c.scope("halt"):
            self._halted = self._register(c, "halted", 1, data=(c.high,))
            self._halt_code = self._register(c, "halt_code", HALT_CODE_BITS)
        line = opcode_lines(c, self._ir.q[OPCODE_SHIFT:])
        w = self._build_datapath(c, line)
        self._build_checks(c, w, address_bits)
        self._build_next_pc(c, w)
        self._build_write_back(c, w)
        if self._pending:
            msg = f"registers left with undriven inputs: {sorted(self._pending)}"
            raise RuntimeError(msg)
        return w.address, w.ram_data, w.ram_write

    def _register(self, c: Circuit, name: str, width: int, data: Bus | None = None) -> Register:
        """Build a register whose `load` (and, unless given, data) wires are filled in later."""
        load = c.wire_placeholder()
        data_in = _placeholders(c, width) if data is None else data
        if data is None:
            self._pending[name] = (data_in, load)
        else:
            self._pending[name] = ((), load)
        return Register(c, width, data_in, load, self._clock, name)

    def _tap(
        self,
        part: str,
        inputs: dict[str, Bus],
        outputs: dict[str, Bus],
        builder: Callable[..., object],
        scope: str | None = None,
    ) -> None:
        """Name a part's input and output wires, and the code that built it.

        This only writes names down, like labels tied onto cables already laid:
        it makes no gate and no wire. `builder` is the function or method that holds
        the part's `with c.scope(...)` block, so the Cockpit can show its source; `scope`
        names that block when it is not called after the part's last path segment; an empty
        `scope` means every line of the builder makes the part, so all of it is shown.
        """
        self.builders[part] = (builder, scope)
        self.taps[part] = {**inputs, **outputs}
        self.tap_outputs[part] = tuple(outputs)

    def _feed(self, c: Circuit, name: str, load: Wire, data: Bus = ()) -> None:
        """Drive the waiting `load` (and data) placeholders of the register `name`."""
        data_in, load_in = self._pending.pop(name)
        _drive(c, (load,), (load_in,))
        _drive(c, data, data_in)

    def _build_datapath(self, c: Circuit, line: Bus) -> _Wires:
        """Add the register file, the ALU and the choosers in front of them.

        The register file's windows read `ra` and `rb`, or `rd` where an
        instruction needs it. The ALU's second input and its job dial are
        chosen by the opcode lines. Two adders keep `sp - 1` and `sp + 1`
        ready for the stack, and the address chooser picks `pc`, the ALU's
        answer, `sp - 1` (a push) or `sp` (a pop).
        """
        ir = self._ir.q
        rd = _field(ir, RD_SHIFT, FIELD_BITS)
        imm8 = _field(ir, 0, IMM8_BITS)
        with c.scope("control"):
            execute = self._phase.q[0]
            fetch = not_(c, execute)
            running = not_(c, self._halted.q[0])
            # Window a reads rd for the two opcodes that change rd in place.
            read_a = mux_bus(
                c, or_(c, line[Opcode.ADDI], line[Opcode.LHI]), _field(ir, RA_SHIFT, FIELD_BITS), rd
            )
            # Window b reads rd for the opcodes that send rd somewhere.
            sends_rd = or_many(c, [line[Opcode.STORE], line[Opcode.PUSH], line[Opcode.SETSP]])
            read_b = mux_bus(c, sends_rd, _field(ir, RB_SHIFT, FIELD_BITS), rd)
        write_back, register_write = _placeholders(c, WORD_BITS), c.wire_placeholder()
        bank = RegisterFile(c, write_back, register_write, rd, read_a, read_b, self._clock)
        self._registers = bank.registers
        self._tap(
            "cpu.registers",
            {
                "write": (register_write,),
                "write_select": rd,
                "data": write_back,
                "read_a": read_a,
                "read_b": read_b,
            },
            {"a": bank.a, "b": bank.b},
            RegisterFile.__init__,
        )
        with c.scope("operand"):
            memory_op = or_(c, line[Opcode.LOAD], line[Opcode.STORE])
            b = mux_bus(c, memory_op, bank.b, sign_extend(c, _field(ir, 0, OFF6_BITS)))
            b = mux_bus(c, line[Opcode.ADDI], b, sign_extend(c, imm8))
            # CMP always subtracts; ADDI, LOAD and STORE always add; others use fn.
            forced = or_many(
                c, [line[Opcode.CMP], line[Opcode.ADDI], line[Opcode.LOAD], line[Opcode.STORE]]
            )
            op = mux_bus(c, forced, _field(ir, 0, FIELD_BITS), (line[Opcode.CMP], c.low, c.low))
        out = alu(c, bank.a, b, op)
        self._tap(
            "cpu.alu",
            {"a": bank.a, "b": b},
            {"result": out.result, "flags": (out.zero, out.negative, out.carry, out.overflow)},
            alu,
            scope="",  # the whole function: its flags are made after the block closes
        )
        flags = self._flags.q
        met = condition_met(c, rd, flags[0], flags[1], flags[2], flags[3])
        sp = self._sp.q
        with c.scope("sp_minus_1"):
            # Adding 0xFFFF is adding -1 in two's complement: the finger moves down.
            sp_down, _ = ripple_adder(c, sp, _constant(c, WORD_MASK, WORD_BITS), c.low)
        with c.scope("sp_plus_1"):
            sp_up, _ = ripple_adder(c, sp, _constant(c, 0, WORD_BITS), c.high)
        with c.scope("address_mux"):
            pushes = or_(c, line[Opcode.PUSH], line[Opcode.CALL])
            pops = or_(c, line[Opcode.POP], line[Opcode.RET])
            stack_spot = mux_bus(c, pops, sp_down, sp)
            execute_address = mux_bus(c, or_(c, pushes, pops), out.result, stack_spot)
            address = mux_bus(c, execute, self._pc.q, execute_address)
        self._tap(
            "cpu.address_mux",
            {"pc": self._pc.q, "alu": out.result, "sp": sp, "sp_minus_1": sp_down},
            {"address": address},
            self._build_datapath,
        )
        return _Wires(
            line=line,
            imm8=imm8,
            fetch=fetch,
            execute=execute,
            running=running,
            memory_op=memory_op,
            bank=bank,
            write_back=write_back,
            register_write=register_write,
            out=out,
            met=met,
            sp_down=sp_down,
            sp_up=sp_up,
            pushes=pushes,
            pops=pops,
            address=address,
        )

    def _build_checks(self, c: Circuit, w: _Wires, address_bits: int) -> None:
        """Add the output port's wire and the fault and halt logic.

        A bad address (outside RAM, except a STORE to the port) or a HALT
        instruction stops the machine and blocks every other load that beat.
        The stack opcodes need RAM too, so for them even `0xFFFF` is bad.
        """
        w.outside = outside_ram(c, w.address, address_bits)
        with c.scope("port"):
            port_store = and_(c, w.line[Opcode.STORE], is_zero(c, not_bus(c, w.address)))
            self.port_write: Wire = and_(c, and_(c, w.execute, port_store), w.running)
            self.port_data: Bus = w.bank.b
        with c.scope("fault"):
            uses_memory = or_many(c, [and_(c, w.memory_op, not_(c, port_store)), w.pushes, w.pops])
            needs_ram = or_(c, w.fetch, uses_memory)
            bad = and_(c, w.outside, needs_ram)
            halt_instruction = and_(c, w.execute, w.line[Opcode.HALT])
            stop = or_(c, bad, halt_instruction)
            w.go = and_(c, w.running, not_(c, stop))  # nothing else may load after a stop
            w.act = and_(c, w.go, w.execute)
            halt_load = and_(c, w.running, stop)
            self._feed(c, "halted", halt_load)
            fault_code = _constant(c, Fault.BAD_ADDRESS, HALT_CODE_BITS)
            code = mux_bus(c, bad, w.imm8, fault_code)
            self._feed(c, "halt_code", halt_load, code)
        # The outputs are what the halt logic sends this beat, not what the `halted` and
        # `halt_code` registers hold: those only take it in when the clock rises.
        self._tap(
            "cpu.halt",
            {"bad_address": (bad,), "halt_instruction": (halt_instruction,), "imm8": w.imm8},
            {"halt_now": (halt_load,), "code": code},
            self._build_checks,
            scope="fault",
        )

    def _build_next_pc(self, c: Circuit, w: _Wires) -> None:
        """Add the two adders and the choosers that decide `pc`, `ir` and `phase`.

        `JMP` and `CALL` take the 12-bit address from `ir`; `RET` takes the
        return address from `ram.out`, which is safe because `pc` is a
        register and nothing writes the RAM on a `RET` beat.
        """
        ir, pc = self._ir.q, self._pc.q
        with c.scope("pc_plus_1"):
            plus_one, _ = ripple_adder(c, pc, _constant(c, 0, WORD_BITS), c.high)
        with c.scope("branch_target"):
            target, _ = ripple_adder(c, pc, sign_extend(c, _field(ir, 0, OFF9_BITS)), c.low)
        with c.scope("next_pc"):
            jump_to = (*_field(ir, 0, ADDR12_BITS), *_constant(c, 0, WORD_BITS - ADDR12_BITS))
            line = w.line
            jumps = or_(c, line[Opcode.JMP], line[Opcode.CALL])
            elsewhere = mux_bus(c, jumps, target, jump_to)
            elsewhere = mux_bus(c, line[Opcode.RET], elsewhere, self._ram.out)
            moves = or_many(c, [jumps, line[Opcode.RET], and_(c, line[Opcode.BR], w.met)])
            pc_load = and_(c, w.go, or_(c, w.fetch, moves))
            next_pc = mux_bus(c, w.execute, plus_one, elsewhere)
            self._feed(c, "pc", pc_load, next_pc)
            self._feed(c, "ir", and_(c, w.go, w.fetch))
            self._feed(c, "phase", w.go, (w.fetch,))
        self._tap(
            "cpu.next_pc",
            {
                "pc": pc,
                "pc_plus_1": plus_one,
                "branch_target": target,
                "jump_to": jump_to,
                "memory": self._ram.out,
            },
            {"next_pc": next_pc, "load": (pc_load,)},
            self._build_next_pc,
        )

    def _build_write_back(self, c: Circuit, w: _Wires) -> None:
        """Add the choosers for what goes into `rd`, `sp` and the RAM, and their load wires."""
        line = w.line
        with c.scope("write_back"):
            from_ram = or_(c, line[Opcode.LOAD], line[Opcode.POP])
            value = mux_bus(c, from_ram, w.out.result, self._ram.out)
            value = mux_bus(c, line[Opcode.LI], value, (*w.imm8, *_constant(c, 0, IMM8_BITS)))
            value = mux_bus(c, line[Opcode.LHI], value, (*w.bank.a[:IMM8_BITS], *w.imm8))
            value = mux_bus(c, line[Opcode.GETSP], value, self._sp.q)
            _drive(c, value, w.write_back)
            writers = [
                Opcode.ALU,
                Opcode.LI,
                Opcode.LHI,
                Opcode.LOAD,
                Opcode.POP,
                Opcode.GETSP,
                Opcode.ADDI,
            ]
            loads_rd = or_many(c, [line[o] for o in writers])
            write = and_(c, w.act, loads_rd)
            _drive(c, (write,), (w.register_write,))
            sets_flags = or_many(c, [line[Opcode.ALU], line[Opcode.CMP], line[Opcode.ADDI]])
            out = w.out
            flags = (out.zero, out.negative, out.carry, out.overflow)
            self._feed(c, "flags", and_(c, w.act, sets_flags), flags)
        with c.scope("next_sp"):
            moved = mux_bus(c, w.pops, w.sp_down, w.sp_up)
            sp_value = mux_bus(c, line[Opcode.SETSP], moved, w.bank.b)
            sp_load = or_many(c, [w.pushes, w.pops, line[Opcode.SETSP]])
            sp_write = and_(c, w.act, sp_load)
            self._feed(c, "sp", sp_write, sp_value)
        rd = _field(self._ir.q, RD_SHIFT, FIELD_BITS)
        self._tap(
            "cpu.write_back",
            {
                "alu": w.out.result,
                "memory": self._ram.out,
                "imm8": w.imm8,
                "register_a": w.bank.a,
                "sp": self._sp.q,
                "destination": rd,
            },
            {"value": value, "write": (write,)},
            self._build_write_back,
        )
        self._tap(
            "cpu.next_sp",
            {
                "sp": self._sp.q,
                "sp_minus_1": w.sp_down,
                "sp_plus_1": w.sp_up,
                "register": w.bank.b,
            },
            {"next_sp": sp_value, "load": (sp_write,)},
            self._build_write_back,
        )
        with c.scope("ram_data"):
            # CALL writes the return address (pc); STORE and PUSH write window b.
            w.ram_data = mux_bus(c, line[Opcode.CALL], w.bank.b, self._pc.q)
            writes = or_(c, line[Opcode.STORE], w.pushes)
            w.ram_write = and_(c, w.act, and_(c, writes, not_(c, w.outside)))

    @property
    def phase(self) -> Phase:
        """Return which beat comes next: `Phase.FETCH` or `Phase.EXECUTE`."""
        return Phase(self._phase.peek(self.simulator))

    def _is_halted(self) -> bool:
        """Return True when the `halted` register holds 1."""
        return self._halted.peek(self.simulator) == 1

    @property
    def at_boundary(self) -> bool:
        """Return True when no instruction is part-way through (always, once halted)."""
        return self._stage == 0 and (self._is_halted() or self.phase == Phase.FETCH)

    def load_state(self, state: MachineState) -> None:
        """Replace the whole machine with `state`, writing straight into its storage.

        The clock wires drop to 0 first, so no beat is half way through. `ir`
        and `phase` are set to 0, so the next beat is a fetch.

        Raises:
            ValueError: If the state does not fit this machine, by the same rules
                as the fast engine (`validate_state`). The machine is left unchanged.

        """
        validate_state(state, self.words)
        sim = self.simulator
        sim.set(self._clock.clk, 0)
        sim.set(self._clock.write, 0)
        sim.settle()
        self._phase.poke(sim, Phase.FETCH)
        self._ir.poke(sim, 0)
        self._pc.poke(sim, state.pc)
        self._sp.poke(sim, state.sp)
        self._flags.poke(sim, sum(flag << bit for bit, flag in enumerate(state.flags)))
        self._halted.poke(sim, int(state.halted))
        self._halt_code.poke(sim, state.halt_code)
        for register, value in zip(self._registers, state.registers, strict=True):
            register.poke(sim, value)
        self._ram.load(sim, state.memory)
        self._output = list(state.output)
        self._stage = 0
        self._cycle_phase = Phase.FETCH

    def state(self) -> MachineState:
        """Read the whole machine into a frozen `MachineState`, using `peek`."""
        sim = self.simulator
        flags = self._flags.peek(sim)
        return MachineState(
            pc=self._pc.peek(sim),
            sp=self._sp.peek(sim),
            registers=tuple(register.peek(sim) for register in self._registers),
            flags=Flags(*((flags >> bit) & 1 for bit in range(FLAG_COUNT))),
            memory=tuple(self._ram.peek(sim, address) for address in range(self.words)),
            halted=self._is_halted(),
            halt_code=self._halt_code.peek(sim),
            output=tuple(self._output),
        )

    def load_program(self, words: Sequence[int]) -> None:
        """Power on, then put `words` into memory starting at address 0.

        Raises:
            ValueError: If the program is bigger than memory or holds a non-word.

        """
        self.load_state(program_state(words, self.words))

    def _edge(self) -> MicroStep:
        """Move the clock wire this stage names, and listen to the port on `write`'s rise.

        The screen is outside the CPU: at the moment the `write` pulse starts it
        looks at the real `port_write` wire and, if it is 1, takes the word on
        the store data wires, the way a terminal reads a cable.
        """
        name, value = _EDGES[(self._stage - 1) // 2]
        sim = self.simulator
        if self._stage == WRITE_RISE and sim.get(self.port_write):
            self._output.append(sim.get_bus(self.port_data))
        wire = self._clock.write if name == "write" else self._clock.clk
        sim.set(wire, value)
        self._stage += 1
        return MicroStep("edge", NOTHING_WAITING, name, value, self._cycle_phase)

    def step_cycle(self) -> None:
        """Finish the current clock cycle (one beat), or play a whole one from its start.

        This follows `Simulator.tick`: settle, `write` up and down, `clk` up and
        down, settling after each. A halted machine at a boundary does nothing.
        """
        if self._stage == 0:
            if self._is_halted():
                return
            self._cycle_phase = self.phase
        while True:
            if self._stage % 2:
                self._edge()
                continue
            self.simulator.settle()
            if self._stage == LAST_STAGE:
                self._stage = 0
                return
            self._stage += 1

    def step(self) -> bool:
        """Run one whole instruction (two beats); return False if already halted."""
        if self.at_boundary and self._is_halted():
            return False
        self.step_cycle()
        while not self.at_boundary:
            self.step_cycle()
        return True

    def micro_step(self) -> MicroStep:
        """Do one tiny thing: evaluate one gate, or move one clock wire.

        The order is exactly `Simulator.tick`'s, for the fetch beat and then the
        execute beat. When an instruction has just finished, the step is of
        kind `"end"`; a halted machine only ever returns `"end"`.
        """
        if self._stage == 0:
            if self._is_halted():
                return MicroStep("end", NOTHING_WAITING, "", 0, self.phase)
            self._cycle_phase = self.phase
        sim = self.simulator
        while True:
            if self._stage % 2:
                return self._edge()
            gate = sim.step()
            if gate != NOTHING_WAITING:
                output = sim.get(self._gate_outputs[gate])
                return MicroStep("gate", gate, "", output, self._cycle_phase)
            if self._stage < LAST_STAGE:
                self._stage += 1
                continue
            self._stage = 0
            if self.at_boundary:
                return MicroStep("end", NOTHING_WAITING, "", 0, self._cycle_phase)
            self._cycle_phase = self.phase

    def run(self, max_steps: int) -> int:
        """Step until the machine halts or `max_steps` steps are taken; return the count."""
        steps = 0
        while steps < max_steps and self.step():
            steps += 1
        return steps
