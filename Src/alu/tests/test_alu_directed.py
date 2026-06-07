import cocotb

from tests.common import *


# ── Basic/default behavior ────────────────────────────────────────────────────

@cocotb.test()
async def test_nop_default_zero(dut):
    await drive_alu(dut, OP_NOP, 123, 456, 789)
    assert_result_u32(dut, 0, "NOP result")
    assert_nzp(dut, 0, "NOP NZP")


@cocotb.test()
async def test_illegal_opcode_default_zero(dut):
    await drive_alu(dut, 0x3F, 123, 456, 789)
    assert_result_u32(dut, 0, "illegal opcode result")
    assert_nzp(dut, 0, "illegal opcode NZP")


# ── Arithmetic directed tests ─────────────────────────────────────────────────

@cocotb.test()
async def test_add_directed(dut):
    await drive_alu(dut, OP_ADD, 5, 3)
    assert_result_u32(dut, 8, "ADD 5+3")


@cocotb.test()
async def test_add_wraparound(dut):
    await drive_alu(dut, OP_ADD, 0xFFFFFFFF, 1)
    assert_result_u32(dut, 0, "ADD wraparound")


@cocotb.test()
async def test_sub_directed(dut):
    await drive_alu(dut, OP_SUB, 10, 4)
    assert_result_u32(dut, 6, "SUB 10-4")


@cocotb.test()
async def test_sub_underflow(dut):
    await drive_alu(dut, OP_SUB, 0, 1)
    assert_result_u32(dut, 0xFFFFFFFF, "SUB underflow")


@cocotb.test()
async def test_mul_directed(dut):
    await drive_alu(dut, OP_MUL, 7, 6)
    assert_result_u32(dut, 42, "MUL 7*6")


@cocotb.test()
async def test_mul_wraparound(dut):
    await drive_alu(dut, OP_MUL, 0xFFFFFFFF, 2)
    assert_result_u32(dut, 0xFFFFFFFE, "MUL wraparound")


@cocotb.test()
async def test_div_directed(dut):
    await drive_alu(dut, OP_DIV, 100, 7)
    assert_result_u32(dut, 100 // 7, "DIV 100/7")


@cocotb.test()
async def test_mod_directed(dut):
    await drive_alu(dut, OP_MOD, 100, 7)
    assert_result_u32(dut, 100 % 7, "MOD 100%7")


@cocotb.test()
async def test_imul_positive_negative(dut):
    await drive_alu(dut, OP_IMUL, u32(-7), 6)
    assert_result_s32(dut, -42, "IMUL -7*6")


@cocotb.test()
async def test_imul_negative_negative(dut):
    await drive_alu(dut, OP_IMUL, u32(-7), u32(-6))
    assert_result_s32(dut, 42, "IMUL -7*-6")


# ── Shift directed tests ──────────────────────────────────────────────────────

@cocotb.test()
async def test_shl_directed(dut):
    await drive_alu(dut, OP_SHL, 0x00000001, 4)
    assert_result_u32(dut, 0x00000010, "SHL")


@cocotb.test()
async def test_shr_directed(dut):
    await drive_alu(dut, OP_SHR, 0x80000000, 31)
    assert_result_u32(dut, 0x00000001, "SHR logical")


@cocotb.test()
async def test_sar_positive(dut):
    await drive_alu(dut, OP_SAR, 0x00000040, 2)
    assert_result_s32(dut, 0x10, "SAR positive")


@cocotb.test()
async def test_sar_negative(dut):
    await drive_alu(dut, OP_SAR, u32(-8), 1)
    assert_result_s32(dut, -4, "SAR negative")


# ── Bitwise directed tests ────────────────────────────────────────────────────

@cocotb.test()
async def test_and_directed(dut):
    await drive_alu(dut, OP_AND, 0xF0F0F0F0, 0x0FF00FF0)
    assert_result_u32(dut, 0x00F000F0, "AND")


@cocotb.test()
async def test_or_directed(dut):
    await drive_alu(dut, OP_OR, 0xF0F00000, 0x00000F0F)
    assert_result_u32(dut, 0xF0F00F0F, "OR")


@cocotb.test()
async def test_xor_directed(dut):
    await drive_alu(dut, OP_XOR, 0xAAAA5555, 0xFFFF0000)
    assert_result_u32(dut, 0x55555555, "XOR")


@cocotb.test()
async def test_not_directed(dut):
    await drive_alu(dut, OP_NOT, 0x00000000)
    assert_result_u32(dut, 0xFFFFFFFF, "NOT zero")


# ── FMA directed tests ────────────────────────────────────────────────────────

@cocotb.test()
async def test_fma_directed(dut):
    await drive_alu(dut, OP_FMA, 6, 7, 5)
    assert_result_u32(dut, 47, "FMA 6*7+5")


@cocotb.test()
async def test_fma_wraparound(dut):
    await drive_alu(dut, OP_FMA, 0xFFFFFFFF, 2, 3)
    assert_result_u32(dut, 1, "FMA wraparound")


# ── CMP directed tests ────────────────────────────────────────────────────────

@cocotb.test()
async def test_cmp_equal(dut):
    await drive_alu(dut, OP_CMP, 5, 5)
    assert_result_u32(dut, 0, "CMP result")
    assert_nzp(dut, 0b010, "CMP equal")


@cocotb.test()
async def test_cmp_greater(dut):
    await drive_alu(dut, OP_CMP, 7, 3)
    assert_nzp(dut, 0b001, "CMP greater")


@cocotb.test()
async def test_cmp_less(dut):
    await drive_alu(dut, OP_CMP, 2, 9)
    assert_nzp(dut, 0b100, "CMP less")


@cocotb.test()
async def test_cmp_signed_negative_less_than_positive(dut):
    await drive_alu(dut, OP_CMP, u32(-1), 1)
    assert_nzp(dut, 0b100, "CMP -1 < 1")


@cocotb.test()
async def test_cmp_signed_positive_greater_than_negative(dut):
    await drive_alu(dut, OP_CMP, 1, u32(-1))
    assert_nzp(dut, 0b001, "CMP 1 > -1")


# ── DOT4 directed tests ───────────────────────────────────────────────────────

@cocotb.test()
async def test_dot4_positive(dut):
    a = pack_i8x4([1, 2, 3, 4])
    b = pack_i8x4([1, 2, 3, 4])
    await drive_alu(dut, OP_DOT4, a, b, 0)
    assert_result_s32(dut, 30, "DOT4 positive")


@cocotb.test()
async def test_dot4_accumulate(dut):
    a = pack_i8x4([1, 1, 1, 1])
    b = pack_i8x4([2, 2, 2, 2])
    await drive_alu(dut, OP_DOT4, a, b, 10)
    assert_result_s32(dut, 18, "DOT4 accumulate")


@cocotb.test()
async def test_dot4_mixed_signs(dut):
    a = pack_i8x4([1, -1, 2, -2])
    b = pack_i8x4([3, 4, 5, 6])
    await drive_alu(dut, OP_DOT4, a, b, 0)
    assert_result_s32(dut, -3, "DOT4 mixed signs")


@cocotb.test()
async def test_dot4_all_negative(dut):
    a = pack_i8x4([-1, -2, -3, -4])
    b = pack_i8x4([1, 2, 3, 4])
    await drive_alu(dut, OP_DOT4, a, b, 0)
    assert_result_s32(dut, -30, "DOT4 all negative A")


@cocotb.test()
async def test_dot4_max_lane_values(dut):
    a = pack_i8x4([127, -128, 127, -128])
    b = pack_i8x4([1, 1, -1, -1])
    expected = 127 - 128 - 127 + 128
    await drive_alu(dut, OP_DOT4, a, b, 0)
    assert_result_s32(dut, expected, "DOT4 max lane values")


# ── RELU directed tests ───────────────────────────────────────────────────────

@cocotb.test()
async def test_relu_positive(dut):
    await drive_alu(dut, OP_RELU, 42)
    assert_result_s32(dut, 42, "RELU positive")


@cocotb.test()
async def test_relu_negative(dut):
    await drive_alu(dut, OP_RELU, u32(-7))
    assert_result_s32(dut, 0, "RELU negative")


@cocotb.test()
async def test_relu_zero(dut):
    await drive_alu(dut, OP_RELU, 0)
    assert_result_s32(dut, 0, "RELU zero")


# ── CLAMP directed tests ──────────────────────────────────────────────────────

@cocotb.test()
async def test_clamp_in_range(dut):
    await drive_alu(dut, OP_CLAMP, 50)
    assert_result_s32(dut, 50, "CLAMP in range")


@cocotb.test()
async def test_clamp_above_max(dut):
    await drive_alu(dut, OP_CLAMP, 200)
    assert_result_s32(dut, 127, "CLAMP above max")


@cocotb.test()
async def test_clamp_below_min(dut):
    await drive_alu(dut, OP_CLAMP, u32(-200))
    assert_result_s32(dut, -128, "CLAMP below min")


@cocotb.test()
async def test_clamp_exact_upper_boundary(dut):
    await drive_alu(dut, OP_CLAMP, 127)
    assert_result_s32(dut, 127, "CLAMP +127")


@cocotb.test()
async def test_clamp_exact_lower_boundary(dut):
    await drive_alu(dut, OP_CLAMP, u32(-128))
    assert_result_s32(dut, -128, "CLAMP -128")


# ── MAX directed tests ────────────────────────────────────────────────────────

@cocotb.test()
async def test_max_first_greater(dut):
    await drive_alu(dut, OP_MAX, 10, 5)
    assert_result_s32(dut, 10, "MAX first greater")


@cocotb.test()
async def test_max_second_greater(dut):
    await drive_alu(dut, OP_MAX, 3, 8)
    assert_result_s32(dut, 8, "MAX second greater")


@cocotb.test()
async def test_max_equal(dut):
    await drive_alu(dut, OP_MAX, 7, 7)
    assert_result_s32(dut, 7, "MAX equal")


@cocotb.test()
async def test_max_both_negative(dut):
    await drive_alu(dut, OP_MAX, u32(-3), u32(-7))
    assert_result_s32(dut, -3, "MAX both negative")


@cocotb.test()
async def test_max_negative_vs_positive(dut):
    await drive_alu(dut, OP_MAX, u32(-3), 2)
    assert_result_s32(dut, 2, "MAX negative vs positive")


# ── MIN directed tests ────────────────────────────────────────────────────────

@cocotb.test()
async def test_min_first_smaller(dut):
    await drive_alu(dut, OP_MIN, 5, 10)
    assert_result_s32(dut, 5, "MIN first smaller")


@cocotb.test()
async def test_min_second_smaller(dut):
    await drive_alu(dut, OP_MIN, 20, 3)
    assert_result_s32(dut, 3, "MIN second smaller")


@cocotb.test()
async def test_min_equal(dut):
    await drive_alu(dut, OP_MIN, 7, 7)
    assert_result_s32(dut, 7, "MIN equal")


@cocotb.test()
async def test_min_negative_vs_positive(dut):
    await drive_alu(dut, OP_MIN, u32(-5), 3)
    assert_result_s32(dut, -5, "MIN negative vs positive")


# ── EXP8 directed tests ───────────────────────────────────────────────────────

@cocotb.test()
async def test_exp8_zero_input(dut):
    # x=0: exp(0/64)*127 = 127, saturates
    await drive_alu(dut, OP_EXP8, 0)
    assert_result_u32(dut, 127, "EXP8 x=0 saturates")


@cocotb.test()
async def test_exp8_positive_input_saturates(dut):
    # x=64: exp(1.0)*127 >> 127, saturates
    await drive_alu(dut, OP_EXP8, 64)
    assert_result_u32(dut, 127, "EXP8 x=64 saturates")


@cocotb.test()
async def test_exp8_minus64(dut):
    # x=-64: exp(-1.0)*127 = 47
    await drive_alu(dut, OP_EXP8, u32(-64))
    assert_result_u32(dut, 47, "EXP8 x=-64")


@cocotb.test()
async def test_exp8_minus128(dut):
    # x=-128: exp(-2.0)*127 = 17
    await drive_alu(dut, OP_EXP8, u32(-128))
    assert_result_u32(dut, 17, "EXP8 x=-128")


@cocotb.test()
async def test_exp8_minus32(dut):
    # x=-32: exp(-0.5)*127 = 77
    await drive_alu(dut, OP_EXP8, u32(-32))
    assert_result_u32(dut, 77, "EXP8 x=-32")


@cocotb.test()
async def test_exp8_monotone_decreasing(dut):
    # For x = -128 to -1, output must be non-increasing
    prev = 0  # smaller than any possible output
    for x in range(-128, 0):
        await drive_alu(dut, OP_EXP8, u32(x))
        v = int(dut.result.value)
        assert v >= prev, f"EXP8 not monotone at x={x}: got {v} < prev {prev}"
        prev = v