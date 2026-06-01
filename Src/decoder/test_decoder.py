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
    assert dut.opcode.value == opcode,           f"Expected opcode {opcode} got {dut.opcode.value}"
    assert dut.sync_en.value == 1,               f"Expected sync_en=1 got {dut.sync_en.value}"
    assert dut.write_back_en.value == 0,         f"Expected write_back_en=0 got {dut.write_back_en.value}"
    assert dut.branch_en.value == 0,             f"Expected branch_en=0 got {dut.branch_en.value}"
    assert dut.ret.value == 0,                   f"Expected ret=0 got {dut.ret.value}"
    assert dut.mem_read_en.value == 0,           f"Expected mem_read_en=0 got {dut.mem_read_en.value}"
    assert dut.mem_write_en.value == 0,          f"Expected mem_write_en=0 got {dut.mem_write_en.value}"
    assert dut.nzp_en.value == 0,               f"Expected nzp_en=0 got {dut.nzp_en.value}"