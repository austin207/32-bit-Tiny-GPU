import random
import cocotb

from tests.common import *


RNG_SEED = 0xDEC0DE


def rand_instr():
    return random.getrandbits(32)


@cocotb.test()
async def test_random_raw_field_extraction(dut):
    random.seed(RNG_SEED)

    for i in range(500):
        instruction = rand_instr()
        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"random raw fields iter={i}")


@cocotb.test()
async def test_random_control_decode_all_opcodes(dut):
    random.seed(RNG_SEED + 1)

    for i in range(500):
        op = random.randint(0, 63)
        instruction = (
            ((op & 0x3F) << 26) |
            random.getrandbits(26)
        )
        await apply_instruction(dut, instruction)

        assert_controls(dut, expected_controls(op), f"random controls iter={i} op=0x{op:02x}")


@cocotb.test()
async def test_random_r_type_alu_fields_and_controls(dut):
    random.seed(RNG_SEED + 2)

    ops = sorted(ALU_WRITEBACK_OPS)

    for i in range(300):
        op = random.choice(ops)
        rd = random.randint(0, 31)
        rs1 = random.randint(0, 31)
        rs2 = random.randint(0, 31)
        rs3 = random.randint(0, 31)

        instruction = encode_r(op, rd=rd, rs1=rs1, rs2=rs2, rs3=rs3)
        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"random ALU fields iter={i}")
        assert_controls(dut, expected_controls(op), f"random ALU controls iter={i}")


@cocotb.test()
async def test_random_branch_fields_and_controls(dut):
    random.seed(RNG_SEED + 3)

    for i in range(300):
        nzp_mask = random.randint(0, 7)
        sync_offset = random.randint(0, 0x7FF)
        branch_offset = random.randint(0, 0xFFF)

        instruction = encode_branch(
            op=OP_BR,
            nzp_mask=nzp_mask,
            sync_offset=sync_offset,
            branch_offset=branch_offset,
        )
        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"random branch fields iter={i}")
        assert_controls(dut, expected_controls(OP_BR), f"random branch controls iter={i}")


@cocotb.test()
async def test_random_sync_fields_and_controls(dut):
    random.seed(RNG_SEED + 4)

    for i in range(300):
        sync_offset = random.randint(0, 0x7FF)
        instruction = encode_sync(sync_offset=sync_offset)

        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"random SYNC fields iter={i}")
        assert_controls(dut, expected_controls(OP_SYNC), f"random SYNC controls iter={i}")


@cocotb.test()
async def test_random_ldr_str_const_fields_and_controls(dut):
    random.seed(RNG_SEED + 5)

    for i in range(300):
        op = random.choice([OP_LDR, OP_STR, OP_CONST])
        rd = random.randint(0, 31)
        rs1 = random.randint(0, 31)
        imm = random.randint(0, 0xFFFF)

        instruction = encode_i(op, rd=rd, rs1=rs1, imm=imm)
        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"random I-type fields iter={i}")
        assert_controls(dut, expected_controls(op), f"random I-type controls iter={i}")


@cocotb.test()
async def test_random_illegal_opcodes_controls_low(dut):
    random.seed(RNG_SEED + 6)

    legal = {
        OP_NOP, OP_CMP, OP_BR, OP_LDR, OP_STR, OP_CONST,
        OP_RET, OP_SYNC,
    } | ALU_WRITEBACK_OPS

    illegal_ops = [op for op in range(64) if op not in legal]

    for i in range(300):
        op = random.choice(illegal_ops)
        instruction = ((op & 0x3F) << 26) | random.getrandbits(26)

        await apply_instruction(dut, instruction)

        assert_raw_fields(dut, instruction, f"random illegal fields iter={i}")
        assert_controls(dut, expected_controls(op), f"random illegal controls iter={i}")