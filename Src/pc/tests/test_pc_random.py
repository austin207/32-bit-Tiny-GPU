import random
import cocotb

from tests.common import *


RNG_SEED = 0x0C517E

@cocotb.test()
async def test_random_sequential_increment_counts(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    expected_pc = 0

    for i in range(100):
        n = random.randint(0, 10)

        await increment_pc(dut, n)
        expected_pc += n

        assert_pc(dut, expected_pc, f"random sequential increments iter={i}")


@cocotb.test()
async def test_random_branch_taken_offsets(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    expected_pc = 0

    for i in range(100):
        # Move PC forward a little
        inc = random.randint(0, 5)
        await increment_pc(dut, inc)
        expected_pc += inc

        flag = random.choice([NZP_N, NZP_Z, NZP_P])
        offset = random.randint(0, 0xFFF)

        await store_nzp(dut, flag)
        await branch_cycle(dut, flag, offset)

        expected_pc = u32(expected_pc + offset)

        assert_pc(dut, expected_pc, f"random branch taken iter={i}")


@cocotb.test()
async def test_random_branch_not_taken(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    expected_pc = 0

    for i in range(100):
        inc = random.randint(0, 5)
        await increment_pc(dut, inc)
        expected_pc += inc

        flag = random.choice([NZP_N, NZP_Z, NZP_P])
        masks_not_taking = [m for m in range(8) if (m & flag) == 0]
        mask = random.choice(masks_not_taking)
        offset = random.randint(0, 0xFFF)

        await store_nzp(dut, flag)
        await branch_cycle(dut, mask, offset)

        expected_pc = u32(expected_pc + 1)

        assert_pc(dut, expected_pc, f"random branch not taken iter={i}")


@cocotb.test()
async def test_random_nzp_store_readback(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    expected_pc = 0

    for i in range(100):
        flag = random.randint(0, 7)
        await store_nzp(dut, flag)

        assert_pc(dut, expected_pc, f"random NZP store does not move PC iter={i}")
        assert_nzp(dut, flag, f"random NZP readback iter={i}")


@cocotb.test()
async def test_random_mixed_increment_branch_block_reset(dut):
    random.seed(RNG_SEED + 4)
    await setup_dut(dut)

    expected_pc = 0
    expected_nzp = 0

    for i in range(200):
        action = random.choice(["inc", "store_nzp", "branch", "block_rst", "hold"])

        if action == "inc":
            n = random.randint(1, 5)
            await increment_pc(dut, n)
            expected_pc = u32(expected_pc + n)

        elif action == "store_nzp":
            flag = random.randint(0, 7)
            await store_nzp(dut, flag)
            expected_nzp = flag & 0x7

        elif action == "branch":
            mask = random.randint(0, 7)
            offset = random.randint(0, 50)
            await branch_cycle(dut, mask, offset)

            if (expected_nzp & mask) != 0:
                expected_pc = u32(expected_pc + offset)
            else:
                expected_pc = u32(expected_pc + 1)

        elif action == "block_rst":
            await block_reset_cycle(dut)
            expected_pc = 0
            expected_nzp = 0

        else:
            dut.pc_en.value = 0
            dut.branch_en.value = 0
            dut.nzp_en.value = 0
            await step(dut)

        assert_pc(dut, expected_pc, f"random mixed PC iter={i}, action={action}")
        assert_nzp(dut, expected_nzp, f"random mixed NZP iter={i}, action={action}")