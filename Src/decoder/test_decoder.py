import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_add_instruction(dut):
    opcode = 0x01
    rd = 5
    rs1 = 2
    rs2 = 3
    instruction = (opcode << 26) | (rd << 21) | (rs1 << 16) | (rs2 << 11)
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value == opcode, f"Expected opcode {opcode} got {dut.opcode.value}"
    assert dut.rd_addr.value == rd, f"Expected rd {rd} got {dut.rd_addr.value}"
    assert dut.rs1_addr.value == rs1, f"Expected rs1 {rs1} got {dut.rs1_addr.value}"
    assert dut.rs2_addr.value == rs2, f"Expected rs2 {rs2} got {dut.rs2_addr.value}"

    assert dut.write_back_en.value == 1, f"Expected write back enable to be 1 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value == 0, f"Expected memory read enable to be 0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value == 0, f"Expected memory write enable to be 0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value == 0, f"Expected branch enable to be 0 got {dut.branch_en.value}"
    assert dut.nzp_en.value == 0, f"Expected NZP enable to be 0 got {dut.nzp_en.value}"

@cocotb.test()
async def test_BRNZP_instruction(dut):
    opcode = 0x0E
    nzp_mask = 0b101
    sync_offset = 0x3FF
    offset = 0xABC
    instruction = (opcode << 26) | (nzp_mask << 23) | (sync_offset << 12) | offset
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.sync_en.value == 0, f"Expected sync enable to be 1 got {dut.sync_en.value}"
    assert dut.branch_en.value == 1, f"Expected branch enable to be 1 got {dut.branch_en.value}"
    assert dut.opcode.value == opcode, f"Expected opcode {opcode} got {dut.opcode.value}"
    assert dut.nzp_mask.value == nzp_mask, f"Expected NZP mask {nzp_mask} got {dut.nzp_mask.value}"
    assert dut.branch_offset.value == offset, f"Expected branch offset {offset} got {dut.branch_offset.value}"
    assert dut.sync_offset.value == sync_offset, f"Expected sync offset {sync_offset} got {dut.sync_offset.value}"

    assert dut.write_back_en.value == 0, f"Expected write back enable to be 0 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value == 0, f"Expected memory read enable to be 0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value == 0, f"Expected memory write enable to be 0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value == 1, f"Expected branch enable to be 1 got {dut.branch_en.value}"
    assert dut.nzp_en.value == 0, f"Expected NZP enable to be 0 got {dut.nzp_en.value}"

@cocotb.test()
async def test_LDR_instruction(dut):
    opcode = 0x0F
    rd = 4
    rs1 = 1
    offset = 0x10
    instruction = (opcode << 26) | (rd << 21) | (rs1 << 16) | offset
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value == opcode, f"Expected opcode {opcode} got {dut.opcode.value}"
    assert dut.rd_addr.value == rd, f"Expected rd {rd} got {dut.rd_addr.value}"
    assert dut.rs1_addr.value == rs1, f"Expected rs1 {rs1} got {dut.rs1_addr.value}"
    assert dut.imm.value == offset, f"Expected offset {offset} got {dut.imm.value}"

    assert dut.write_back_en.value == 1, f"Expected write back enable to be 1 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value == 1, f"Expected memory read enable to be 1 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value == 0, f"Expected memory write enable to be 0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value == 0, f"Expected branch enable to be 0 got {dut.branch_en.value}"
    assert dut.nzp_en.value == 0, f"Expected NZP enable to be 0 got {dut.nzp_en.value}"

@cocotb.test()
async def test_RET_instruction(dut):
    opcode = 0x12
    instruction = (opcode << 26)
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value == opcode, f"Expected opcode {opcode} got {dut.opcode.value}"

    assert dut.write_back_en.value == 0, f"Expected write back enable to be 0 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value == 0, f"Expected memory read enable to be 0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value == 0, f"Expected memory write enable to be 0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value == 0, f"Expected branch enable to be 0 got {dut.branch_en.value}"
    assert dut.nzp_en.value == 0, f"Expected NZP enable to be 0 got {dut.nzp_en.value}"
    assert dut.ret.value == 1, f"Expected return enable to be 1 got {dut.ret.value}"

@cocotb.test()
async def test_SYNC_instruction(dut):
    opcode = 0x15
    instruction = (opcode << 26)
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value == opcode,   f"Expected opcode {opcode} got {dut.opcode.value}"
    assert dut.sync_en.value == 1,       f"Expected sync_en=1 got {dut.sync_en.value}"
    assert dut.write_back_en.value == 0, f"Expected write_back_en=0 got {dut.write_back_en.value}"
    assert dut.branch_en.value == 0,     f"Expected branch_en=0 got {dut.branch_en.value}"
    assert dut.ret.value == 0,           f"Expected ret=0 got {dut.ret.value}"
    assert dut.mem_read_en.value == 0,   f"Expected mem_read_en=0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value == 0,  f"Expected mem_write_en=0 got {dut.mem_write_en.value}"
    assert dut.nzp_en.value == 0,        f"Expected nzp_en=0 got {dut.nzp_en.value}"


# ── Phase 1 AI instruction decoder tests ─────────────────────────────────────
# All four new opcodes are R-type ALU ops.
# Expected: write_back_en=1, all other control signals=0.

@cocotb.test()
async def test_DOT4_instruction(dut):
    opcode = 0x16
    rd  = 3
    rs1 = 1
    rs2 = 2
    rs3 = 3  # accumulator = rd
    instruction = (opcode << 26) | (rd << 21) | (rs1 << 16) | (rs2 << 11) | (rs3 << 6)
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value    == opcode, f"DOT4: expected opcode {opcode} got {dut.opcode.value}"
    assert dut.rd_addr.value   == rd,     f"DOT4: expected rd {rd} got {dut.rd_addr.value}"
    assert dut.rs1_addr.value  == rs1,    f"DOT4: expected rs1 {rs1} got {dut.rs1_addr.value}"
    assert dut.rs2_addr.value  == rs2,    f"DOT4: expected rs2 {rs2} got {dut.rs2_addr.value}"
    assert dut.rs3_addr.value  == rs3,    f"DOT4: expected rs3 {rs3} got {dut.rs3_addr.value}"
    assert dut.write_back_en.value == 1,  f"DOT4: expected write_back_en=1 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value   == 0,  f"DOT4: expected mem_read_en=0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value  == 0,  f"DOT4: expected mem_write_en=0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value     == 0,  f"DOT4: expected branch_en=0 got {dut.branch_en.value}"
    assert dut.nzp_en.value        == 0,  f"DOT4: expected nzp_en=0 got {dut.nzp_en.value}"
    assert dut.ret.value           == 0,  f"DOT4: expected ret=0 got {dut.ret.value}"
    assert dut.sync_en.value       == 0,  f"DOT4: expected sync_en=0 got {dut.sync_en.value}"

@cocotb.test()
async def test_RELU_instruction(dut):
    opcode = 0x17
    rd  = 5
    rs1 = 2
    instruction = (opcode << 26) | (rd << 21) | (rs1 << 16)
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value    == opcode, f"RELU: expected opcode {opcode} got {dut.opcode.value}"
    assert dut.rd_addr.value   == rd,     f"RELU: expected rd {rd} got {dut.rd_addr.value}"
    assert dut.rs1_addr.value  == rs1,    f"RELU: expected rs1 {rs1} got {dut.rs1_addr.value}"
    assert dut.write_back_en.value == 1,  f"RELU: expected write_back_en=1 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value   == 0,  f"RELU: expected mem_read_en=0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value  == 0,  f"RELU: expected mem_write_en=0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value     == 0,  f"RELU: expected branch_en=0 got {dut.branch_en.value}"
    assert dut.nzp_en.value        == 0,  f"RELU: expected nzp_en=0 got {dut.nzp_en.value}"
    assert dut.ret.value           == 0,  f"RELU: expected ret=0 got {dut.ret.value}"
    assert dut.sync_en.value       == 0,  f"RELU: expected sync_en=0 got {dut.sync_en.value}"

@cocotb.test()
async def test_CLAMP_instruction(dut):
    opcode = 0x18
    rd  = 7
    rs1 = 4
    instruction = (opcode << 26) | (rd << 21) | (rs1 << 16)
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value    == opcode, f"CLAMP: expected opcode {opcode} got {dut.opcode.value}"
    assert dut.rd_addr.value   == rd,     f"CLAMP: expected rd {rd} got {dut.rd_addr.value}"
    assert dut.rs1_addr.value  == rs1,    f"CLAMP: expected rs1 {rs1} got {dut.rs1_addr.value}"
    assert dut.write_back_en.value == 1,  f"CLAMP: expected write_back_en=1 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value   == 0,  f"CLAMP: expected mem_read_en=0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value  == 0,  f"CLAMP: expected mem_write_en=0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value     == 0,  f"CLAMP: expected branch_en=0 got {dut.branch_en.value}"
    assert dut.nzp_en.value        == 0,  f"CLAMP: expected nzp_en=0 got {dut.nzp_en.value}"
    assert dut.ret.value           == 0,  f"CLAMP: expected ret=0 got {dut.ret.value}"
    assert dut.sync_en.value       == 0,  f"CLAMP: expected sync_en=0 got {dut.sync_en.value}"

@cocotb.test()
async def test_MAX_instruction(dut):
    opcode = 0x19
    rd  = 6
    rs1 = 3
    rs2 = 4
    instruction = (opcode << 26) | (rd << 21) | (rs1 << 16) | (rs2 << 11)
    dut.instruction.value = instruction
    await Timer(1, unit="ns")
    assert dut.opcode.value    == opcode, f"MAX: expected opcode {opcode} got {dut.opcode.value}"
    assert dut.rd_addr.value   == rd,     f"MAX: expected rd {rd} got {dut.rd_addr.value}"
    assert dut.rs1_addr.value  == rs1,    f"MAX: expected rs1 {rs1} got {dut.rs1_addr.value}"
    assert dut.rs2_addr.value  == rs2,    f"MAX: expected rs2 {rs2} got {dut.rs2_addr.value}"
    assert dut.write_back_en.value == 1,  f"MAX: expected write_back_en=1 got {dut.write_back_en.value}"
    assert dut.mem_read_en.value   == 0,  f"MAX: expected mem_read_en=0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value  == 0,  f"MAX: expected mem_write_en=0 got {dut.mem_write_en.value}"
    assert dut.branch_en.value     == 0,  f"MAX: expected branch_en=0 got {dut.branch_en.value}"
    assert dut.nzp_en.value        == 0,  f"MAX: expected nzp_en=0 got {dut.nzp_en.value}"
    assert dut.ret.value           == 0,  f"MAX: expected ret=0 got {dut.ret.value}"
    assert dut.sync_en.value       == 0,  f"MAX: expected sync_en=0 got {dut.sync_en.value}"