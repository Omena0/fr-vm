
# Init
MEM_SIZE  = 16 * 1024 # 16 kb
REG_COUNT = 16

# Context
PC_INIT = 0
SP_INIT = MEM_SIZE - 1024 # 1 kb

# Architecture
WORD_BITS = 32
WORD_SIZE = WORD_BITS // 8
WORD_MAX = (1 << WORD_BITS) - 1

# Flags
IE = 1 << 4  # Interrupt Enable (bit 4)

# Opcodes
OPCODE_BITS = 8
OPCODE_SIZE = OPCODE_BITS // 8
OPCODE_MAX = (1 << OPCODE_BITS) - 1

