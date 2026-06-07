import random
import cocotb

from tests.common import *


RNG_SEED = 0xDCDCDC


def rand_u32():
    return random.getrandbits(32)


@cocotb.test()
async def test_random_num_blocks_writes(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    expected_num_blocks = 0

    for i in range(100):
        value = rand_u32()
        await write_dcr(dut, ADDR_NUM_BLOCKS, value)

        expected_num_blocks = value

        assert_dcr(
            dut,
            num_blocks=expected_num_blocks,
            start=0,
            msg=f"random num_blocks iter={i}",
        )


@cocotb.test()
async def test_random_blockDim_writes(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    expected_blockDim = 0

    for i in range(100):
        value = rand_u32()
        await write_dcr(dut, ADDR_BLOCK_DIM, value)

        expected_blockDim = value

        assert_dcr(
            dut,
            blockDim=expected_blockDim,
            start=0,
            msg=f"random blockDim iter={i}",
        )


@cocotb.test()
async def test_random_mixed_writes_mirror_model(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    expected_num_blocks = 0
    expected_blockDim = 0

    for i in range(300):
        addr = random.randint(0, 3)
        data = rand_u32()
        write_en = random.randint(0, 1)

        dut.dcr_write_en.value = write_en
        dut.dcr_addr.value = addr
        dut.dcr_data.value = data

        await step(dut)

        expected_start = 0

        if write_en:
            if addr == ADDR_NUM_BLOCKS:
                expected_num_blocks = data
            elif addr == ADDR_BLOCK_DIM:
                expected_blockDim = data
            elif addr == ADDR_START:
                expected_start = 1
            else:
                expected_start = 0

        assert_dcr(
            dut,
            num_blocks=expected_num_blocks,
            blockDim=expected_blockDim,
            start=expected_start,
            msg=f"random mixed iter={i}",
        )


@cocotb.test()
async def test_random_start_pulses_clear_when_not_rewritten(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    for i in range(100):
        await write_dcr(dut, ADDR_START, rand_u32())
        assert_dcr(dut, start=1, msg=f"random start active iter={i}")

        idle_cycles = random.randint(1, 5)
        for j in range(idle_cycles):
            await idle_cycle(dut)
            assert_dcr(
                dut,
                start=0,
                msg=f"random start clear iter={i} idle={j}",
            )