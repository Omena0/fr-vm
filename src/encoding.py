from dataclasses import dataclass
from enum import IntEnum, auto
from arch import *


class OperandType(IntEnum):
    REGISTER = auto()

    IMMEDIATE8 = auto()
    IMMEDIATE16 = auto()
    IMMEDIATE32 = auto()
    IMMEDIATE64 = auto()

    ADDRESS8 = auto()
    ADDRESS16 = auto()
    ADDRESS32 = auto()
    ADDRESS64 = auto()

    OFFSET8 = auto()
    OFFSET16 = auto()
    OFFSET32 = auto()
    OFFSET64 = auto()

    SYSCALL = auto()


@dataclass(frozen=True, slots=True)
class Instruction:
    opcode: int
    operands: tuple[OperandType, ...] = ()

    def __post_init__(self):
        if not 0 <= self.opcode <= OPCODE_MAX:
            raise ValueError(
                f"opcode out of range: {self.opcode:#x}"
            )

    @property
    def name(self):
        return INSTRUCTION_NAMES[self]

    @property
    def size(self):
        return OPCODE_SIZE + sum(
            operand_size(operand)
            for operand in self.operands
        )


def operand_size(operand: OperandType) -> int:
    if operand == OperandType.REGISTER:
        return 1

    if operand in (
        OperandType.IMMEDIATE8,
        OperandType.ADDRESS8,
        OperandType.OFFSET8,
    ):
        return 1

    if operand in (
        OperandType.IMMEDIATE16,
        OperandType.ADDRESS16,
        OperandType.OFFSET16,
    ):
        return 2

    if operand in (
        OperandType.IMMEDIATE32,
        OperandType.ADDRESS32,
        OperandType.OFFSET32,
        OperandType.SYSCALL,
    ):
        return 4

    if operand in (
        OperandType.IMMEDIATE64,
        OperandType.ADDRESS64,
        OperandType.OFFSET64,
    ):
        return 8

    raise ValueError(f"unknown operand type: {operand}")


def operand_signed(operand: OperandType) -> bool:
    return operand in (
        OperandType.IMMEDIATE8,
        OperandType.IMMEDIATE16,
        OperandType.IMMEDIATE32,
        OperandType.IMMEDIATE64,
        OperandType.OFFSET8,
        OperandType.OFFSET16,
        OperandType.OFFSET32,
        OperandType.OFFSET64,
    )


def operand_is_address(operand: OperandType) -> bool:
    return operand in (
        OperandType.ADDRESS8,
        OperandType.ADDRESS16,
        OperandType.ADDRESS32,
        OperandType.ADDRESS64,
    )


def operand_is_offset(operand: OperandType) -> bool:
    return operand in (
        OperandType.OFFSET8,
        OperandType.OFFSET16,
        OperandType.OFFSET32,
        OperandType.OFFSET64,
    )


# ---------------------------------------------------------------------------
# Instruction set
# ---------------------------------------------------------------------------

def _instruction(
    name: str,
    opcode: int,
    *operands: OperandType,
):
    instruction = Instruction(opcode, operands)

    if name in INSTRUCTIONS:
        raise ValueError(f"duplicate instruction: {name}")

    INSTRUCTIONS[name] = instruction
    OPCODES[opcode] = instruction
    INSTRUCTION_NAMES[instruction] = name


INSTRUCTIONS: dict[str, Instruction] = {}
OPCODES: dict[int, Instruction] = {}
INSTRUCTION_NAMES: dict[Instruction, str] = {}


# Data movement
_instruction(
    "LOAD",
    0x00,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.OFFSET32,
)

_instruction(
    "STORE",
    0x01,
    OperandType.REGISTER,
    OperandType.OFFSET32,
    OperandType.REGISTER,
)

_instruction(
    "LOAD_CONST",
    0x02,
    OperandType.REGISTER,
    OperandType.IMMEDIATE32,
)

_instruction(
    "MOVE",
    0x03,
    OperandType.REGISTER,
    OperandType.REGISTER,
)


# Integer arithmetic
_instruction(
    "ADD",
    0x10,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "SUB",
    0x11,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "MUL",
    0x12,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "DIV",
    0x13,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "MOD",
    0x14,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "NEG",
    0x15,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "ADDI",
    0x16,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.IMMEDIATE32,
)


# Logic / bitwise
_instruction(
    "AND",
    0x20,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "OR",
    0x21,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "XOR",
    0x22,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "NOT",
    0x23,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "SHL",
    0x24,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "SHR",
    0x25,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "SAR",
    0x26,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.REGISTER,
)


# Comparisons
_instruction(
    "CMP_EQ",
    0x30,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "CMP_NE",
    0x31,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "CMP_LT",
    0x32,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "CMP_LE",
    0x33,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "CMP_GT",
    0x34,
    OperandType.REGISTER,
    OperandType.REGISTER,
)

_instruction(
    "CMP_GE",
    0x35,
    OperandType.REGISTER,
    OperandType.REGISTER,
)


# Control flow
_instruction(
    "JUMP",
    0x40,
    OperandType.ADDRESS32,
)

_instruction(
    "JZ",
    0x41,
    OperandType.ADDRESS32,
)

_instruction(
    "JNZ",
    0x42,
    OperandType.ADDRESS32,
)

_instruction(
    "JC",
    0x43,
    OperandType.ADDRESS32,
)

_instruction(
    "JNC",
    0x44,
    OperandType.ADDRESS32,
)

_instruction(
    "JS",
    0x45,
    OperandType.ADDRESS32,
)

_instruction(
    "JNS",
    0x46,
    OperandType.ADDRESS32,
)

_instruction(
    "JO",
    0x47,
    OperandType.ADDRESS32,
)

_instruction(
    "JNO",
    0x48,
    OperandType.ADDRESS32,
)

_instruction(
    "CALL",
    0x49,
    OperandType.ADDRESS32,
)

_instruction(
    "RETURN",
    0x4A,
)


# Stack
_instruction(
    "PUSH",
    0x50,
    OperandType.REGISTER,
)

_instruction(
    "POP",
    0x51,
    OperandType.REGISTER,
)

_instruction(
    "LOAD_SP",
    0x52,
    OperandType.REGISTER,
)

_instruction(
    "STORE_SP",
    0x53,
    OperandType.REGISTER,
)

_instruction(
    "ADD_SP",
    0x54,
    OperandType.IMMEDIATE32,
)

_instruction(
    "SUB_SP",
    0x55,
    OperandType.IMMEDIATE32,
)


# Byte / word / dword / qword memory
_instruction(
    "LOAD_BYTE",
    0x60,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.OFFSET32,
)

_instruction(
    "STORE_BYTE",
    0x61,
    OperandType.REGISTER,
    OperandType.OFFSET32,
    OperandType.REGISTER,
)

_instruction(
    "LOAD_WORD",
    0x62,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.OFFSET32,
)

_instruction(
    "STORE_WORD",
    0x63,
    OperandType.REGISTER,
    OperandType.OFFSET32,
    OperandType.REGISTER,
)

_instruction(
    "LOAD_DWORD",
    0x64,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.OFFSET32,
)

_instruction(
    "STORE_DWORD",
    0x65,
    OperandType.REGISTER,
    OperandType.OFFSET32,
    OperandType.REGISTER,
)

_instruction(
    "LOAD_QWORD",
    0x66,
    OperandType.REGISTER,
    OperandType.REGISTER,
    OperandType.OFFSET32,
)

_instruction(
    "STORE_QWORD",
    0x67,
    OperandType.REGISTER,
    OperandType.OFFSET32,
    OperandType.REGISTER,
)


# System / privilege
_instruction(
    "SYSCALL",
    0x70,
    OperandType.SYSCALL,
)

_instruction(
    "HALT",
    0x71,
)

_instruction(
    "ENABLE_INT",
    0x72,
)

_instruction(
    "DISABLE_INT",
    0x73,
)

_instruction(
    "BREAK",
    0x74,
)

_instruction(
    "NOP",
    0x75,
)

_instruction(
    "IRET",
    0x76,
)


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------

def encode_register(register: int) -> bytes:
    if not isinstance(register, int):
        raise TypeError("register must be an integer")

    if not 0 <= register < REG_COUNT:
        raise ValueError(
            f"register out of range: {register}"
        )

    return bytes((register,))


def decode_register(data: bytes) -> int:
    if len(data) != 1:
        raise ValueError("register encoding must be one byte")

    register = data[0]

    if register >= REG_COUNT:
        raise ValueError(
            f"invalid register encoding: {register}"
        )

    return register


def encode_integer(
    value: int,
    size: int,
    signed: bool = False,
) -> bytes:
    if not isinstance(value, int):
        raise TypeError("integer operand must be an integer")

    return value.to_bytes(
        size,
        "little",
        signed=signed,
    )


def decode_integer(
    data: bytes,
    signed: bool = False,
) -> int:
    return int.from_bytes(
        data,
        "little",
        signed=signed,
    )


def encode_operand(
    operand_type: OperandType,
    value: int,
) -> bytes:
    if operand_type == OperandType.REGISTER:
        return encode_register(value)

    size = operand_size(operand_type)

    return encode_integer(
        value,
        size,
        signed=operand_signed(operand_type),
    )


def decode_operand(
    operand_type: OperandType,
    data: bytes,
) -> int:
    expected_size = operand_size(operand_type)

    if len(data) != expected_size:
        raise ValueError(
            f"expected {expected_size} bytes for "
            f"{operand_type.name}, got {len(data)}"
        )

    if operand_type == OperandType.REGISTER:
        return decode_register(data)

    return decode_integer(
        data,
        signed=operand_signed(operand_type),
    )


def encode_instruction(
    instruction: Instruction,
    operands: tuple[int, ...],
) -> bytes:
    if len(operands) != len(instruction.operands):
        raise ValueError(
            f"{instruction.name} expects "
            f"{len(instruction.operands)} operands, "
            f"got {len(operands)}"
        )

    encoded = bytearray()
    encoded.append(instruction.opcode)

    for operand_type, value in zip(
        instruction.operands,
        operands,
    ):
        encoded.extend(
            encode_operand(
                operand_type,
                value,
            )
        )

    return bytes(encoded)


def decode_instruction(
    data: bytes,
    offset: int = 0,
) -> tuple[Instruction, tuple[int, ...], int]:
    if offset < 0 or offset >= len(data):
        raise ValueError("instruction offset out of range")

    opcode = data[offset]

    if opcode not in OPCODES:
        raise ValueError(
            f"unknown opcode: {opcode:#04x}"
        )

    instruction = OPCODES[opcode]
    cursor = offset + OPCODE_SIZE
    operands = []

    for operand_type in instruction.operands:
        size = operand_size(operand_type)

        end = cursor + size

        if end > len(data):
            raise ValueError(
                f"truncated {instruction.name} instruction"
            )

        operands.append(
            decode_operand(
                operand_type,
                data[cursor:end],
            )
        )

        cursor = end

    return (
        instruction,
        tuple(operands),
        cursor,
    )
