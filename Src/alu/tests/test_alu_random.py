import random
import cocotb

from tests.common import *


RNG_SEED = 0xA10A17


def rand_u32():
    return random.getrandbits(32)


def rand_s32():
    return random.randint(-(2**31), 2**31 - 1)


def rand_i8():
    return random.randint(-128, 127)


# ── Random arithmetic and bitwise tests ───────────────────────────────────────

@cocotb.test()
async def test_random_add_sub_mul(dut):
    random.seed(RNG_SEED)

    for i in range(200):
        a = rand_u32()
        b = rand_u32()

        await drive_alu(dut, OP_ADD, a, b)
        assert_result_u32(dut, a + b, f"random ADD iter={i}")

        await drive_alu(dut, OP_SUB, a, b)
        assert_result_u32(dut, a - b, f"random SUB iter={i}")

        await drive_alu(dut, OP_MUL, a, b)
        assert_result_u32(dut, a * b, f"random MUL iter={i}")


@cocotb.test()
async def test_random_div_mod_nonzero(dut):
    random.seed(RNG_SEED + 1)

    for i in range(100):
        a = rand_u32()
        b = random.randint(1, 0xFFFFFFFF)

        await drive_alu(dut, OP_DIV, a, b)
        assert_result_u32(dut, trunc_div_u32(a, b), f"random DIV iter={i}")

        await drive_alu(dut, OP_MOD, a, b)
        assert_result_u32(dut, trunc_mod_u32(a, b), f"random MOD iter={i}")


@cocotb.test()
async def test_random_bitwise(dut):
    random.seed(RNG_SEED + 2)

    for i in range(200):
        a = rand_u32()
        b = rand_u32()

        await drive_alu(dut, OP_AND, a, b)
        assert_result_u32(dut, a & b, f"random AND iter={i}")

        await drive_alu(dut, OP_OR, a, b)
        assert_result_u32(dut, a | b, f"random OR iter={i}")

        await drive_alu(dut, OP_XOR, a, b)
        assert_result_u32(dut, a ^ b, f"random XOR iter={i}")

        await drive_alu(dut, OP_NOT, a, b)
        assert_result_u32(dut, ~a, f"random NOT iter={i}")


@cocotb.test()
async def test_random_shifts(dut):
    random.seed(RNG_SEED + 3)

    for i in range(200):
        a = rand_u32()
        sh = random.randint(0, 31)

        await drive_alu(dut, OP_SHL, a, sh)
        assert_result_u32(dut, a << sh, f"random SHL iter={i}")

        await drive_alu(dut, OP_SHR, a, sh)
        assert_result_u32(dut, u32(a) >> sh, f"random SHR iter={i}")

        await drive_alu(dut, OP_SAR, a, sh)
        assert_result_s32(dut, s32(a) >> sh, f"random SAR iter={i}")


# ── Random signed tests ───────────────────────────────────────────────────────

@cocotb.test()
async def test_random_imul(dut):
    random.seed(RNG_SEED + 4)

    for i in range(200):
        a = rand_s32()
        b = rand_s32()
        expected = s32(a * b)

        await drive_alu(dut, OP_IMUL, u32(a), u32(b))
        assert_result_s32(dut, expected, f"random IMUL iter={i}")


@cocotb.test()
async def test_random_cmp_signed(dut):
    random.seed(RNG_SEED + 5)

    for i in range(200):
        a = rand_s32()
        b = rand_s32()

        if a == b:
            exp = 0b010
        elif a > b:
            exp = 0b001
        else:
            exp = 0b100

        await drive_alu(dut, OP_CMP, u32(a), u32(b))
        assert_result_u32(dut, 0, f"random CMP result iter={i}")
        assert_nzp(dut, exp, f"random CMP NZP iter={i}")


# ── Random AI ops ─────────────────────────────────────────────────────────────

@cocotb.test()
async def test_random_dot4(dut):
    random.seed(RNG_SEED + 6)

    for i in range(300):
        a_lanes = [rand_i8() for _ in range(4)]
        b_lanes = [rand_i8() for _ in range(4)]
        acc = rand_s32()

        a = pack_i8x4(a_lanes)
        b = pack_i8x4(b_lanes)
        expected = dot4_model(a, b, acc)

        await drive_alu(dut, OP_DOT4, a, b, u32(acc))
        assert_result_s32(dut, expected, f"random DOT4 iter={i}, A={a_lanes}, B={b_lanes}, acc={acc}")


@cocotb.test()
async def test_random_relu_clamp_max(dut):
    random.seed(RNG_SEED + 7)

    for i in range(200):
        a = rand_s32()
        b = rand_s32()

        await drive_alu(dut, OP_RELU, u32(a))
        assert_result_s32(dut, max(a, 0), f"random RELU iter={i}")

        if a > 127:
            clamp_exp = 127
        elif a < -128:
            clamp_exp = -128
        else:
            clamp_exp = a

        await drive_alu(dut, OP_CLAMP, u32(a))
        assert_result_s32(dut, clamp_exp, f"random CLAMP iter={i}")

        await drive_alu(dut, OP_MAX, u32(a), u32(b))
        assert_result_s32(dut, max(a, b), f"random MAX iter={i}")


@cocotb.test()
async def test_random_fma_unsigned_behavior(dut):
    random.seed(RNG_SEED + 8)

    for i in range(200):
        a = rand_u32()
        b = rand_u32()
        c = rand_u32()

        expected = u32((u32(a) * u32(b)) + u32(c))

        await drive_alu(dut, OP_FMA, a, b, c)
        assert_result_u32(dut, expected, f"random FMA iter={i}")