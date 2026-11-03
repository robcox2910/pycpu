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

from collections.abc import Callable, Sequence

from pycpu.arithmetic import AluOp
from pycpu.isa import (
    OUTPUT_PORT,
    Condition,
    Fault,
    Instruction,
    Opcode,
    condition_holds,
    decode,
)
from pycpu.memory import RAM_WORDS, WORD_BITS
from pycpu.state import (
    BYTE_MASK,
    WORD_MASK,
    Flags,
    MachineState,
    power_on,
    program_state,
    validate_state,
)

SIGN_BIT = 1 << (WORD_BITS - 1)
BYTE_BITS = 8


def alu_model(a: int, b: int, op: AluOp) -> tuple[int, Flags]:
    """Work out what the gate ALU would give, using plain integers.

    Return the 16-bit result and the four flags, matching `pycpu.arithmetic.alu`
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
                `sp` or output word is outside 0-65535, or `halt_code` is outside
                0-255, or a flag is not 0 or 1. The machine is left unchanged.

        """
        validate_state(state, self.words)
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
        self.load_state(program_state(words, self.words))

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

    def step(self) -> bool:
        """Fetch and obey one instruction; return False if the machine had already halted."""
        if self._halted:
            return False
        pc = self._pc
        if pc >= self.words:
            self._fault()  # a fetch fault leaves pc on the bad address
            return True
        instruction = decode(self._memory[pc])
        self._pc = (pc + 1) & WORD_MASK
        self._handlers()[instruction.opcode](instruction)
        return True

    def _handlers(self) -> dict[Opcode, Callable[[Instruction], None]]:
        """Map each opcode to the method that obeys it."""
        return {
            Opcode.ALU: self._alu,
            Opcode.CMP: self._cmp,
            Opcode.LI: self._li,
            Opcode.LHI: self._lhi,
            Opcode.LOAD: self._load,
            Opcode.STORE: self._store,
            Opcode.JMP: self._jmp,
            Opcode.CALL: self._call,
            Opcode.BR: self._br,
            Opcode.RET: self._ret,
            Opcode.PUSH: self._push,
            Opcode.POP: self._pop,
            Opcode.GETSP: self._getsp,
            Opcode.SETSP: self._setsp,
            Opcode.ADDI: self._addi,
            Opcode.HALT: self._halt,
        }

    def _alu(self, i: Instruction) -> None:
        """Obey `ALU`: `rd = ra <fn> rb`, setting the flags."""
        result, self._flags = alu_model(self._registers[i.ra], self._registers[i.rb], AluOp(i.fn))
        self._registers[i.rd] = result

    def _cmp(self, i: Instruction) -> None:
        """Obey `CMP`: set the flags from `ra - rb` and keep no answer."""
        _, self._flags = alu_model(self._registers[i.ra], self._registers[i.rb], AluOp.SUB)

    def _li(self, i: Instruction) -> None:
        """Obey `LI`: put the immediate in `rd`."""
        self._registers[i.rd] = i.imm

    def _lhi(self, i: Instruction) -> None:
        """Obey `LHI`: put the immediate in the high byte of `rd`, keeping the low byte."""
        self._registers[i.rd] = (i.imm << BYTE_BITS) | (self._registers[i.rd] & BYTE_MASK)

    def _load(self, i: Instruction) -> None:
        """Obey `LOAD`: `rd = mem[ra + off6]`, a fault outside RAM."""
        address = (self._registers[i.ra] + i.imm) & WORD_MASK
        if address >= self.words:
            self._fault()
        else:
            self._registers[i.rd] = self._memory[address]

    def _store(self, i: Instruction) -> None:
        """Obey `STORE`: `mem[ra + off6] = rd`, or send it to the output port."""
        address = (self._registers[i.ra] + i.imm) & WORD_MASK
        if address < self.words:
            self._memory[address] = self._registers[i.rd]
        elif address == OUTPUT_PORT:
            self._output.append(self._registers[i.rd])
        else:
            self._fault()

    def _jmp(self, i: Instruction) -> None:
        """Obey `JMP`: go to the address (a bad one faults at the next fetch)."""
        self._pc = i.imm

    def _push_word(self, value: int) -> bool:
        """Push `value` on the stack; return False after a fault, with nothing changed."""
        address = (self._sp - 1) & WORD_MASK
        if address >= self.words:
            self._fault()
            return False
        self._memory[address] = value
        self._sp = address
        return True

    def _call(self, i: Instruction) -> None:
        """Obey `CALL`: push the return address, then jump."""
        if self._push_word(self._pc):
            self._pc = i.imm

    def _br(self, i: Instruction) -> None:
        """Obey `BR`: jump by the offset if the condition (held in `rd`) is true."""
        if condition_holds(Condition(i.rd), self._flags):
            self._pc = (self._pc + i.imm) & WORD_MASK

    def _pop_word(self) -> int | None:
        """Pop a word off the stack; return None after a fault, with nothing changed."""
        if self._sp >= self.words:
            self._fault()
            return None
        value = self._memory[self._sp]
        self._sp = (self._sp + 1) & WORD_MASK
        return value

    def _ret(self, _i: Instruction) -> None:
        """Obey `RET`: pop the return address into `pc`."""
        value = self._pop_word()
        if value is not None:
            self._pc = value

    def _push(self, i: Instruction) -> None:
        """Obey `PUSH`: put `rd` on the stack."""
        self._push_word(self._registers[i.rd])

    def _pop(self, i: Instruction) -> None:
        """Obey `POP`: take the top of the stack into `rd`."""
        value = self._pop_word()
        if value is not None:
            self._registers[i.rd] = value

    def _getsp(self, i: Instruction) -> None:
        """Obey `GETSP`: copy the stack pointer into `rd`."""
        self._registers[i.rd] = self._sp

    def _setsp(self, i: Instruction) -> None:
        """Obey `SETSP`: copy `rd` into the stack pointer."""
        self._sp = self._registers[i.rd]

    def _addi(self, i: Instruction) -> None:
        """Obey `ADDI`: add the signed immediate to `rd`, setting the flags."""
        self._registers[i.rd], self._flags = alu_model(
            self._registers[i.rd], i.imm & WORD_MASK, AluOp.ADD
        )

    def _halt(self, i: Instruction) -> None:
        """Obey `HALT`: stop with the immediate as the halt code."""
        self._halted = True
        self._halt_code = i.imm
