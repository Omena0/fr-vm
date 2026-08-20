from dataclasses import dataclass
from enum import IntEnum, auto

from arch import MEM_SIZE


@dataclass(frozen=True, slots=True)
class MMIORegister:
    offset: int
    size: int

    @property
    def address(self) -> int:
        return MEM_SIZE - MMIO_SIZE + self.offset


class _MMIOAllocator:
    def __init__(self):
        self.offset = 0

    def auto(self, size: int = 1) -> MMIORegister:
        if size <= 0:
            raise ValueError("MMIO register size must be positive")

        register = MMIORegister(
            offset=self.offset,
            size=size,
        )

        self.offset += size

        return register

    @property
    def size(self) -> int:
        return self.offset


_mmio = _MMIOAllocator()


# ---------------------------------------------------------------------------
# Console
# ---------------------------------------------------------------------------

CONSOLE_DATA    = _mmio.auto()
CONSOLE_STATUS  = _mmio.auto()
CONSOLE_CONTROL = _mmio.auto()


# ---------------------------------------------------------------------------
# Keyboard
# ---------------------------------------------------------------------------

KEYBOARD_DATA    = _mmio.auto()
KEYBOARD_STATUS  = _mmio.auto()
KEYBOARD_CONTROL = _mmio.auto()


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------

TIMER_VALUE   = _mmio.auto(4)
TIMER_RELOAD  = _mmio.auto(4)
TIMER_CONTROL = _mmio.auto()
TIMER_STATUS  = _mmio.auto()


# ---------------------------------------------------------------------------
# Interrupt Controller
# ---------------------------------------------------------------------------

INTERRUPT_PENDING     = _mmio.auto(4)
INTERRUPT_MASK        = _mmio.auto(4)
INTERRUPT_EOI         = _mmio.auto()
INTERRUPT_VECTOR_BASE = _mmio.auto(4)
INTERRUPT_STATUS      = _mmio.auto()
SYSCALL_VECTOR_BASE   = _mmio.auto(4)


# ---------------------------------------------------------------------------
# Process management
# ---------------------------------------------------------------------------

PROC_CREATE   = _mmio.auto()
PROC_CREATED  = _mmio.auto(4)
PROC_DELETE   = _mmio.auto(4)
PROC_SWITCH   = _mmio.auto(4)
PROC_TARGET_PID = _mmio.auto(4)


# ---------------------------------------------------------------------------
# Process state (accessed via PROC_TARGET_PID)
# ---------------------------------------------------------------------------

PROC_REG_INDEX  = _mmio.auto()
PROC_REG_VALUE  = _mmio.auto(4)
PROC_SP         = _mmio.auto(4)
PROC_PC         = _mmio.auto(4)
PROC_FLAGS      = _mmio.auto(4)


# ---------------------------------------------------------------------------
# Process memory (accessed via PROC_TARGET_PID)
# ---------------------------------------------------------------------------

PROC_MEM_ADDR  = _mmio.auto(4)
PROC_MEM_BYTE  = _mmio.auto()
PROC_MEM_WORD  = _mmio.auto(4)


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

SYSTEM_VERSION     = _mmio.auto(4)
SYSTEM_MEMORY_SIZE = _mmio.auto(4)
SYSTEM_CURRENT_PID = _mmio.auto(4)
SYSTEM_PRIVILEGE   = _mmio.auto()
SYSTEM_CONTROL     = _mmio.auto()
SYSTEM_STATUS      = _mmio.auto()

HWRAND = _mmio.auto(8)


# ---------------------------------------------------------------------------
# Extension MMIO region — dynamically carved out by the extension loader
# ---------------------------------------------------------------------------

EXTENSION_REGION_SIZE = 256
_EXTENSIONS = _mmio.auto(EXTENSION_REGION_SIZE)


# Dynamically-allocated extension MMIO helpers
_extension_offset = 0


def reset_extensions():
    global _extension_offset
    _extension_offset = 0


def alloc_extension_mmio(size: int = 4) -> int:
    global _extension_offset

    if size <= 0:
        raise ValueError("extension MMIO size must be positive")

    if _extension_offset + size > EXTENSION_REGION_SIZE:
        raise ValueError(
            f"extension MMIO region exhausted "
            f"(need {size} bytes at offset {_extension_offset})"
        )

    addr = _EXTENSIONS.address + _extension_offset
    _extension_offset += size
    return addr


# ---------------------------------------------------------------------------
# MMIO occupies exactly the bytes required by the registers above.
MMIO_SIZE = _mmio.size
MMIO_BASE = MEM_SIZE - MMIO_SIZE
MMIO_END = MEM_SIZE


# ---------------------------------------------------------------------------
# System commands
# ---------------------------------------------------------------------------

class SystemCommand(IntEnum):
    RESET = auto()
    SHUTDOWN = auto()


# ---------------------------------------------------------------------------
# Interrupt numbers
# ---------------------------------------------------------------------------

class Interrupt(IntEnum):
    TIMER = auto()
    KEYBOARD = auto()
    CONSOLE = auto()


if __name__ == '__main__':
    print(MMIO_BASE)
