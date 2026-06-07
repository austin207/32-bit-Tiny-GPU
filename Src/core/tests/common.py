import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


# ── Opcodes ───────────────────────────────────────────────────────────────────

OP_NOP   = 0x00
OP_ADD   = 0x01
OP_SUB   = 0x02
OP_MUL   = 0x03
OP_DIV   = 0x04
OP_MOD   = 0x05
OP_SHL   = 0x06
OP_SHR   = 0x07
OP_AND   = 0x08
OP_OR    = 0x09
OP_XOR   = 0x0A
OP_NOT   = 0x0B
OP_FMA   = 0x0C
OP_CMP   = 0x0D
OP_BR    = 0x0E
OP_LDR   = 0x0F
OP_STR   = 0x10
OP_CONST = 0x11
OP_RET   = 0x12
OP_IMUL  = 0x13
OP_SAR   = 0x14
OP_SYNC  = 0x15
OP_DOT4  = 0x16
OP_RELU  = 0x17
OP_CLAMP = 0x18
OP_MAX   = 0x19


# ── Register aliases ─────────────────────────────────────────────────────────

R0  = 0
R1  = 1
R2  = 2
R3  = 3
R4  = 4
R5  = 5
R6  = 6
R7  = 7
R8  = 8
R9  = 9
R10 = 10

THREAD_IDX = 29
BLOCK_IDX  = 30
BLOCK_DIM  = 31

MASK32 = 0xFFFFFFFF


# ── Integer helpers ───────────────────────────────────────────────────────────

def u32(v: int) -> int:
    return int(v) & MASK32


def s32(v: int) -> int:
    v = int(v) & MASK32
    return v - 0x100000000 if v & 0x80000000 else v


def s8(v: int) -> int:
    v = int(v) & 0xFF
    return v - 0x100 if v & 0x80 else v


def pack_i8x4(vals) -> int:
    assert len(vals) == 4
    return (
        ((vals[0] & 0xFF) << 0)  |
        ((vals[1] & 0xFF) << 8)  |
        ((vals[2] & 0xFF) << 16) |
        ((vals[3] & 0xFF) << 24)
    )


def unpack_i8x4(word: int):
    word = u32(word)
    return [
        s8((word >> 0) & 0xFF),
        s8((word >> 8) & 0xFF),
        s8((word >> 16) & 0xFF),
        s8((word >> 24) & 0xFF),
    ]


def dot4_model(a_word: int, b_word: int, acc: int = 0) -> int:
    a = unpack_i8x4(a_word)
    b = unpack_i8x4(b_word)
    total = s32(acc)

    for i in range(4):
        total += a[i] * b[i]

    return s32(total)


# ── Encoders ──────────────────────────────────────────────────────────────────

def encode_r(op, rd=0, rs1=0, rs2=0, rs3=0):
    return (
        ((op  & 0x3F) << 26) |
        ((rd  & 0x1F) << 21) |
        ((rs1 & 0x1F) << 16) |
        ((rs2 & 0x1F) << 11) |
        ((rs3 & 0x1F) << 6)
    )


def encode_i(op, rd=0, rs1=0, imm=0):
    return (
        ((op  & 0x3F) << 26) |
        ((rd  & 0x1F) << 21) |
        ((rs1 & 0x1F) << 16) |
        (imm & 0xFFFF)
    )


def encode_branch(nzp_mask=0, branch_offset=0):
    return (
        ((OP_BR & 0x3F) << 26) |
        ((nzp_mask & 0x7) << 23) |
        (branch_offset & 0xFFF)
    )


def instr_const(rd, imm):
    return encode_i(OP_CONST, rd=rd, rs1=0, imm=imm)


def instr_add(rd, rs1, rs2):
    return encode_r(OP_ADD, rd=rd, rs1=rs1, rs2=rs2)


def instr_sub(rd, rs1, rs2):
    return encode_r(OP_SUB, rd=rd, rs1=rs1, rs2=rs2)


def instr_mul(rd, rs1, rs2):
    return encode_r(OP_MUL, rd=rd, rs1=rs1, rs2=rs2)


def instr_cmp(rs1, rs2):
    return encode_r(OP_CMP, rd=0, rs1=rs1, rs2=rs2)


def instr_dot(rd, rs1, rs2):
    # DOT4 accumulator comes from rd through rs3=rd.
    return encode_r(OP_DOT4, rd=rd, rs1=rs1, rs2=rs2, rs3=rd)


def instr_ldr(rd, addr_reg, imm=0):
    return encode_i(OP_LDR, rd=rd, rs1=addr_reg, imm=imm)


def instr_str(value_reg, addr_reg, imm=0):
    # STR uses rd field as value register, rs1 as address register.
    return encode_i(OP_STR, rd=value_reg, rs1=addr_reg, imm=imm)


def instr_ret():
    return encode_r(OP_RET)


# ── Simulation helpers ────────────────────────────────────────────────────────

async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.core_start.value = 0
    dut.blockIdx.value = 0
    dut.blockDim.value = 4

    dut.prog_mem_resp_valid.value = 0
    dut.prog_mem_resp_data.value = 0

    dut.data_mem_resp_valid.value = 0
    dut.data_mem_resp_data.value = 0


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut, block_idx=0, block_dim=4):
    init_inputs(dut)

    dut.blockIdx.value = u32(block_idx)
    dut.blockDim.value = u32(block_dim)

    dut.rst.value = 1
    await step(dut)
    await step(dut)

    dut.rst.value = 0
    await step(dut)

    assert int(dut.block_done.value) == 0, "block_done should be low after reset"
    assert int(dut.prog_mem_req_valid.value) == 0, "prog_mem_req_valid should be low after reset"
    assert int(dut.data_mem_req_valid.value) == 0, "data_mem_req_valid should be low after reset"


async def program_memory_model(dut, instructions):
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if int(dut.prog_mem_req_valid.value) == 1:
            addr = int(dut.prog_mem_req_addr.value)
            dut.prog_mem_resp_valid.value = 1
            dut.prog_mem_resp_data.value = u32(instructions.get(addr, 0))
        else:
            dut.prog_mem_resp_valid.value = 0
            dut.prog_mem_resp_data.value = 0


async def data_memory_model(dut, data_memory):
    """
    data_mem_req_rw convention from LSU/mem_controller:
      1 = read
      0 = write
    """
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        if int(dut.data_mem_req_valid.value) == 1:
            addr = int(dut.data_mem_req_addr.value)
            rw = int(dut.data_mem_req_rw.value)

            if rw == 1:
                dut.data_mem_resp_data.value = u32(data_memory.get(addr, 0))
            else:
                data_memory[addr] = u32(int(dut.data_mem_req_data.value))
                dut.data_mem_resp_data.value = 0

            dut.data_mem_resp_valid.value = 1
        else:
            dut.data_mem_resp_valid.value = 0
            dut.data_mem_resp_data.value = 0


async def setup_core(dut, instructions, data_memory=None, block_idx=0, block_dim=4):
    if data_memory is None:
        data_memory = {}

    await start_clock(dut)
    await reset_dut(dut, block_idx=block_idx, block_dim=block_dim)

    cocotb.start_soon(program_memory_model(dut, instructions))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    return data_memory


async def run_core(dut, instructions, data_memory=None, block_idx=0, block_dim=4, timeout_cycles=1000):
    data_memory = await setup_core(
        dut,
        instructions=instructions,
        data_memory=data_memory,
        block_idx=block_idx,
        block_dim=block_dim,
    )

    dut.core_start.value = 1
    await step(dut)
    dut.core_start.value = 0

    for cycle in range(timeout_cycles):
        await step(dut)

        if int(dut.block_done.value) == 1:
            return cycle + 1, data_memory

    raise AssertionError(f"core timed out after {timeout_cycles} cycles")


def program_dict(instrs):
    return {i: u32(instr) for i, instr in enumerate(instrs)}


def assert_mem(data_memory, addr, expected, msg=""):
    got = u32(data_memory.get(addr, 0))
    exp = u32(expected)

    assert got == exp, (
        f"{msg}: mem[{addr}] expected 0x{exp:08x} ({s32(exp)}), "
        f"got 0x{got:08x} ({s32(got)})"
    )


def assert_mem_range(data_memory, base, expected_values, msg=""):
    for i, expected in enumerate(expected_values):
        assert_mem(data_memory, base + i, expected, f"{msg} index={i}")
async def run_core_loaded(dut, timeout_cycles=1000):
    """
    Run core using already-running program/data memory models.

    Use this for looped random tests. The dictionaries captured by the memory
    models should be mutated in-place before each run.
    """
    dut.core_start.value = 1
    await step(dut)
    dut.core_start.value = 0

    for cycle in range(timeout_cycles):
        await step(dut)

        if int(dut.block_done.value) == 1:
            return cycle + 1

    raise AssertionError(f"core timed out after {timeout_cycles} cycles")
