import cocotb

from tests.common import *


@cocotb.test()
async def test_nop_control_signals_low(dut):
    instruction = encode_r(OP_NOP, rd=5, rs1=2, rs2=3, rs3=4)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "NOP")
    assert_controls(dut, expected_controls(OP_NOP), "NOP controls")


@cocotb.test()
async def test_raw_r_type_field_extraction(dut):
    instruction = encode_r(OP_ADD, rd=5, rs1=2, rs2=3, rs3=4)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "R-type field extraction")


@cocotb.test()
async def test_raw_i_type_field_extraction(dut):
    instruction = encode_i(OP_LDR, rd=4, rs1=1, imm=0xABCD)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "I-type field extraction")


@cocotb.test()
async def test_raw_branch_field_extraction(dut):
    instruction = encode_branch(
        op=OP_BR,
        nzp_mask=0b101,
        sync_offset=0x3FF,
        branch_offset=0xABC,
    )
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "BR field extraction")


@cocotb.test()
async def test_all_alu_writeback_opcodes(dut):
    for op in sorted(ALU_WRITEBACK_OPS):
        instruction = encode_r(op, rd=7, rs1=8, rs2=9, rs3=10)
        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"ALU op 0x{op:02x}")
        assert_controls(dut, expected_controls(op), f"ALU op 0x{op:02x}")


@cocotb.test()
async def test_cmp_enables_only_nzp(dut):
    instruction = encode_r(OP_CMP, rd=0, rs1=3, rs2=4)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "CMP")
    assert_controls(dut, expected_controls(OP_CMP), "CMP controls")


@cocotb.test()
async def test_branch_enables_only_branch(dut):
    instruction = encode_branch(
        op=OP_BR,
        nzp_mask=0b111,
        sync_offset=0x155,
        branch_offset=0x321,
    )
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "BR")
    assert_controls(dut, expected_controls(OP_BR), "BR controls")


@cocotb.test()
async def test_ldr_enables_mem_read_and_writeback(dut):
    instruction = encode_i(OP_LDR, rd=4, rs1=1, imm=0x10)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "LDR")
    assert_controls(dut, expected_controls(OP_LDR), "LDR controls")


@cocotb.test()
async def test_str_enables_only_mem_write(dut):
    instruction = encode_i(OP_STR, rd=4, rs1=1, imm=0x20)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "STR")
    assert_controls(dut, expected_controls(OP_STR), "STR controls")


@cocotb.test()
async def test_const_enables_writeback(dut):
    instruction = encode_i(OP_CONST, rd=6, rs1=0, imm=0x1234)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "CONST")
    assert_controls(dut, expected_controls(OP_CONST), "CONST controls")


@cocotb.test()
async def test_ret_enables_only_ret(dut):
    instruction = encode_r(OP_RET)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "RET")
    assert_controls(dut, expected_controls(OP_RET), "RET controls")


@cocotb.test()
async def test_sync_enables_only_sync(dut):
    instruction = encode_sync(sync_offset=0x456)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "SYNC")
    assert_controls(dut, expected_controls(OP_SYNC), "SYNC controls")


@cocotb.test()
async def test_dot4_rs3_accumulator_field(dut):
    rd = 3
    rs1 = 1
    rs2 = 2
    rs3 = rd

    instruction = encode_r(OP_DOT4, rd=rd, rs1=rs1, rs2=rs2, rs3=rs3)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "DOT4")
    assert int(dut.rs3_addr.value) == rd, f"DOT4 rs3 should equal accumulator rd={rd}"
    assert_controls(dut, expected_controls(OP_DOT4), "DOT4 controls")


@cocotb.test()
async def test_ai_unary_ops_writeback(dut):
    for op in [OP_RELU, OP_CLAMP]:
        instruction = encode_r(op, rd=5, rs1=2)
        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"AI unary op 0x{op:02x}")
        assert_controls(dut, expected_controls(op), f"AI unary op 0x{op:02x}")


@cocotb.test()
async def test_max_writeback_and_rs2_field(dut):
    instruction = encode_r(OP_MAX, rd=6, rs1=3, rs2=4)
    await apply_instruction(dut, instruction)

    assert_raw_fields(dut, instruction, "MAX")
    assert int(dut.rs2_addr.value) == 4, "MAX rs2 extraction"
    assert_controls(dut, expected_controls(OP_MAX), "MAX controls")


@cocotb.test()
async def test_illegal_opcodes_all_controls_low(dut):
    legal = {
        OP_NOP, OP_CMP, OP_BR, OP_LDR, OP_STR, OP_CONST,
        OP_RET, OP_SYNC,
    } | ALU_WRITEBACK_OPS

    for op in range(64):
        if op in legal:
            continue

        instruction = encode_r(op, rd=1, rs1=2, rs2=3, rs3=4)
        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"illegal op 0x{op:02x}")
        assert_controls(dut, expected_controls(op), f"illegal op 0x{op:02x}")