import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_clears_all_registers(dut):
    await setup_dut(dut)

    assert_dcr(
        dut,
        num_blocks=0,
        blockDim=0,
        start=0,
        msg="reset clears all",
    )


@cocotb.test()
async def test_write_num_blocks(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_NUM_BLOCKS, 8)

    assert_dcr(
        dut,
        num_blocks=8,
        blockDim=0,
        start=0,
        msg="write num_blocks",
    )


@cocotb.test()
async def test_write_blockDim(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_BLOCK_DIM, 4)

    assert_dcr(
        dut,
        num_blocks=0,
        blockDim=4,
        start=0,
        msg="write blockDim",
    )


@cocotb.test()
async def test_start_write_asserts_start(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_START, 0)

    assert_dcr(
        dut,
        start=1,
        msg="start write",
    )


@cocotb.test()
async def test_start_pulse_clears_next_idle_cycle(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_START, 0)
    assert_dcr(dut, start=1, msg="start pulse active")

    await idle_cycle(dut)

    assert_dcr(
        dut,
        start=0,
        msg="start clears next idle cycle",
    )


@cocotb.test()
async def test_start_write_does_not_modify_config_registers(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_NUM_BLOCKS, 12)
    await write_dcr(dut, ADDR_BLOCK_DIM, 4)
    await write_dcr(dut, ADDR_START, 0xDEADBEEF)

    assert_dcr(
        dut,
        num_blocks=12,
        blockDim=4,
        start=1,
        msg="start does not modify config",
    )


@cocotb.test()
async def test_write_en_low_ignores_num_blocks_write(dut):
    await setup_dut(dut)

    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = ADDR_NUM_BLOCKS
    dut.dcr_data.value = 99
    await step(dut)

    assert_dcr(
        dut,
        num_blocks=0,
        blockDim=0,
        start=0,
        msg="write_en low num_blocks ignored",
    )


@cocotb.test()
async def test_write_en_low_ignores_blockDim_write(dut):
    await setup_dut(dut)

    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = ADDR_BLOCK_DIM
    dut.dcr_data.value = 99
    await step(dut)

    assert_dcr(
        dut,
        num_blocks=0,
        blockDim=0,
        start=0,
        msg="write_en low blockDim ignored",
    )


@cocotb.test()
async def test_write_en_low_does_not_start(dut):
    await setup_dut(dut)

    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = ADDR_START
    dut.dcr_data.value = 0
    await step(dut)

    assert_dcr(
        dut,
        start=0,
        msg="write_en low start ignored",
    )


@cocotb.test()
async def test_invalid_address_does_not_modify_registers(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_NUM_BLOCKS, 7)
    await write_dcr(dut, ADDR_BLOCK_DIM, 4)

    await idle_cycle(dut)

    await write_dcr(dut, ADDR_INVALID, 0xFFFFFFFF)

    assert_dcr(
        dut,
        num_blocks=7,
        blockDim=4,
        start=0,
        msg="invalid addr ignored",
    )


@cocotb.test()
async def test_num_blocks_overwrite(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_NUM_BLOCKS, 3)
    await write_dcr(dut, ADDR_NUM_BLOCKS, 10)

    assert_dcr(
        dut,
        num_blocks=10,
        blockDim=0,
        start=0,
        msg="num_blocks overwrite",
    )


@cocotb.test()
async def test_blockDim_overwrite(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_BLOCK_DIM, 2)
    await write_dcr(dut, ADDR_BLOCK_DIM, 8)

    assert_dcr(
        dut,
        num_blocks=0,
        blockDim=8,
        start=0,
        msg="blockDim overwrite",
    )


@cocotb.test()
async def test_back_to_back_config_writes(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_NUM_BLOCKS, 16)
    await write_dcr(dut, ADDR_BLOCK_DIM, 4)

    assert_dcr(
        dut,
        num_blocks=16,
        blockDim=4,
        start=0,
        msg="back-to-back config writes",
    )


@cocotb.test()
async def test_back_to_back_start_writes_keep_start_high_each_write_cycle(dut):
    await setup_dut(dut)

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = ADDR_START
    dut.dcr_data.value = 0

    await step(dut)
    assert_dcr(dut, start=1, msg="start held cycle 1")

    await step(dut)
    assert_dcr(dut, start=1, msg="start held cycle 2")

    dut.dcr_write_en.value = 0
    await step(dut)
    assert_dcr(dut, start=0, msg="start clears after held writes")


@cocotb.test()
async def test_reset_after_writes_clears_all(dut):
    await setup_dut(dut)

    await write_dcr(dut, ADDR_NUM_BLOCKS, 9)
    await write_dcr(dut, ADDR_BLOCK_DIM, 4)
    await write_dcr(dut, ADDR_START, 0)

    dut.rst.value = 1
    await step(dut)

    assert_dcr(
        dut,
        num_blocks=0,
        blockDim=0,
        start=0,
        msg="reset after writes",
    )