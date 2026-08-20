import re
import shlex
import sys
from dataclasses import dataclass, field
import argparse

from syscalls import (
    SYS_PRINT,
    SYS_PRINTLN,
    SYS_INPUT,
    SYS_STORE_GLOBAL,
    SYS_LOAD_GLOBAL,
    SYS_RAISE,
    SYS_TRY_BEGIN,
    SYS_TRY_END,
)


WORD_SIZE = 4
WORD_BITS = 32

GENERAL_REGISTERS = [f"r{i}" for i in range(15)]
FRAME_REGISTER = "r15"

ARGUMENT_REGISTERS = [
    "r0",
    "r1",
    "r2",
    "r3",
    "r4",
    "r5",
    "r6",
    "r7",
    "r8",
    "r9",
    "r10",
    "r11",
    "r12",
    "r13",
    "r14",
]


class CompileError(Exception):
    pass


@dataclass(slots=True)
class SSAInstruction:
    result: str | None
    opcode: str
    operands: list[str]
    line: int


@dataclass(slots=True)
class BasicBlock:
    name: str
    instructions: list[SSAInstruction] = field(
        default_factory=list
    )


@dataclass(slots=True)
class Function:
    name: str
    return_type: str
    arguments: list[tuple[str, str]]
    blocks: list[BasicBlock] = field(
        default_factory=list
    )


@dataclass(slots=True)
class ValueInfo:
    name: str
    value_type: str
    size: int


@dataclass(slots=True)
class Slot:
    offset: int
    size: int


@dataclass(slots=True)
class Phi:
    result: str
    incoming: dict[str, str]


class SSAParser:
    FUNCTION_RE = re.compile(
        r"function\s+(\S+)\s+@([A-Za-z_.$][A-Za-z0-9_.$]*)"
        r"\((.*?)\)\s*\{"
    )

    RESULT_RE = re.compile(
        r"^(%[A-Za-z0-9_][A-Za-z0-9_.$]*)\s*=\s*(.*)$"
    )

    LABEL_RE = re.compile(
        r"^([A-Za-z_.$][A-Za-z0-9_.$]*):"
    )

    def parse(self, source: str) -> list[Function]:
        lines = source.splitlines()
        functions = []

        index = 0

        while index < len(lines):
            line = self._strip_comment(lines[index]).strip()

            if not line:
                index += 1
                continue

            if line.startswith(";"):
                index += 1
                continue

            if line.startswith("function "):
                function, index = self._parse_function(
                    lines,
                    index,
                )
                functions.append(function)
                continue

            index += 1

        if not functions:
            raise CompileError("no functions found")

        return functions

    def _parse_function(
        self,
        lines: list[str],
        start: int,
    ) -> tuple[Function, int]:
        line = self._strip_comment(lines[start]).strip()

        match = self.FUNCTION_RE.match(line)

        if not match:
            raise CompileError(
                f"line {start + 1}: invalid function declaration"
            )

        return_type = match.group(1)
        name = match.group(2)
        argument_text = match.group(3).strip()

        arguments = []

        if argument_text:
            for argument in self._split_arguments(
                argument_text
            ):
                parts = argument.split()

                if len(parts) != 2:
                    raise CompileError(
                        f"line {start + 1}: invalid argument: "
                        f"{argument}"
                    )

                arg_type, arg_name = parts

                arguments.append(
                    (arg_name, arg_type)
                )

        function = Function(
            name=name,
            return_type=return_type,
            arguments=arguments,
        )

        current_block = None
        index = start + 1

        while index < len(lines):
            raw_line = lines[index]
            line = self._strip_comment(raw_line).strip()

            if not line:
                index += 1
                continue

            if line == "}":
                return function, index + 1

            label_match = self.LABEL_RE.match(line)

            if label_match:
                current_block = BasicBlock(
                    label_match.group(1)
                )
                function.blocks.append(current_block)

                index += 1
                continue

            if current_block is None:
                raise CompileError(
                    f"line {index + 1}: "
                    "instruction outside basic block"
                )

            result = None
            instruction_text = line

            result_match = self.RESULT_RE.match(line)

            if result_match:
                result = result_match.group(1)
                instruction_text = result_match.group(2)

            parts = shlex.split(
                instruction_text,
                posix=True,
            )

            if not parts:
                index += 1
                continue

            current_block.instructions.append(
                SSAInstruction(
                    result=result,
                    opcode=parts[0].upper(),
                    operands=parts[1:],
                    line=index + 1,
                )
            )

            index += 1

        raise CompileError(
            f"function {name} is missing closing brace"
        )

    @staticmethod
    def _split_arguments(text: str) -> list[str]:
        result = []
        current = []
        depth = 0

        for char in text:
            if char == "," and depth == 0:
                result.append(
                    "".join(current).strip()
                )
                current = []
                continue

            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1

            current.append(char)

        if current:
            result.append(
                "".join(current).strip()
            )

        return result

    @staticmethod
    def _strip_comment(line: str) -> str:
        result = []
        in_string = False
        escaped = False

        for char in line:
            if char == '"' and not escaped:
                in_string = not in_string

            if char == ";" and not in_string:
                break

            result.append(char)

            if char == "\\" and not escaped:
                escaped = True
            else:
                escaped = False

        return "".join(result)


class SSACompiler:
    RUNTIME_FUNCTIONS = {
        "CONST_FLOAT": "const_float",
        "FADD": "fadd",
        "FSUB": "fsub",
        "FMUL": "fmul",
        "FDIV": "fdiv",
        "FNEG": "fneg",
        "INT_TO_FLOAT": "int_to_float",
        "FLOAT_TO_INT": "float_to_int",
        "STR_CONCAT": "str_concat",
        "STR_LEN": "str_len",
        "ALLOC_STRUCT": "alloc_struct",
        "LOAD_FIELD": "load_field",
        "STORE_FIELD": "store_field",
        "ALLOC_LIST": "list_new",
        "LIST_GET": "list_get_int",
        "LIST_SET": "list_set_int",
        "LIST_APPEND": "list_append_int",
        "LIST_LEN": "list_len",
        "TO_STR": "to_str",
        "TO_BOOL": "to_bool",
        "SQRT": "sqrt",
        "SIN": "sin",
        "COS": "cos",
        "TAN": "tan",
        "ABS": "abs",
        "MIN": "min",
        "MAX": "max",
        "FLOOR": "floor",
        "CEIL": "ceil",
        "ROUND": "round",
        "POW": "pow",
    }

    SYSCALLS = {
        "PRINT": SYS_PRINT,
        "PRINTLN": SYS_PRINTLN,
        "INPUT": SYS_INPUT,
        "STORE_GLOBAL": SYS_STORE_GLOBAL,
        "LOAD_GLOBAL": SYS_LOAD_GLOBAL,
        "RAISE": SYS_RAISE,
        "TRY_BEGIN": SYS_TRY_BEGIN,
        "TRY_END": SYS_TRY_END,
    }

    SYSCALL_NAMES = {v: k for k, v in SYSCALLS.items()}

    def __init__(self, kernel_mode: bool = False):
        self.kernel_mode = kernel_mode

        self.functions: list[Function] = []

        self.output: list[str] = []

        self.function: Function | None = None
        self.value_info: dict[str, ValueInfo] = {}
        self.slots: dict[str, Slot] = {}

        self.phis: dict[str, list[Phi]] = {}

        self.frame_size = 0
        self.label_counter = 0
        self.string_counter = 0

        self.block: BasicBlock | None = None

        self._string_data: dict[str, str] = {}
        self.used_helpers: set[str] = set()
        self.used_helpers: set[str] = set()
        self._is_entry_point = False

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def compile(
        self,
        source: str,
    ) -> str:
        self.functions = SSAParser().parse(source)
        self.output.clear()

        if self.kernel_mode:
            self._emit(".entry main")
            self._emit("")

        for function in self.functions:
            self._compile_function(function)

        self._emit("")
        self._emit_helpers()

        return "\n".join(self.output) + "\n"

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _compile_function(
        self,
        function: Function,
    ):
        self.function = function
        self.value_info.clear()
        self.slots.clear()
        self.phis.clear()
        self.frame_size = 0
        self.label_counter = 0
        self.string_counter = 0
        self._string_data.clear()
        self.used_helpers.clear()

        self._is_entry_point = function.name == "main"
        self._epilogue_emitted = False

        self._infer_value_types(function)
        self._collect_phis(function)
        self._allocate_slots()

        self._emit(f"{function.name}:")
        self._emit(
            f"    PUSH {FRAME_REGISTER}"
        )

        if self.frame_size:
            self._emit(
                f"    SUB_SP {self.frame_size}"
            )

        self._emit(
            f"    LOAD_SP {FRAME_REGISTER}"
        )

        self._store_arguments()

        for block in function.blocks:
            self.block = block

            self._emit("")
            self._emit(
                f"{function.name}_{block.name}:"
            )

            for instruction in block.instructions:
                if instruction.opcode == "PHI":
                    continue

                self._compile_instruction(
                    instruction
                )

        if self._is_entry_point and not self._epilogue_emitted:
            self._emit_epilogue()

        for label, value in self._string_data.items():
            self._emit(f'{label}: string "{value}"')

        self.block = None
        self.function = None

    def _store_arguments(self):
        if self.function is None:
            return

        for index, (name, value_type) in enumerate(
            self.function.arguments
        ):
            if index >= len(ARGUMENT_REGISTERS):
                raise CompileError(
                    f"function {self.function.name}: "
                    "too many arguments"
                )

            value_name = (
                name
                if name.startswith("%")
                else f"%{name}"
            )

            register = ARGUMENT_REGISTERS[index]

            self._store_value(
                value_name,
                register,
            )

    # ------------------------------------------------------------------
    # Type inference
    # ------------------------------------------------------------------

    def _infer_value_types(
        self,
        function: Function,
    ):
        for name, value_type in function.arguments:
            value_name = (
                name
                if name.startswith("%")
                else f"%{name}"
            )

            self._define_type(
                value_name,
                value_type,
            )

        for block in function.blocks:
            for instruction in block.instructions:
                if instruction.result is None:
                    continue

                value_type = self._infer_result_type(
                    instruction
                )

                self._define_type(
                    instruction.result,
                    value_type,
                )

    def _define_type(
        self,
        name: str,
        value_type: str,
    ):
        size = self._type_size(value_type)

        existing = self.value_info.get(name)

        if existing is not None:
            if existing.value_type != value_type:
                if existing.value_type == "UNKNOWN":
                    existing.value_type = value_type
                    existing.size = size
                return

        self.value_info[name] = ValueInfo(
            name=name,
            value_type=value_type,
            size=size,
        )

    def _infer_result_type(
        self,
        instruction: SSAInstruction,
    ) -> str:
        opcode = instruction.opcode

        if opcode in {
            "CONST_INT",
            "ADD",
            "SUB",
            "MUL",
            "DIV",
            "MOD",
            "NEG",
            "ABS",
            "MIN",
            "MAX",
        }:
            return "INT64"

        if opcode in {
            "CONST_FLOAT",
            "FADD",
            "FSUB",
            "FMUL",
            "FDIV",
            "FNEG",
            "SQRT",
            "SIN",
            "COS",
            "TAN",
            "FLOOR",
            "CEIL",
            "ROUND",
            "POW",
        }:
            return "FLOAT64"

        if opcode == "CONST_BOOL":
            return "BOOL"

        if opcode in {
            "LT",
            "GT",
            "LE",
            "GE",
            "EQ",
            "NE",
            "AND",
            "OR",
            "NOT",
            "TO_BOOL",
        }:
            return "BOOL"

        if opcode in {
            "CONST_STR",
            "STR_CONCAT",
            "TO_STR",
            "INPUT",
        }:
            return "STRING"

        if opcode in {
            "ALLOC_STRUCT",
            "ALLOC_LIST",
        }:
            return "POINTER"

        if opcode in {
            "LIST_LEN",
            "STR_LEN",
            "LIST_GET",
        }:
            return "INT64"

        if opcode == "INT_TO_FLOAT":
            return "FLOAT64"

        if opcode == "FLOAT_TO_INT":
            return "INT64"

        if opcode == "LOAD_GLOBAL":
            return "UNKNOWN"

        if opcode == "CALL":
            return "UNKNOWN"

        if opcode == "CALL_EXTERN":
            return "UNKNOWN"

        if opcode == "CALL_BUILTIN":
            return "UNKNOWN"

        if opcode == "COPY":
            if not instruction.operands:
                return "UNKNOWN"

            return self._get_value_type(
                instruction.operands[0]
            )

        if opcode == "SELECT":
            if len(instruction.operands) < 2:
                return "UNKNOWN"

            return self._get_value_type(
                instruction.operands[1]
            )

        if opcode == "PHI":
            if instruction.operands:
                return self._get_value_type(
                    instruction.operands[0]
                )

        return "UNKNOWN"

    @staticmethod
    def _type_size(value_type: str) -> int:
        if value_type in {
            "INT64",
            "FLOAT64",
        }:
            return 8

        return 4

    def _get_value_type(
        self,
        value: str,
    ) -> str:
        info = self.value_info.get(value)

        if info is None:
            return "UNKNOWN"

        return info.value_type

    # ------------------------------------------------------------------
    # Stack slots
    # ------------------------------------------------------------------

    def _allocate_slots(self):
        offset = 0

        for value, info in self.value_info.items():
            self.slots[value] = Slot(
                offset=offset,
                size=info.size,
            )

            offset += info.size

        self.frame_size = offset

        if self.frame_size & 3:
            self.frame_size = (
                self.frame_size + 3
            ) & ~3

    # ------------------------------------------------------------------
    # PHI
    # ------------------------------------------------------------------

    def _collect_phis(
        self,
        function: Function,
    ):
        for block in function.blocks:
            phis = []

            for instruction in block.instructions:
                if instruction.opcode != "PHI":
                    break

                phis.append(
                    self._parse_phi(
                        instruction
                    )
                )

            if phis:
                self.phis[block.name] = phis

    def _parse_phi(
        self,
        instruction: SSAInstruction,
    ) -> Phi:
        operands = instruction.operands

        if len(operands) < 3:
            raise CompileError(
                f"line {instruction.line}: invalid PHI"
            )

        pair_count = (len(operands) - 1) // 2

        if len(operands) != 1 + pair_count * 2:
            raise CompileError(
                f"line {instruction.line}: invalid PHI"
            )

        values = operands[:pair_count]
        predecessors = operands[
            pair_count + 1:
        ]

        assert instruction.result

        return Phi(
            result=instruction.result,
            incoming={
                predecessors[index]: values[index]
                for index in range(pair_count)
            },
        )

    def _emit_phi_copies(
        self,
        predecessor: str,
        target: str,
    ):
        for phi in self.phis.get(target, []):
            source = phi.incoming.get(
                predecessor
            )

            if source is None:
                continue

            self._copy_value(
                source,
                phi.result,
            )

    # ------------------------------------------------------------------
    # Instruction dispatch
    # ------------------------------------------------------------------

    def _compile_instruction(
        self,
        instruction: SSAInstruction,
    ):
        opcode = instruction.opcode

        if opcode == "CONST_INT":
            self._compile_const_int(instruction)
        elif opcode == "CONST_BOOL":
            self._compile_const_bool(instruction)
        elif opcode == "CONST_STR":
            self._compile_const_str(instruction)
        elif opcode == "CONST_FLOAT":
            self._compile_runtime(
                instruction,
                "runtime_const_float",
            )
        elif opcode in {
            "ADD",
            "SUB",
            "MUL",
            "DIV",
            "MOD",
        }:
            self._compile_i64_binary(
                instruction
            )
        elif opcode == "NEG":
            self._compile_i64_unary(
                instruction,
                "runtime_i64_neg",
            )
        elif opcode in {
            "FADD",
            "FSUB",
            "FMUL",
            "FDIV",
            "FNEG",
        }:
            self._compile_runtime(
                instruction,
                self.RUNTIME_FUNCTIONS[opcode],
            )
        elif opcode in {
            "LT",
            "GT",
            "LE",
            "GE",
            "EQ",
            "NE",
        }:
            self._compile_compare(
                instruction
            )
        elif opcode in {
            "AND",
            "OR",
            "BIT_AND",
            "BIT_OR",
            "BIT_XOR",
            "SHL",
            "SHR",
        }:
            self._compile_bitwise(
                instruction
            )
        elif opcode == "NOT":
            self._compile_bool_not(
                instruction
            )
        elif opcode == "COPY":
            self._copy_value(
                instruction.operands[0],
                instruction.result,
            )
        elif opcode == "SELECT":
            self._compile_select(
                instruction
            )
        elif opcode == "BRANCH":
            self._compile_branch(
                instruction
            )
        elif opcode == "JUMP":
            self._compile_jump(
                instruction
            )
        elif opcode == "RETURN":
            self._compile_return(
                instruction
            )
        elif opcode == "RETURN_VOID":
            self._compile_return_void()
        elif opcode == "CALL":
            self._compile_call(
                instruction
            )
        elif opcode == "CALL_EXTERN":
            self._compile_call(
                instruction
            )
        elif opcode == "CALL_BUILTIN":
            self._compile_builtin(
                instruction
            )
        elif opcode in self.RUNTIME_FUNCTIONS:
            self._compile_runtime(
                instruction,
                self.RUNTIME_FUNCTIONS[opcode],
            )
        elif opcode == "LOAD_GLOBAL":
            self._compile_syscall(
                instruction,
                "SYS_LOAD_GLOBAL",
            )
        elif opcode == "STORE_GLOBAL":
            self._compile_syscall(
                instruction,
                "SYS_STORE_GLOBAL",
            )
        elif opcode == "PRINT":
            self._compile_syscall(
                instruction,
                "SYS_PRINT",
            )
        elif opcode == "PRINTLN":
            self._compile_syscall(
                instruction,
                "SYS_PRINTLN",
            )
        elif opcode == "INPUT":
            self._compile_syscall(
                instruction,
                "SYS_INPUT",
            )
        elif opcode == "TRY_BEGIN":
            self._compile_syscall(
                instruction,
                "SYS_TRY_BEGIN",
            )
        elif opcode == "TRY_END":
            self._compile_syscall(
                instruction,
                "SYS_TRY_END",
            )
        elif opcode == "RAISE":
            self._compile_syscall(
                instruction,
                "SYS_RAISE",
            )
        elif opcode == "NOP":
            self._emit("    NOP")
        else:
            raise CompileError(
                f"line {instruction.line}: "
                f"unsupported SSA operation: {opcode}"
            )

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------

    def _compile_const_int(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        value = self._parse_int(
            instruction.operands[0],
            instruction.line,
        )

        assert instruction.result

        self._emit_i64_const(
            instruction.result,
            value,
        )

    def _compile_const_bool(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        value = self._parse_int(
            instruction.operands[0],
            instruction.line,
        )

        if value not in (0, 1):
            raise CompileError(
                f"line {instruction.line}: "
                "invalid boolean"
            )

        self._load_const(
            "r0",
            value,
        )

        self._store_value(
            instruction.result,
            "r0",
        )

    def _compile_const_str(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        value = instruction.operands[0]
        label = self._new_string_label()

        self._string_data[label] = value

        self._emit(
            f"    LOAD_CONST r0, {label}"
        )

        self._store_value(
            instruction.result,
            "r0",
        )

    def _compile_const_float(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        value = self._parse_float(
            instruction.operands[0],
            instruction.line,
        )

        if self.kernel_mode:
            self._compile_runtime(
                instruction,
                "runtime_const_float",
            )
        else:
            self._load_const(
                "r0",
                value,
            )

            self._store_value(
                instruction.result,
                "r0",
            )

    def _new_string_label(self) -> str:
        label = f".__str_{self.string_counter}"
        self.string_counter += 1
        return label

    def _parse_float(
        self,
        value: str,
        line: int,
    ) -> int:
        import struct

        try:
            float_val = float(value)
        except ValueError:
            raise CompileError(
                f"line {line}: invalid float: {value}"
            ) from None

        return struct.unpack("<I", struct.pack("<f", float_val))[0]

    # ------------------------------------------------------------------
    # Integer operations
    # ------------------------------------------------------------------

    def _compile_i64_binary(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        left = instruction.operands[0]
        right = instruction.operands[1]

        left_type = self._get_value_type(left)
        right_type = self._get_value_type(right)

        if left_type != "INT64" or right_type != "INT64":
            self._compile_runtime(
                instruction,
                f"{left_type.lower()}_{instruction.opcode.lower()}",
            )
            return

        self._load_i64(
            left,
            "r0",
            "r1",
        )

        self._load_i64(
            right,
            "r2",
            "r3",
        )

        helper_name = (
            f"i64_{instruction.opcode.lower()}"
        )

        self.used_helpers.add(helper_name)

        self._emit(
            f"    CALL {helper_name}"
        )

        assert instruction.result

        self._store_i64(
            instruction.result,
            "r0",
            "r1",
        )

    def _compile_i64_unary(
        self,
        instruction: SSAInstruction,
        runtime_name: str,
    ):
        self._require_result(instruction)

        operand = instruction.operands[0]
        operand_type = self._get_value_type(operand)

        if operand_type != "INT64":
            self._compile_runtime(
                instruction,
                f"{operand_type.lower()}_{runtime_name.lower()}",
            )
            return

        self._load_i64(
            operand,
            "r0",
            "r1",
        )

        helper_name = runtime_name.lower()

        self.used_helpers.add(helper_name)

        self._emit(
            f"    CALL {helper_name}"
        )

        assert instruction.result

        self._store_i64(
            instruction.result,
            "r0",
            "r1",
        )

    # ------------------------------------------------------------------
    # Bitwise
    # ------------------------------------------------------------------

    def _compile_bitwise(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        left = instruction.operands[0]
        right = instruction.operands[1]

        left_type = self._get_value_type(left)

        if left_type == "BOOL":
            self._load_value(left, "r0")
            self._load_value(right, "r1")

            machine_op = {
                "AND": "AND",
                "OR": "OR",
            }[instruction.opcode]

            self._emit(
                f"    {machine_op} r0, r0, r1"
            )

            self._store_value(
                instruction.result,
                "r0",
            )

            return

        if left_type == "INT64":
            self._compile_runtime(
                instruction,
                f"i64_{instruction.opcode.lower()}",
            )
            return

        self._load_value(left, "r0")
        self._load_value(right, "r1")

        machine_op = {
            "BIT_AND": "AND",
            "BIT_OR": "OR",
            "BIT_XOR": "XOR",
            "SHL": "SHL",
            "SHR": "SHR",
        }[instruction.opcode]

        self._emit(
            f"    {machine_op} r0, r0, r1"
        )

        self._store_value(
            instruction.result,
            "r0",
        )

    def _compile_bool_not(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        self._load_value(
            instruction.operands[0],
            "r0",
        )

        self._load_const(
            "r1",
            1,
        )

        self._emit(
            "    XOR r0, r0, r1"
        )

        self._store_value(
            instruction.result,
            "r0",
        )

    # ------------------------------------------------------------------
    # Select
    # ------------------------------------------------------------------

    def _compile_select(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        condition = instruction.operands[0]
        true_value = instruction.operands[1]
        false_value = instruction.operands[2]

        false_label = self._new_label(
            "select_false"
        )
        done_label = self._new_label(
            "select_done"
        )

        self._load_value(
            condition,
            "r0",
        )

        self._load_const(
            "r1",
            0,
        )

        self._emit(
            "    CMP_EQ r0, r1"
        )

        self._emit(
            f"    JNZ {false_label}"
        )

        self._copy_value_into(
            true_value,
            "r0",
        )

        self._emit(
            f"    JUMP {done_label}"
        )

        self._emit(
            f"{false_label}:"
        )

        self._copy_value_into(
            false_value,
            "r0",
        )

        self._emit(
            f"{done_label}:"
        )

        self._store_value(
            instruction.result,
            "r0",
        )

    # ------------------------------------------------------------------
    # Comparison
    # ------------------------------------------------------------------

    def _compile_compare(
        self,
        instruction: SSAInstruction,
    ):
        self._require_result(instruction)

        left = instruction.operands[0]
        right = instruction.operands[1]

        left_type = self._get_value_type(left)

        if left_type == "INT64":
            self._compile_runtime(
                instruction,
                f"i64_cmp_{instruction.opcode.lower()}",
            )
            return

        if left_type == "FLOAT64":
            self._compile_runtime(
                instruction,
                f"runtime_compare_{instruction.opcode.lower()}",
            )
            return

        if left_type == "STRING":
            self._compile_runtime(
                instruction,
                f"runtime_compare_{instruction.opcode.lower()}",
            )
            return

        self._load_value(left, "r0")
        self._load_value(right, "r1")

        opcode = instruction.opcode

        cmp_op = {
            "LT": "CMP_LT",
            "GT": "CMP_GT",
            "LE": "CMP_LE",
            "GE": "CMP_GE",
            "EQ": "CMP_EQ",
            "NE": "CMP_NE",
        }[opcode]

        false_label = self._new_label("cmp_false")
        done_label = self._new_label("cmp_done")

        self._emit(f"    {cmp_op} r0, r1")
        self._emit(f"    JZ {false_label}")
        self._emit("    LOAD_CONST r0, 1")
        self._emit(f"    JUMP {done_label}")
        self._emit(f"{false_label}:")
        self._emit("    LOAD_CONST r0, 0")
        self._emit(f"{done_label}:")

        self._store_value(
            instruction.result,
            "r0",
        )

    # ------------------------------------------------------------------
    # Control flow
    # ------------------------------------------------------------------

    def _compile_branch(
        self,
        instruction: SSAInstruction,
    ):
        if len(instruction.operands) != 4:
            raise CompileError(
                f"line {instruction.line}: "
                "BRANCH expects four operands"
            )

        condition = instruction.operands[0]
        false_label = instruction.operands[1]
        true_block = instruction.operands[2]
        false_block = instruction.operands[3]

        true_edge = self._new_label(
            "edge_true"
        )
        false_edge = self._new_label(
            "edge_false"
        )

        self._load_value(
            condition,
            "r0",
        )

        self._load_const(
            "r1",
            0,
        )

        self._emit(
            "    CMP_NE r0, r1"
        )

        self._emit(
            f"    JNZ {true_edge}"
        )

        self._emit(
            f"    JUMP {false_edge}"
        )

        self._emit(
            f"{true_edge}:"
        )

        assert self.block

        self._emit_phi_copies(
            self.block.name,
            true_block,
        )

        self._emit(
            f"    JUMP {self._block_label(true_block)}"
        )

        self._emit(
            f"{false_edge}:"
        )

        self._emit_phi_copies(
            self.block.name,
            false_block,
        )

        self._emit(
            f"    JUMP "
            f"{self._block_label(false_block)}"
        )

    def _compile_jump(
        self,
        instruction: SSAInstruction,
    ):
        if len(instruction.operands) != 2:
            raise CompileError(
                f"line {instruction.line}: "
                "JUMP expects two operands"
            )

        target = instruction.operands[1]

        assert self.block

        self._emit_phi_copies(
            self.block.name,
            target,
        )

        self._emit(
            f"    JUMP {self._block_label(target)}"
        )

    def _compile_return(
        self,
        instruction: SSAInstruction,
    ):
        value = instruction.operands[0]

        value_type = self._get_value_type(value)

        if value_type == "INT64":
            self._load_i64(
                value,
                "r0",
                "r1",
            )
        else:
            self._load_value(
                value,
                "r0",
            )

        self._emit_epilogue()

    def _compile_return_void(self):
        self._load_const(
            "r0",
            0,
        )

        self._emit_epilogue()

    def _emit_epilogue(self):
        if self._epilogue_emitted:
            return
        self._epilogue_emitted = True

        if self.frame_size:
            self._emit(
                f"    ADD_SP {self.frame_size}"
            )

        self._emit(
            f"    POP {FRAME_REGISTER}"
        )

        if self._is_entry_point:
            self._emit("    HALT")
        else:
            self._emit("    RETURN")

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _compile_call(
        self,
        instruction: SSAInstruction,
    ):
        if not instruction.operands:
            raise CompileError(
                f"line {instruction.line}: "
                "CALL missing function"
            )

        function_name = instruction.operands[-1]
        arguments = instruction.operands[:-1]

        self._emit_call_arguments(
            arguments,
            instruction.line,
        )

        self._emit(
            f"    CALL {function_name}"
        )

        if instruction.result is not None:
            return_type = self._get_value_type(
                instruction.result
            )

            if return_type == "INT64":
                self._store_i64(
                    instruction.result,
                    "r0",
                    "r1",
                )
            else:
                self._store_value(
                    instruction.result,
                    "r0",
                )

    def _compile_builtin(
        self,
        instruction: SSAInstruction,
    ):
        if not instruction.operands:
            raise CompileError(
                f"line {instruction.line}: "
                "CALL_BUILTIN missing name"
            )

        builtin_name = instruction.operands[-1]
        arguments = instruction.operands[:-1]

        self._emit_call_arguments(
            arguments,
            instruction.line,
        )

        self._emit(
            f"    CALL runtime_{builtin_name}"
        )

        if instruction.result is not None:
            self._store_value(
                instruction.result,
                "r0",
            )

    def _emit_call_arguments(
        self,
        arguments: list[str],
        line: int,
    ):
        register_index = 0

        for argument in arguments:
            value_type = self._get_value_type(
                argument
            )

            if value_type == "INT64":
                if register_index + 1 >= len(
                    ARGUMENT_REGISTERS
                ):
                    raise CompileError(
                        f"line {line}: "
                        "too many call arguments"
                    )

                self._load_i64(
                    argument,
                    ARGUMENT_REGISTERS[
                        register_index
                    ],
                    ARGUMENT_REGISTERS[
                        register_index + 1
                    ],
                )

                register_index += 2
            else:
                if register_index >= len(
                    ARGUMENT_REGISTERS
                ):
                    raise CompileError(
                        f"line {line}: "
                        "too many call arguments"
                    )

                self._load_value(
                    argument,
                    ARGUMENT_REGISTERS[
                        register_index
                    ],
                )

                register_index += 1

    # ------------------------------------------------------------------
    # Syscalls
    # ------------------------------------------------------------------

    def _compile_syscall(
        self,
        instruction: SSAInstruction,
        name: str,
    ):
        arguments = instruction.operands
        syscall_key = name.removeprefix("SYS_")

        if self.kernel_mode:
            if syscall_key in {"PRINT", "PRINTLN"}:
                self._compile_kernel_print(
                    instruction,
                    newline=(syscall_key == "PRINTLN"),
                )
                return

            if syscall_key == "INPUT":
                self._compile_kernel_input(instruction)
                return

        if instruction.opcode in {
            "LOAD_GLOBAL",
        }:
            if len(arguments) != 1:
                raise CompileError(
                    f"line {instruction.line}: "
                    f"{instruction.opcode} expects one operand"
                )

            self._load_const(
                "r0",
                self._parse_int(
                    arguments[0],
                    instruction.line,
                ),
            )

            syscall_id = self.SYSCALLS[syscall_key]
            self._emit(
                f"    SYSCALL {syscall_id}"
            )

            if instruction.result is not None:
                self._store_value(
                    instruction.result,
                    "r0",
                )

            return

        for index, argument in enumerate(
            arguments
        ):
            if index >= len(
                ARGUMENT_REGISTERS
            ):
                raise CompileError(
                    f"line {instruction.line}: "
                    "too many syscall arguments"
                )

            self._load_value(
                argument,
                ARGUMENT_REGISTERS[index],
            )

        syscall_id = self.SYSCALLS[syscall_key]
        self._emit(
            f"    SYSCALL {syscall_id}"
        )

        if instruction.result is not None:
            self._store_value(
                instruction.result,
                "r0",
            )

    def _compile_kernel_print(
        self,
        instruction: SSAInstruction,
        newline: bool = False,
    ):
        string_value = instruction.operands[0]

        self._load_value(string_value, "r0")

        self._load_const("r1", "CONSOLE_DATA")

        loop_label = self._new_label("print_loop")
        done_label = self._new_label("print_done")

        self._emit(f"{loop_label}:")
        self._emit("    LOAD_BYTE r2, r0, 0")
        self._emit("    LOAD_CONST r3, 0")
        self._emit("    CMP_EQ r2, r3")
        self._emit(f"    JZ {done_label}")
        self._emit("    STORE_BYTE r1, 0, r2")
        self._emit("    ADDI r0, r0, 1")
        self._emit(f"    JUMP {loop_label}")
        self._emit(f"{done_label}: ")

        if newline:
            self._load_const("r2", 10)
            self._emit("    STORE r1, 0, r2")

        if instruction.result is not None:
            self._store_value(instruction.result, "r0")

    def _compile_kernel_input(
        self,
        instruction: SSAInstruction,
    ):
        self._load_const("r0", "KEYBOARD_DATA")

        loop_label = self._new_label("input_loop")

        self._emit(f"{loop_label}:")
        self._emit("    LOAD_BYTE r1, r0, 0")
        self._emit("    LOAD_CONST r2, 0")
        self._emit("    CMP_EQ r1, r2")
        self._emit(f"    JZ {loop_label}")

        if instruction.result is not None:
            self._store_value(instruction.result, "r1")

    # ------------------------------------------------------------------
    # Runtime calls
    # ------------------------------------------------------------------

    def _compile_runtime(
        self,
        instruction: SSAInstruction,
        runtime_name: str,
    ):
        self._emit_call_arguments(
            instruction.operands,
            instruction.line,
        )

        if self.kernel_mode:
            self._emit(
                f"    CALL {runtime_name}"
            )
        else:
            self.used_helpers.add(runtime_name)
            self._emit(
                f"    CALL {runtime_name}"
            )

        if instruction.result is None:
            return

        value_type = self._get_value_type(
            instruction.result
        )

        if value_type == "INT64":
            self._store_i64(
                instruction.result,
                "r0",
                "r1",
            )
        else:
            self._store_value(
                instruction.result,
                "r0",
            )

    # ------------------------------------------------------------------
    # Value access
    # ------------------------------------------------------------------

    def _load_value(
        self,
        value: str,
        register: str,
    ):
        if value.startswith("%"):
            slot = self.slots.get(value)

            if slot is None:
                raise CompileError(
                    f"unknown SSA value: {value}"
                )

            if slot.size == 8:
                raise CompileError(
                    f"64-bit value {value} requires "
                    "the 64-bit load helper"
                )

            self._emit(
                f"    LOAD {register}, "
                f"{FRAME_REGISTER}, "
                f"{slot.offset}"
            )

            return

        raise CompileError(
            f"expected SSA value, got {value}"
        )

    def _store_value(
        self,
        value: str | None,
        register: str,
    ):
        if value is None:
            return

        slot = self.slots.get(value)

        if slot is None:
            raise CompileError(
                f"unknown SSA value: {value}"
            )

        if slot.size != 4:
            raise CompileError(
                f"64-bit value {value} requires "
                "the 64-bit store helper"
            )

        self._emit(
            f"    STORE "
            f"{FRAME_REGISTER}, "
            f"{slot.offset}, "
            f"{register}"
        )

    def _load_i64(
        self,
        value: str,
        low_register: str,
        high_register: str,
    ):
        slot = self.slots.get(value)

        if slot is None:
            raise CompileError(
                f"unknown SSA value: {value}"
            )

        if slot.size != 8:
            self._load_value(
                value,
                low_register,
            )

            self._load_const(
                high_register,
                0,
            )

            return

        self._emit(
            f"    LOAD "
            f"{low_register}, "
            f"{FRAME_REGISTER}, "
            f"{slot.offset}"
        )

        self._emit(
            f"    LOAD "
            f"{high_register}, "
            f"{FRAME_REGISTER}, "
            f"{slot.offset + 4}"
        )

    def _store_i64(
        self,
        value: str,
        low_register: str,
        high_register: str,
    ):
        slot = self.slots.get(value)

        if slot is None:
            raise CompileError(
                f"unknown SSA value: {value}"
            )

        if slot.size != 8:
            self._store_value(
                value,
                low_register,
            )
            return

        self._emit(
            f"    STORE "
            f"{FRAME_REGISTER}, "
            f"{slot.offset}, "
            f"{low_register}"
        )

        self._emit(
            f"    STORE "
            f"{FRAME_REGISTER}, "
            f"{slot.offset + 4}, "
            f"{high_register}"
        )

    def _copy_value(
        self,
        source: str,
        destination: str | None,
    ):
        if destination is None:
            return

        value_type = self._get_value_type(
            source
        )

        if value_type == "INT64":
            self._load_i64(
                source,
                "r0",
                "r1",
            )

            self._store_i64(
                destination,
                "r0",
                "r1",
            )
        else:
            self._load_value(
                source,
                "r0",
            )

            self._store_value(
                destination,
                "r0",
            )

    def _copy_value_into(
        self,
        source: str,
        register: str,
    ):
        value_type = self._get_value_type(
            source
        )

        if value_type == "INT64":
            raise CompileError(
                "SELECT of INT64 requires a dedicated "
                "64-bit lowering"
            )

        self._load_value(
            source,
            register,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _require_result(
        self,
        instruction: SSAInstruction,
    ):
        if instruction.result is None:
            raise CompileError(
                f"line {instruction.line}: "
                f"{instruction.opcode} requires a result"
            )

    def _parse_int(
        self,
        value: str,
        line: int,
    ) -> int:
        try:
            return int(value, 0)
        except ValueError:
            raise CompileError(
                f"line {line}: invalid integer: {value}"
            ) from None

    def _load_const(
        self,
        register: str,
        value: int | str,
    ):
        self._emit(
            f"    LOAD_CONST {register}, {value}"
        )

    def _emit_i64_const(
        self,
        value_name: str,
        value: int,
    ):
        value &= (1 << 64) - 1

        low = value & 0xFFFFFFFF
        high = (value >> 32) & 0xFFFFFFFF

        self._load_const(
            "r0",
            low,
        )

        self._load_const(
            "r1",
            high,
        )

        self._store_i64(
            value_name,
            "r0",
            "r1",
        )

    def _emit(
        self,
        line: str,
    ):
        self.output.append(line)

    def _new_label(
        self,
        prefix: str,
    ) -> str:
        label = (
            f".__{prefix}_{self.label_counter}"
        )
        self.label_counter += 1
        return label

    def _block_label(
        self,
        block: str,
    ) -> str:
        if self.function is None:
            raise CompileError(
                "no current function"
            )

        return (
            f"{self.function.name}_{block}"
        )

    def _emit_helpers(self):
        if "i64_add" in self.used_helpers:
            self._emit_i64_binary_helper("i64_add", "ADD")
        if "i64_sub" in self.used_helpers:
            self._emit_i64_binary_helper("i64_sub", "SUB")
        if "i64_mul" in self.used_helpers:
            self._emit_i64_binary_helper("i64_mul", "MUL")
        if "i64_div" in self.used_helpers:
            self._emit_i64_binary_helper("i64_div", "DIV")
        if "i64_mod" in self.used_helpers:
            self._emit_i64_binary_helper("i64_mod", "MOD")
        if "i64_neg" in self.used_helpers:
            self._emit_i64_unary_helper("i64_neg", "NEG")
        if "i64_bit_and" in self.used_helpers:
            self._emit_i64_binary_helper("i64_bit_and", "AND")
        if "i64_bit_or" in self.used_helpers:
            self._emit_i64_binary_helper("i64_bit_or", "OR")
        if "i64_bit_xor" in self.used_helpers:
            self._emit_i64_binary_helper("i64_bit_xor", "XOR")
        if "i64_shl" in self.used_helpers:
            self._emit_i64_binary_helper("i64_shl", "SHL")
        if "i64_shr" in self.used_helpers:
            self._emit_i64_binary_helper("i64_shr", "SHR")
        if "i64_cmp_eq" in self.used_helpers:
            self._emit_i64_cmp_helper("i64_cmp_eq", "CMP_EQ")
        if "i64_cmp_ne" in self.used_helpers:
            self._emit_i64_cmp_helper("i64_cmp_ne", "CMP_NE")
        if "i64_cmp_lt" in self.used_helpers:
            self._emit_i64_cmp_helper("i64_cmp_lt", "CMP_LT")
        if "i64_cmp_le" in self.used_helpers:
            self._emit_i64_cmp_helper("i64_cmp_le", "CMP_LE")
        if "i64_cmp_gt" in self.used_helpers:
            self._emit_i64_cmp_helper("i64_cmp_gt", "CMP_GT")
        if "i64_cmp_ge" in self.used_helpers:
            self._emit_i64_cmp_helper("i64_cmp_ge", "CMP_GE")

    def _emit_i64_binary_helper(
        self,
        name: str,
        opcode: str,
    ):
        self._emit(f"{name}:")
        self._emit("    PUSH r14")
        self._emit("    PUSH r13")
        self._emit("    PUSH r12")
        self._emit("    PUSH r11")
        self._emit("")
        self._emit("    ; low a = r0, high a = r1")
        self._emit("    ; low b = r2, high b = r3")
        self._emit("")
        self._emit(f"    {opcode} r0, r0, r2")
        self._emit("    ; TO\\DO: carry/borrow for high".replace('\\',''))
        self._emit("    ; result low in r0, high in r1 (r1 unchanged for now)")
        self._emit("    POP r11")
        self._emit("    POP r12")
        self._emit("    POP r13")
        self._emit("    POP r14")
        self._emit("    RETURN")

    def _emit_i64_unary_helper(
        self,
        name: str,
        opcode: str,
    ):
        self._emit(f"{name}:")
        self._emit("    PUSH r14")
        self._emit("    PUSH r13")
        self._emit("")
        self._emit(f"    {opcode} r0, r0")
        self._emit("    ; high unchanged")
        self._emit("    POP r13")
        self._emit("    POP r14")
        self._emit("    RETURN")

    def _emit_i64_cmp_helper(
        self,
        name: str,
        cmp_op: str,
    ):
        self._emit(f"{name}:")
        self._emit("    PUSH r14")
        self._emit("    PUSH r13")
        self._emit("    PUSH r12")
        self._emit("")
        self._emit(f"    {cmp_op} r0, r2")
        self._emit("    JZ false_label")
        self._emit("    LOAD_CONST r0, 1")
        self._emit("    JUMP done_label")
        self._emit("false_label:")
        self._emit("    LOAD_CONST r0, 0")
        self._emit("done_label:")
        self._emit("    POP r12")
        self._emit("    POP r13")
        self._emit("    POP r14")
        self._emit("    RETURN")


def compile_ssa(
    source: str,
    kernel_mode: bool = False,
) -> str:
    return SSACompiler(kernel_mode=kernel_mode).compile(source)


def compile_file(
    input_path: str,
    output_path: str,
    kernel_mode: bool = False,
):
    with open(
        input_path,
        "r",
        encoding="utf-8",
    ) as file:
        source = file.read()

    assembly = compile_ssa(source, kernel_mode=kernel_mode)

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(assembly)


def main():
    parser = argparse.ArgumentParser(
        prog="compiler",
        description="Compile SSA IR to assembly",
    )
    parser.add_argument(
        "input",
        help="input SSA file",
    )
    parser.add_argument(
        "output",
        help="output assembly file",
    )
    parser.add_argument(
        "--kernel",
        action="store_true",
        help="compile for kernel mode",
    )

    args = parser.parse_args()

    try:
        compile_file(
            args.input,
            args.output,
            kernel_mode=args.kernel,
        )
    except CompileError as error:
        print(
            f"compile error: {error}",
            file=sys.stderr,
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
