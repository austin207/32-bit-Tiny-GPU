from cocotb.triggers import Timer


# ── Opcode constants ──────────────────────────────────────────────────────────

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


ALU_WRITEBACK_OPS = {
    OP_ADD, OP_SUB, OP_MUL, OP_DIV,
    OP_MOD, OP_SHL, OP_SHR, OP_AND,
    OP_OR, OP_XOR, OP_NOT, OP_FMA,
    OP_IMUL, OP_SAR, OP_DOT4, OP_RELU,
    OP_CLAMP, OP_MAX,
}


def u32(v: int) -> int:
    return int(v) & 0xFFFFFFFF


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


def encode_branch(op=OP_BR, nzp_mask=0, sync_offset=0, branch_offset=0):
    return (
        ((op & 0x3F) << 26) |
        ((nzp_mask & 0x7) << 23) |
        ((sync_offset & 0x7FF) << 12) |
        (branch_offset & 0xFFF)
    )


def encode_sync(sync_offset=0):
    return (
        ((OP_SYNC & 0x3F) << 26) |
        ((sync_offset & 0x7FF) << 12)
    )


async def apply_instruction(dut, instruction):
    dut.instruction.value = u32(instruction)
    await Timer(1, unit="ns")


def expected_controls(op):
    controls = {
        "ret": 0,
        "write_back_en": 0,
        "mem_read_en": 0,
        "mem_write_en": 0,
        "branch_en": 0,
        "nzp_en": 0,
        "sync_en": 0,
    }

    if op in ALU_WRITEBACK_OPS:
        controls["write_back_en"] = 1
    elif op == OP_CMP:
        controls["nzp_en"] = 1
    elif op == OP_BR:
        controls["branch_en"] = 1
    elif op == OP_LDR:
        controls["mem_read_en"] = 1
        controls["write_back_en"] = 1
    elif op == OP_STR:
        controls["mem_write_en"] = 1
    elif op == OP_CONST:
        controls["write_back_en"] = 1
    elif op == OP_RET:
        controls["ret"] = 1
    elif op == OP_SYNC:
        controls["sync_en"] = 1

    return controls


def dut_controls(dut):
    return {
        "ret": int(dut.ret.value),
        "write_back_en": int(dut.write_back_en.value),
        "mem_read_en": int(dut.mem_read_en.value),
        "mem_write_en": int(dut.mem_write_en.value),
        "branch_en": int(dut.branch_en.value),
        "nzp_en": int(dut.nzp_en.value),
        "sync_en": int(dut.sync_en.value),
    }


def assert_controls(dut, expected, msg=""):
    got = dut_controls(dut)
    for name, exp in expected.items():
        assert got[name] == exp, (
            f"{msg} {name}: expected {exp}, got {got[name]} "
            f"all_controls={got}"
        )


def assert_raw_fields(dut, instruction, msg=""):
    instruction = u32(instruction)

    exp_opcode = (instruction >> 26) & 0x3F
    exp_rd     = (instruction >> 21) & 0x1F
    exp_rs1    = (instruction >> 16) & 0x1F
    exp_rs2    = (instruction >> 11) & 0x1F
    exp_rs3    = (instruction >> 6)  & 0x1F
    exp_imm    = instruction & 0xFFFF
    exp_nzp    = (instruction >> 23) & 0x7
    exp_sync   = (instruction >> 12) & 0x7FF
    exp_branch = instruction & 0xFFF

    assert int(dut.opcode.value) == exp_opcode, f"{msg} opcode expected {exp_opcode}, got {dut.opcode.value}"
    assert int(dut.rd_addr.value) == exp_rd, f"{msg} rd expected {exp_rd}, got {dut.rd_addr.value}"
    assert int(dut.rs1_addr.value) == exp_rs1, f"{msg} rs1 expected {exp_rs1}, got {dut.rs1_addr.value}"
    assert int(dut.rs2_addr.value) == exp_rs2, f"{msg} rs2 expected {exp_rs2}, got {dut.rs2_addr.value}"
    assert int(dut.rs3_addr.value) == exp_rs3, f"{msg} rs3 expected {exp_rs3}, got {dut.rs3_addr.value}"
    assert int(dut.imm.value) == exp_imm, f"{msg} imm expected {exp_imm}, got {dut.imm.value}"
    assert int(dut.nzp_mask.value) == exp_nzp, f"{msg} nzp_mask expected {exp_nzp}, got {dut.nzp_mask.value}"
    assert int(dut.sync_offset.value) == exp_sync, f"{msg} sync_offset expected {exp_sync}, got {dut.sync_offset.value}"
    assert int(dut.branch_offset.value) == exp_branch, f"{msg} branch_offset expected {exp_branch}, got {dut.branch_offset.value}"