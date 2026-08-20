import sys
import select

from encoding import decode_instruction, OPCODES, OperandType
from dataclasses import dataclass, field
from arch import *
from mmio import (
    MMIO_BASE,
    CONSOLE_DATA,
    CONSOLE_STATUS,
    CONSOLE_CONTROL,
    KEYBOARD_DATA,
    KEYBOARD_STATUS,
    KEYBOARD_CONTROL,
    TIMER_VALUE,
    TIMER_RELOAD,
    TIMER_CONTROL,
    TIMER_STATUS,
    INTERRUPT_PENDING,
    INTERRUPT_MASK,
    INTERRUPT_EOI,
    INTERRUPT_VECTOR_BASE,
    INTERRUPT_STATUS,
    SYSCALL_VECTOR_BASE,
    PROC_CREATE,
    PROC_CREATED,
    PROC_DELETE,
    PROC_SWITCH,
    PROC_TARGET_PID,
    PROC_REG_INDEX,
    PROC_REG_VALUE,
    PROC_SP,
    PROC_PC,
    PROC_FLAGS,
    PROC_MEM_ADDR,
    PROC_MEM_BYTE,
    PROC_MEM_WORD,
    SYSTEM_VERSION,
    SYSTEM_MEMORY_SIZE,
    SYSTEM_CURRENT_PID,
    SYSTEM_PRIVILEGE,
    SYSTEM_CONTROL,
    SYSTEM_STATUS,
    HWRAND,
    Interrupt,
)

def wrap(n: int, bits: int):
    return n & ((1 << bits) - 1) # Same as n % (2**bits)

def signed(n: int, bits: int) -> int:
    n = wrap(n, bits)
    return n - (1 << bits) if n & (1 << (bits - 1)) else n

def rotate_left(x, n):
    return ((x << n) | (x >> (64 - n))) & 0xFFFFFFFFFFFFFFFF

def privileged(func):
    def wrap(self, *args, **kwargs):
        if not self.pid == 0:
            raise PermissionError(f'Privileged function {func.__name__} executed as PID {self.pid}')
        return func(self, *args, **kwargs)
    return wrap

class Sigill(Exception): ...

@dataclass(slots=True)
class Flags:
    zero:  bool = False
    sign:  bool = False
    carry: bool = False
    overflow: bool = False
    interrupt_enable: bool = True

@dataclass(slots=True)
class Context:
    memory: bytearray = field(
        default_factory = lambda: bytearray(MEM_SIZE)
    )
    registers: list[int] = field(
        default_factory = lambda: [0] * REG_COUNT
    )
    pc: int      = PC_INIT
    sp: int      = SP_INIT
    flags: Flags = field(default_factory=Flags)
    pid: int     = 0

class VMState:
    def __init__(self):
        # Context
        self.contexts = {}

        self.ctx: Context = None # type: ignore

        # MMIO state
        self._console_input: list[int] = []
        self._keyboard_input: list[int] = []
        self._timer_value: int = 0
        self._timer_reload: int = 0
        self._timer_control: int = 0
        self._timer_status: int = 0
        self._interrupt_pending: int = 0
        self._interrupt_mask: int = 0
        self._interrupt_vector_base: int = 0
        self._interrupt_status: int = 0

        self._syscall_vector_base: int = 0
        self._return_context: Context | None = None

        # Extension state
        self._ext_write_map: dict[int, tuple] = {}
        self._ext_read_map: dict[int, object] = {}

        # MMIO Process management state
        self._proc_created: int = 0
        self._proc_target_pid: int = 0
        self._proc_reg_index: int = 0
        self._proc_mem_addr: int = 0

        self.hwrand = 75518
        self.instruction_counter = 0
        self._trace = False

    # Context management
    def swap_context(self, pid:int) -> int | None:
        if pid not in self.contexts:
            raise ValueError(f'PID {pid} does not exist')

        old_pid = None
        if self.ctx:
            old_pid = self.pid

        self.ctx = self.contexts[pid]

        return old_pid

    def create_context(self) -> Context:
        # Find first free PID
        pid = 0
        while pid in self.contexts:
            pid += 1

        context = Context(pid=pid)
        self.contexts[pid] = context

        return context

    def delete_context(self, pid: int):
        if pid not in self.contexts:
            raise ValueError(f"PID {pid} does not exist")

        # Delete context
        self.contexts.pop(pid)

    # Process managmenet
    def load_program(self, program: bytearray) -> Context:
        if len(program) > MEM_SIZE:
            raise MemoryError(
                f"program is too large: {len(program)} bytes "
                f"(maximum {MEM_SIZE})"
            )

        # Create process
        ctx = self.create_context()

        # Load memory
        ctx.memory[:len(program)] = program

        return ctx

    # Hardware memory management
    def _check_memory(self, address: int, size: int = 1):
        if address < 0:
            raise MemoryError(f"negative address: {address:#x}")

        if address + size > MEM_SIZE:
            raise MemoryError(
                f"address range {address:#x}..{address + size - 1:#x} "
                "is out of bounds"
            )

    # Read/write primitives
    def _read(self, address: int, size: int) -> int:
        self._check_memory(address, size)

        if address >= MMIO_BASE:
            return self._mmio_read(address, size)

        return int.from_bytes(
            self.ctx.memory[address:address + size],
            "little",
        )

    def _fetch(self, address: int, size: int) -> int:
        self._check_memory(address, size)

        return int.from_bytes(
            self.ctx.memory[address:address + size],
            "little",
        )

    def _write(self, address: int, value: int, size: int):
        self._check_memory(address, size)

        if address >= MMIO_BASE:
            self._mmio_write(address, value, size)
            return

        value = wrap(value, size * 8)

        self.ctx.memory[address:address + size] = value.to_bytes(
            size,
            "little",
        )

    def _mmio_write(self, address: int, value: int, size: int):
        if self.pid != 0:
            raise PermissionError(
                f"MMIO write at {address:#x} denied for PID {self.pid}"
            )

        offset = address - MMIO_BASE
        value = wrap(value, size * 8)

        if offset == CONSOLE_DATA.offset:
            for i in range(size):
                char = (value >> (i * 8)) & 0xFF
                if char == 10:
                    print(flush=True)
                elif char >= 32:
                    print(chr(char), end='', flush=True)

        elif offset == CONSOLE_STATUS.offset:
            pass
        elif offset == CONSOLE_CONTROL.offset:
            pass
        elif offset == KEYBOARD_DATA.offset:
            pass
        elif offset == KEYBOARD_STATUS.offset:
            pass
        elif offset == KEYBOARD_CONTROL.offset:
            pass
        elif offset == TIMER_VALUE.offset:
            self._timer_value = wrap(value, 32)
        elif offset == TIMER_RELOAD.offset:
            self._timer_reload = wrap(value, 32)
        elif offset == TIMER_CONTROL.offset:
            self._timer_control = wrap(value, 8)
            if self._timer_control & 1:
                self._timer_value = self._timer_reload
                self._timer_status = 0
        elif offset == TIMER_STATUS.offset:
            self._timer_status = wrap(value, 8) & 1
        elif offset == INTERRUPT_PENDING.offset:
            self._interrupt_pending = wrap(value, 32)
        elif offset == INTERRUPT_MASK.offset:
            self._interrupt_mask = wrap(value, 32)
        elif offset == INTERRUPT_EOI.offset:
            self._interrupt_pending = 0
            self._interrupt_status = 0
        elif offset == INTERRUPT_VECTOR_BASE.offset:
            self._interrupt_vector_base = wrap(value, 32)
        elif offset == SYSCALL_VECTOR_BASE.offset:
            self._syscall_vector_base = wrap(value, 32)
        elif offset == INTERRUPT_STATUS.offset:
            self._interrupt_status = wrap(value, 8)
        elif offset == SYSTEM_PRIVILEGE.offset:
            pass
        elif offset == SYSTEM_CONTROL.offset:
            pass
        elif offset == SYSTEM_STATUS.offset:
            pass

        # --- Process management ---
        elif offset == PROC_CREATE.offset:
            new_ctx = self.create_context()
            self._proc_created = new_ctx.pid

        elif offset == PROC_DELETE.offset:
            self.delete_context(value)

        elif offset == PROC_SWITCH.offset:
            self.swap_context(value)

        elif offset == PROC_TARGET_PID.offset:
            self._proc_target_pid = value

        elif offset == PROC_REG_INDEX.offset:
            self._proc_reg_index = wrap(value, 8)

        elif offset == PROC_REG_VALUE.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                ctx.registers[self._proc_reg_index] = wrap(value, 32)

        elif offset == PROC_SP.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                ctx.sp = wrap(value, 32)

        elif offset == PROC_PC.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                ctx.pc = wrap(value, 32)

        elif offset == PROC_FLAGS.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                ctx.flags = Flags(
                    zero=bool(value & 1),
                    sign=bool(value & 2),
                    carry=bool(value & 4),
                    overflow=bool(value & 8),
                    interrupt_enable=bool(value & 16),
                )

        # --- Process memory ---
        elif offset == PROC_MEM_ADDR.offset:
            self._proc_mem_addr = wrap(value, 32)

        elif offset == PROC_MEM_BYTE.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                addr = wrap(self._proc_mem_addr, 32)
                ctx.memory[addr:addr + 1] = bytes([value & 0xFF])
                self._proc_mem_addr = wrap(addr + 1, 32)

        elif offset == PROC_MEM_WORD.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                addr = wrap(self._proc_mem_addr, 32)
                ctx.memory[addr:addr + 4] = wrap(value, 32).to_bytes(4, "little")
                self._proc_mem_addr = wrap(addr + 4, 32)

        # --- Extension MMIO ---
        if address in self._ext_write_map:
            func, arg_index = self._ext_write_map[address]
            func.arg_values[arg_index] = wrap(value, 32)
            if arg_index == len(func.args) - 1:
                func.result = func.func(*func.arg_values)

    def _mmio_read(self, address: int, size: int) -> int:
        offset = address - MMIO_BASE

        if offset == CONSOLE_DATA.offset:
            if self._console_input:
                return self._console_input.pop(0)
            return 0
        elif offset == CONSOLE_STATUS.offset:
            return 1 if self._console_input else 0
        elif offset == CONSOLE_CONTROL.offset:
            return 0
        elif offset == KEYBOARD_DATA.offset:
            if self._keyboard_input:
                return self._keyboard_input.pop(0)
            return 0
        elif offset == KEYBOARD_STATUS.offset:
            return 1 if self._keyboard_input else 0
        elif offset == KEYBOARD_CONTROL.offset:
            return 0
        elif offset == TIMER_VALUE.offset:
            return self._timer_value
        elif offset == TIMER_RELOAD.offset:
            return self._timer_reload
        elif offset == TIMER_CONTROL.offset:
            return self._timer_control
        elif offset == TIMER_STATUS.offset:
            return self._timer_status
        elif offset == INTERRUPT_PENDING.offset:
            return self._interrupt_pending
        elif offset == INTERRUPT_MASK.offset:
            return self._interrupt_mask
        elif offset == INTERRUPT_EOI.offset:
            return 0
        elif offset == INTERRUPT_VECTOR_BASE.offset:
            return self._interrupt_vector_base
        elif offset == SYSCALL_VECTOR_BASE.offset:
            return self._syscall_vector_base
        elif offset == INTERRUPT_STATUS.offset:
            return self._interrupt_status
        elif offset == SYSTEM_VERSION.offset:
            return 1
        elif offset == SYSTEM_MEMORY_SIZE.offset:
            return MEM_SIZE
        elif offset == SYSTEM_CURRENT_PID.offset:
            return self.pid
        elif offset == SYSTEM_PRIVILEGE.offset:
            return 0 if self.pid == 0 else 1
        elif offset == SYSTEM_CONTROL.offset:
            return 0
        elif offset == SYSTEM_STATUS.offset:
            return 0

        # --- Process management ---
        elif offset == PROC_CREATED.offset:
            return self._proc_created

        elif offset == PROC_REG_VALUE.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                return ctx.registers[self._proc_reg_index]
            return 0

        elif offset == PROC_SP.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            return ctx.sp if ctx else 0

        elif offset == PROC_PC.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            return ctx.pc if ctx else 0

        elif offset == PROC_FLAGS.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is None:
                return 0
            return (
                (1 if ctx.flags.zero else 0) |
                (2 if ctx.flags.sign else 0) |
                (4 if ctx.flags.carry else 0) |
                (8 if ctx.flags.overflow else 0) |
                (16 if ctx.flags.interrupt_enable else 0)
            )

        # --- Process memory ---
        elif offset == PROC_MEM_BYTE.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                addr = wrap(self._proc_mem_addr, 32)
                result = ctx.memory[addr]
                self._proc_mem_addr = wrap(addr + 1, 32)
                return result
            return 0

        elif offset == PROC_MEM_WORD.offset:
            ctx = self.contexts.get(self._proc_target_pid)
            if ctx is not None:
                addr = wrap(self._proc_mem_addr, 32)
                result = int.from_bytes(
                    ctx.memory[addr:addr + 4], "little"
                )
                self._proc_mem_addr = wrap(addr + 4, 32)
                return result
            return 0

        elif HWRAND.offset <= offset < HWRAND.offset + HWRAND.size:
            byte_index = offset - HWRAND.offset
            return (self.hwrand >> (byte_index * 8)) & 0xFF

        # --- Extension MMIO ---
        if address in self._ext_read_map:
            func = self._ext_read_map[address]
            if len(func.args) == 0:
                func.result = func.func()
            return wrap(func.result, size * 8)

        return 0

    def _poll_input(self):
        if not sys.stdin.isatty():
            return

        if not select.select([sys.stdin], [], [], 0)[0]:
            return

        try:
            char = sys.stdin.read(1)
        except Exception:
            return

        if not char:
            return

        code = ord(char)
        self._console_input.append(code)
        self._keyboard_input.append(code)

        if self._interrupt_mask & (1 << Interrupt.KEYBOARD):
            self._interrupt_pending |= (1 << Interrupt.KEYBOARD)
            self._interrupt_status = 1

    def _tick_timer(self):
        if not (self._timer_control & 1):
            return

        if self._timer_value > 0:
            self._timer_value -= 1

        if self._timer_value == 0:
            self._timer_status = 1
            self._timer_value = self._timer_reload

            if self._interrupt_mask & (1 << Interrupt.TIMER):
                self._interrupt_pending |= (1 << Interrupt.TIMER)
                self._interrupt_status = 1

    # Utility aliases
    def read8(self, address: int) -> int:
        return self._read(address, 1)
    def read16(self, address: int) -> int:
        return self._read(address, 2)
    def read32(self, address: int) -> int:
        return self._read(address, 4)
    def read64(self, address: int) -> int:
        return self._read(address, 8)

    def write8(self, address: int, value: int):
        self._write(address, value, 1)
    def write16(self, address: int, value: int):
        self._write(address, value, 2)
    def write32(self, address: int, value: int):
        self._write(address, value, 4)
    def write64(self, address: int, value: int):
        self._write(address, value, 8)

    def fetch8(self, address: int) -> int:
        return self._fetch(address, 1)
    def fetch16(self, address: int) -> int:
        return self._fetch(address, 2)
    def fetch32(self, address: int) -> int:
        return self._fetch(address, 4)
    def fetch64(self, address: int) -> int:
        return self._fetch(address, 8)

    # Registers
    @property
    def registers(self) -> tuple[int, ...]:
        return tuple(self.ctx.registers)

    def get_register(self, index: int) -> int:
        self._check_register(index)
        return self.ctx.registers[index]

    def set_register(self, index: int, value: int):
        self._check_register(index)

        if not isinstance(value, int):
            raise TypeError("register value must be an integer")

        self.ctx.registers[index] = wrap(value, WORD_BITS)

    def _check_register(self, index: int):
        if not isinstance(index, int):
            raise TypeError("register index must be an integer")

        if not 0 <= index < REG_COUNT:
            raise IndexError(f"register index out of range: {index}")

    # Program Counter
    @property
    def pc(self) -> int:
        return self.ctx.pc

    @pc.setter
    def pc(self, value: int):
        if not isinstance(value, int):
            raise TypeError("pc must be an integer")
        self.ctx.pc = wrap(value, WORD_BITS)

    # Stack pointer
    @property
    def sp(self) -> int:
        return self.ctx.sp

    @sp.setter
    def sp(self, value: int):
        if not isinstance(value, int):
            raise TypeError("sp must be an integer")
        self.ctx.sp = wrap(value, WORD_BITS)

    # Flags
    @property
    def flags(self):
        return self.ctx.flags

    @flags.setter
    def flags(self, value):
        if not isinstance(value, Flags):
            raise ValueError('Value is not Flags')
        self.ctx.flags = value

    # Process ID
    @property
    def pid(self):
        return self.ctx.pid

class VirtualMachine(VMState):
    def __init__(self):
        self._running = False

        super().__init__()

    def load_kernel(self, kernel: bytearray):
        self.load_program(kernel)
        self.swap_context(0)
        self.flags.interrupt_enable = False

    def load_extensions(self, source: str):
        from extension import ExtensionLoader

        loader = ExtensionLoader()
        loader.load(source)

        self._ext_write_map = loader.write_map
        self._ext_read_map = loader.read_map

    def _enter_kernel_mode(self, vector: int, is_syscall: bool):
        self._return_context = self.ctx
        self.contexts[0].registers = list(self.ctx.registers)
        self.swap_context(0)
        self.flags.interrupt_enable = False

        base = (
            self._syscall_vector_base
            if is_syscall
            else self._interrupt_vector_base
        )
        if base == 0:
            raise Sigill('vector base not set')
        handler = self.read32(base + vector * 4)
        if handler == 0:
            raise Sigill(f'no handler for vector {vector}')
        self.pc = handler

    def _exit_kernel_mode(self):
        if self._return_context is None:
            raise ValueError('Return context is None')

        self._return_context.registers = list(self.ctx.registers)
        user_pid = self._return_context.pid
        self.swap_context(user_pid)
        self._return_context = None

    def _deliver_pending_interrupt(self) -> bool:
        if self.pid == 0:
            return False
        if not self.flags.interrupt_enable:
            return False

        active = self._interrupt_pending & self._interrupt_mask
        if not active:
            return False

        vector = (active & -active).bit_length() - 1

        base = self._interrupt_vector_base
        if base == 0:
            return False

        kernel = self.contexts[0]
        handler_bytes = kernel.memory[
            base + vector * 4 : base + vector * 4 + 4
        ]
        if int.from_bytes(handler_bytes, 'little') == 0:
            return False

        self._interrupt_pending &= ~(1 << vector)
        self._interrupt_status = 1

        self._enter_kernel_mode(vector, is_syscall=False)
        return True

    def _update_flags(self, result: int, left: int, right: int, is_add: bool):
        self.flags.zero = result == 0
        self.flags.sign = bool(result & (1 << (WORD_BITS - 1)))

        if is_add:
            self.flags.carry = (wrap(left, WORD_BITS) + wrap(right, WORD_BITS)) > WORD_MAX
            self.flags.overflow = bool(
                ~(left ^ right) & (left ^ result) & (1 << (WORD_BITS - 1))
            )
        else:
            self.flags.carry = wrap(left, WORD_BITS) < wrap(right, WORD_BITS)
            self.flags.overflow = bool(
                (left ^ right) & (left ^ result) & (1 << (WORD_BITS - 1))
            )

    def fetch_instruction(self):
        opcode = self.fetch8(self.pc)

        if opcode not in OPCODES:
            raise ValueError(
                f"unknown opcode: {opcode:#04x}"
            )

        instruction = OPCODES[opcode]
        total_size = instruction.size

        data = bytearray()

        for index in range(total_size):
            data.append(
                self.fetch8(self.pc + index)
            )

        _, operands, end_offset = decode_instruction(
            bytes(data),
            0,
        )

        self.pc += end_offset

        return instruction, operands

    def step(self):
        self._poll_input()
        self._tick_timer()

        if self._deliver_pending_interrupt():
            return

        self.instruction_counter += 1

        if self._trace:
            pc_before = self.pc
            regs_before = list(self.registers)

        instruction, operands = self.fetch_instruction()
        name = instruction.name

        state = self.hwrand
        state ^= instruction.opcode
        state ^= self.instruction_counter
        state = rotate_left(state, 17)
        state *= 0x9E3779B97F4A7C15
        state ^= state >> 32
        state = wrap(state, 64)
        self.hwrand = state

        if self._trace:
            BOLD = '\033[1m'
            DIM = '\033[2m'
            ITALIC = '\033[3m'
            UNDERLINE = '\033[4m'
            color = '\033[94m' if self.pid == 0 else '\033[92m'
            reset = '\033[0m'
            cyan = '\033[96m'
            op_strs = []
            for op_type, op_val in zip(instruction.operands, operands):
                if op_type == OperandType.REGISTER:
                    op_strs.append(f'r{op_val}')
                elif op_type == OperandType.SYSCALL:
                    op_strs.append(str(op_val))
                else:
                    op_strs.append(str(op_val))
            ops = f' {", ".join(op_strs)}' if op_strs else ''
            print(
                f'{color}{BOLD}[{self.instruction_counter:5d}]{reset} '
                f'{color}{ITALIC}PID={self.pid}{reset} '
                f'{DIM}PC=0x{pc_before:04x}{reset} '
                f'{color}{BOLD}{UNDERLINE}{name}{reset}{color}{ops}{reset}',
                flush=True,
            )

        try:
            match name:
                case 'SYSCALL':
                    self._enter_kernel_mode(operands[0], is_syscall=True)
                case 'IRET':
                    self._exit_kernel_mode()
                case 'ENABLE_INT':
                    if self.pid != 0:
                        raise PermissionError(
                            f'ENABLE_INT executed as PID {self.pid}'
                        )
                    self.flags.interrupt_enable = True
                case 'DISABLE_INT':
                    if self.pid != 0:
                        raise PermissionError(
                            f'DISABLE_INT executed as PID {self.pid}'
                        )
                    self.flags.interrupt_enable = False
                case 'NOP':
                    pass
                case 'MOVE':
                    self.set_register(operands[0], self.get_register(operands[1]))
                case 'PUSH':
                    self.sp -= 4
                    value = self.get_register(operands[0])
                    self.write32(self.sp, value)
                case 'SUB_SP':
                    self.sp -= operands[0]
                case 'LOAD_SP':
                    self.set_register(operands[0], self.sp)
                case 'STORE_SP':
                    self.sp = self.get_register(operands[0])
                case 'LOAD_CONST':
                    self.set_register(operands[0], operands[1])
                case 'STORE':
                    value = self.get_register(operands[2])
                    self.write32(self.get_register(operands[0]) + operands[1], value)
                case 'LOAD':
                    value = self.read32(self.get_register(operands[1]) + operands[2])
                    self.set_register(operands[0], value)
                case 'LOAD_BYTE':
                    value = self.read8(self.get_register(operands[1]) + operands[2])
                    self.set_register(operands[0], value)
                case 'STORE_BYTE':
                    value = self.get_register(operands[2])
                    self.write8(self.get_register(operands[0]) + operands[1], value)
                case 'LOAD_WORD':
                    value = self.read16(self.get_register(operands[1]) + operands[2])
                    self.set_register(operands[0], value)
                case 'STORE_WORD':
                    value = self.get_register(operands[2])
                    self.write16(self.get_register(operands[0]) + operands[1], value)
                case 'LOAD_DWORD':
                    value = self.read32(self.get_register(operands[1]) + operands[2])
                    self.set_register(operands[0], value)
                case 'STORE_DWORD':
                    value = self.get_register(operands[2])
                    self.write32(self.get_register(operands[0]) + operands[1], value)
                case 'LOAD_QWORD':
                    value = self.read64(self.get_register(operands[1]) + operands[2])
                    self.set_register(operands[0], value)
                case 'STORE_QWORD':
                    value = self.get_register(operands[2])
                    self.write64(self.get_register(operands[0]) + operands[1], value)
                case 'CMP_EQ':
                    left = self.get_register(operands[0])
                    right = self.get_register(operands[1])
                    result = left - right
                    self._update_flags(result, left, right, is_add=False)
                    self.flags.zero = (left == right)
                case 'JZ':
                    if not self.flags.zero:
                        return
                    self.pc = operands[0]
                case 'ADDI':
                    left = self.get_register(operands[1])
                    right = operands[2]
                    result = left + right
                    self.set_register(operands[0], result)
                    self._update_flags(result, left, right, is_add=True)
                case 'JUMP':
                    self.pc = operands[0]
                case 'ADD_SP':
                    self.sp += operands[0]
                case 'POP':
                    value = self.read32(self.sp)
                    self.sp += 4
                    self.set_register(operands[0], value)
                case 'RETURN':
                    value = self.read32(self.sp)
                    self.sp += 4
                    self.pc = value
                case 'ADD':
                    left = self.get_register(operands[1])
                    right = self.get_register(operands[2])
                    result = left + right
                    self.set_register(operands[0], result)
                    self._update_flags(result, left, right, is_add=True)
                case 'SUB':
                    left = self.get_register(operands[1])
                    right = self.get_register(operands[2])
                    result = left - right
                    self.set_register(operands[0], result)
                    self._update_flags(result, left, right, is_add=False)
                case 'CMP_NE':
                    left = self.get_register(operands[0])
                    right = self.get_register(operands[1])
                    result = left - right
                    self._update_flags(result, left, right, is_add=False)
                    self.flags.zero = (left != right)
                case 'CMP_LT':
                    left = self.get_register(operands[0])
                    right = self.get_register(operands[1])
                    result = left - right
                    self._update_flags(result, left, right, is_add=False)
                    self.flags.zero = signed(left, WORD_BITS) < signed(right, WORD_BITS)
                case 'CMP_LE':
                    left = self.get_register(operands[0])
                    right = self.get_register(operands[1])
                    result = left - right
                    self._update_flags(result, left, right, is_add=False)
                    self.flags.zero = signed(left, WORD_BITS) <= signed(right, WORD_BITS)
                case 'CMP_GT':
                    left = self.get_register(operands[0])
                    right = self.get_register(operands[1])
                    result = left - right
                    self._update_flags(result, left, right, is_add=False)
                    self.flags.zero = signed(left, WORD_BITS) > signed(right, WORD_BITS)
                case 'CMP_GE':
                    left = self.get_register(operands[0])
                    right = self.get_register(operands[1])
                    result = left - right
                    self._update_flags(result, left, right, is_add=False)
                    self.flags.zero = signed(left, WORD_BITS) >= signed(right, WORD_BITS)
                case 'JNZ':
                    if self.flags.zero:
                        return
                    self.pc = operands[0]
                case 'JC':
                    if not self.flags.carry:
                        return
                    self.pc = operands[0]
                case 'JNC':
                    if self.flags.carry:
                        return
                    self.pc = operands[0]
                case 'JS':
                    if not self.flags.sign:
                        return
                    self.pc = operands[0]
                case 'JNS':
                    if self.flags.sign:
                        return
                    self.pc = operands[0]
                case 'JO':
                    if not self.flags.overflow:
                        return
                    self.pc = operands[0]
                case 'JNO':
                    if self.flags.overflow:
                        return
                    self.pc = operands[0]
                case 'HALT':
                    self._running = False
                case default:
                    raise Sigill(f'Illegal instruction: {default}')
        finally:
            if self._trace:
                BOLD = '\033[1m'
                DIM = '\033[2m'
                ITALIC = '\033[3m'
                yellow = '\033[93m'
                dim_gray = '\033[90m'
                reset = '\033[0m'
                changed = []
                for i in range(REG_COUNT):
                    old = regs_before[i]
                    new = self.get_register(i)
                    if old != new:
                        changed.append(
                            f'{yellow}{BOLD}r{i}{reset}{dim_gray}: '
                            f'{old} {BOLD}→{reset} {yellow}{new}{reset}'
                        )
                pc_str = (
                    f'{dim_gray}{ITALIC}, PC{reset}{dim_gray}: '
                    f'0x{pc_before:04x} {BOLD}→{reset} 0x{self.pc:04x}{reset}'
                )
                if changed:
                    print(
                        f'{dim_gray}  {BOLD}→{reset} {", ".join(changed)}{pc_str}',
                        flush=True,
                    )
                else:
                    print(f'{dim_gray}  {BOLD}→{pc_str}', flush=True)

    def run(self):
        self._running = True

        while self._running:
            try:
                self.step()
            except Exception as e:
                print(e)
                exit(1)

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        prog="vm",
        description="FR-Kernel virtual machine",
    )
    parser.add_argument("kernel", nargs="?", default="kernel.bin",
                        help="kernel binary file")
    parser.add_argument(
        "-e", "--extensions",
        dest="extensions",
        default=None,
        help="extension directory or file",
    )
    parser.add_argument(
        "-t", "--trace",
        dest="trace",
        action="store_true",
        default=False,
        help="trace instruction execution",
    )

    args = parser.parse_args()

    kernel = bytearray(open(args.kernel, 'rb').read())

    vm = VirtualMachine()

    if args.extensions:
        vm.load_extensions(args.extensions)

    vm.load_kernel(kernel)
    vm._trace = args.trace

    vm.run()
