"""The fast engine: a cook who follows recipe cards using plain arithmetic, not gates.

The gate-built CPU does every step with real NAND gates, which is wonderful to
look inside and slow to run. The fast engine does exactly the same job with ordinary
Python numbers and `if` statements, thousands of times quicker. It is the answer
key: later, a test runs both engines on the same programs and checks that they never
disagree. That is why this is the one place, besides the test helpers, where Python
works out logic directly, and why it never feeds the gate view.

`alu_model` is the ALU written as plain arithmetic, and `FastMachine` is the whole
computer built on it, following the definitions in `isa.py`.
"""

from collections.abc import Sequence
from dataclasses import replace

from pycpu.arithmetic import AluOp
from pycpu.isa import (
    OUTPUT_PORT,
    WORD_MASK,
    Condition,
    Fault,
    Opcode,
    condition_holds,
    decode,
)
from pycpu.memory import RAM_WORDS, WORD_BITS
from pycpu.state import BYTE_MASK, REGISTER_COUNT, Flags, MachineState, power_on

SIGN_BIT = 1 << (WORD_BITS - 1)
BYTE_BITS = 8


def alu_model(a: int, b: int, op: AluOp) -> tuple[int, Flags]:
    """Work out what the gate ALU would give, using plain integers.

    Returns the 16-bit result and the four flags, matching `pycpu.arithmetic.alu`
    bit for bit: carry is the carry out for `ADD`, 1 for `SUB` when nothing was
    borrowed, the bit shifted out for `SHL` and `SHR`, and 0 for the logic
    operations and `PASS_B`; overflow is 1 only for a signed `ADD` or `SUB` that
    does not fit.
    """
    carry = overflow = 0
    match op:
        case AluOp.ADD:
            total = a + b
            result, carry = total & WORD_MASK, total >> WORD_BITS
            overflow = int(bool(~(a ^ b) & (a ^ result) & SIGN_BIT))
        case AluOp.SUB:
            total = a + (WORD_MASK - b) + 1
            result, carry = total & WORD_MASK, total >> WORD_BITS
            overflow = int(bool((a ^ b) & (a ^ result) & SIGN_BIT))
        case AluOp.AND:
            result = a & b
        case AluOp.OR:
            result = a | b
        case AluOp.XOR:
            result = a ^ b
        case AluOp.SHL:
            result, carry = (a << 1) & WORD_MASK, a >> (WORD_BITS - 1)
        case AluOp.SHR:
            result, carry = a >> 1, a & 1
        case AluOp.PASS_B:
            result = b
    flags = Flags(
        zero=int(result == 0),
        negative=int(bool(result & SIGN_BIT)),
        carry=carry,
        overflow=overflow,
    )
    return result, flags


class FastMachine:
    """A whole computer run with plain Python: fetch a word, obey it, repeat.

    It keeps its state in lists and only builds a frozen `MachineState` when asked
    (`state()`), because that is quicker. Any word is a valid instruction and any
    state can be loaded; a bad memory address halts the machine with
    `Fault.BAD_ADDRESS` and never raises an exception.
    """

    def __init__(self, words: int = RAM_WORDS) -> None:
        """Make a powered-on machine with `words` words of memory.

        Raises:
            ValueError: If `words` is below 1 or reaches the output port's address.

        """
        if not 1 <= words < OUTPUT_PORT:
            msg = f"words must be from 1 to {OUTPUT_PORT - 1}, not {words}"
            raise ValueError(msg)
        self.words = words
        self._pc: int = 0
        self._sp = words
        self._registers: list[int] = []
        self._flags = Flags(0, 0, 0, 0)
        self._memory: list[int] = []
        self._halted = False
        self._halt_code = 0
        self._output: list[int] = []
        self.load_state(power_on(words))

    def load_state(self, state: MachineState) -> None:
        """Replace the whole machine with `state`.

        Raises:
            ValueError: If the memory is the wrong length, or a register, `pc`,
                `sp`, `halt_code` or output word is outside 0-65535, or a flag is
                not 0 or 1. The machine is left unchanged.

        """
        _validate(state, self.words)
        self._pc = state.pc
        self._sp = state.sp
        self._registers = list(state.registers)
        self._flags = state.flags
        self._memory = list(state.memory)
        self._halted = state.halted
        self._halt_code = state.halt_code
        self._output = list(state.output)

    def state(self) -> MachineState:
        """Return a frozen copy of the machine as it is now."""
        return MachineState(
            pc=self._pc,
            sp=self._sp,
            registers=tuple(self._registers),
            flags=self._flags,
            memory=tuple(self._memory),
            halted=self._halted,
            halt_code=self._halt_code,
            output=tuple(self._output),
        )

    def load_program(self, words: Sequence[int]) -> None:
        """Power on, then put `words` into memory starting at address 0.

        Raises:
            ValueError: If the program is bigger than memory or holds a non-word.

        """
        if len(words) > self.words:
            msg = f"a program of {len(words)} words does not fit in {self.words} words of memory"
            raise ValueError(msg)
        for word in words:
            if not 0 <= word <= WORD_MASK:
                msg = f"program word {word} is not a 16-bit number"
                raise ValueError(msg)
        state = power_on(self.words)
        memory = (*words, *state.memory[len(words) :])
        self.load_state(replace(state, memory=memory))

    def run(self, max_steps: int) -> int:
        """Step until the machine halts or `max_steps` steps are taken; return the count."""
        steps = 0
        while steps < max_steps and self.step():
            steps += 1
        return steps

    def _fault(self) -> None:
        """Stop the machine with `Fault.BAD_ADDRESS`, changing nothing else."""
        self._halted = True
        self._halt_code = Fault.BAD_ADDRESS

    def step(self) -> bool:  # noqa: C901, PLR0912, PLR0915
        """Fetch and obey one instruction; return False if the machine had already halted."""
        if self._halted:
            return False
        pc = self._pc
        if pc >= self.words:
            self._fault()  # a fetch fault leaves pc on the bad address
            return True
        instruction = decode(self._memory[pc])
        self._pc = (pc + 1) & WORD_MASK
        regs, memory = self._registers, self._memory
        rd, ra, rb, imm = instruction.rd, instruction.ra, instruction.rb, instruction.imm
        match instruction.opcode:
            case Opcode.ALU:
                result, self._flags = alu_model(regs[ra], regs[rb], AluOp(instruction.fn))
                regs[rd] = result
            case Opcode.CMP:
                _, self._flags = alu_model(regs[ra], regs[rb], AluOp.SUB)
            case Opcode.LI:
                regs[rd] = imm
            case Opcode.LHI:
                regs[rd] = (imm << BYTE_BITS) | (regs[rd] & BYTE_MASK)
            case Opcode.LOAD:
                address = (regs[ra] + imm) & WORD_MASK
                if address >= self.words:
                    self._fault()
                else:
                    regs[rd] = memory[address]
            case Opcode.STORE:
                address = (regs[ra] + imm) & WORD_MASK
                if address < self.words:
                    memory[address] = regs[rd]
                elif address == OUTPUT_PORT:
                    self._output.append(regs[rd])
                else:
                    self._fault()
            case Opcode.JMP:
                self._pc = imm
            case Opcode.CALL:
                address = (self._sp - 1) & WORD_MASK
                if address >= self.words:
                    self._fault()
                else:
                    memory[address] = self._pc
                    self._sp = address
                    self._pc = imm
            case Opcode.BR:
                if condition_holds(Condition(rd), self._flags):  # rd holds the condition
                    self._pc = (self._pc + imm) & WORD_MASK
            case Opcode.RET:
                if self._sp >= self.words:
                    self._fault()
                else:
                    self._pc = memory[self._sp]
                    self._sp = (self._sp + 1) & WORD_MASK
            case Opcode.PUSH:
                address = (self._sp - 1) & WORD_MASK
                if address >= self.words:
                    self._fault()
                else:
                    memory[address] = regs[rd]
                    self._sp = address
            case Opcode.POP:
                if self._sp >= self.words:
                    self._fault()
                else:
                    regs[rd] = memory[self._sp]
                    self._sp = (self._sp + 1) & WORD_MASK
            case Opcode.GETSP:
                regs[rd] = self._sp
            case Opcode.SETSP:
                self._sp = regs[rd]
            case Opcode.ADDI:
                regs[rd], self._flags = alu_model(regs[rd], imm & WORD_MASK, AluOp.ADD)
            case Opcode.HALT:
                self._halted = True
                self._halt_code = imm
        return True


def _validate(state: MachineState, words: int) -> None:
    """Raise a ValueError unless `state` is a state a machine of `words` words could hold."""
    if len(state.memory) != words:
        msg = f"memory has {len(state.memory)} words, but this machine has {words}"
        raise ValueError(msg)
    if len(state.registers) != REGISTER_COUNT:
        msg = f"there must be {REGISTER_COUNT} registers, not {len(state.registers)}"
        raise ValueError(msg)
    numbers = {
        "pc": [state.pc],
        "sp": [state.sp],
        "halt code": [state.halt_code],
        "register": state.registers,
        "memory word": state.memory,
        "output word": state.output,
    }
    for name, values in numbers.items():
        for value in values:
            if not 0 <= value <= WORD_MASK:
                msg = f"{name} {value} is not a 16-bit number"
                raise ValueError(msg)
    for name, flag in zip(Flags._fields, state.flags, strict=True):
        if flag not in (0, 1):
            msg = f"flag {name} must be 0 or 1, not {flag}"
            raise ValueError(msg)
