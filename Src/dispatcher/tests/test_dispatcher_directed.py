import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_clears_outputs(dut):
    await setup_dut(dut)

    assert_dispatcher(
        dut,
        core_start=0,
        kernel_done=0,
        block_indices=[0, 0, 0, 0],
        msg="reset",
    )


@cocotb.test()
async def test_empty_kernel_done_immediately(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=0)

    assert_dispatcher(
        dut,
        core_start=0,
        kernel_done=1,
        msg="empty kernel",
    )


@cocotb.test()
async def test_single_block_launches_core0(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=1)

    assert_dispatcher(
        dut,
        core_start=0b0001,
        kernel_done=0,
        block_indices=[0, None, None, None],
        msg="single block launch",
    )


@cocotb.test()
async def test_single_block_completion_sets_kernel_done(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=1)
    await pulse_block_done(dut, 0b0001)

    assert_dispatcher(
        dut,
        core_start=0b0000,
        kernel_done=1,
        msg="single block done",
    )


@cocotb.test()
async def test_two_blocks_launch_core0_core1(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=2)

    assert_dispatcher(
        dut,
        core_start=0b0011,
        kernel_done=0,
        block_indices=[0, 1, None, None],
        msg="two blocks launch",
    )


@cocotb.test()
async def test_four_blocks_launch_all_cores(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=4)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        kernel_done=0,
        block_indices=[0, 1, 2, 3],
        msg="four blocks launch",
    )


@cocotb.test()
async def test_four_blocks_complete_all_at_once(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=4)
    await pulse_block_done(dut, 0b1111)

    assert_dispatcher(
        dut,
        core_start=0b0000,
        kernel_done=1,
        msg="four blocks complete",
    )


@cocotb.test()
async def test_more_blocks_than_cores_refills_core0_core1(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=6)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[0, 1, 2, 3],
        kernel_done=0,
        msg="6 blocks initial",
    )

    await pulse_block_done(dut, 0b0001)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[4, 1, 2, 3],
        kernel_done=0,
        msg="6 blocks refill core0",
    )

    await pulse_block_done(dut, 0b0010)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[4, 5, 2, 3],
        kernel_done=0,
        msg="6 blocks refill core1",
    )

    await pulse_block_done(dut, 0b1111)

    assert_dispatcher(
        dut,
        core_start=0b0000,
        kernel_done=1,
        msg="6 blocks complete",
    )


@cocotb.test()
async def test_simultaneous_two_core_completion_refills_two_blocks(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=8)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[0, 1, 2, 3],
        msg="8 blocks initial",
    )

    await pulse_block_done(dut, 0b0011)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[4, 5, 2, 3],
        kernel_done=0,
        msg="8 blocks refill core0/core1",
    )


@cocotb.test()
async def test_simultaneous_all_core_completion_refills_all_cores(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=8)

    await pulse_block_done(dut, 0b1111)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[4, 5, 6, 7],
        kernel_done=0,
        msg="8 blocks refill all cores",
    )

    await pulse_block_done(dut, 0b1111)

    assert_dispatcher(
        dut,
        core_start=0b0000,
        kernel_done=1,
        msg="8 blocks complete",
    )


@cocotb.test()
async def test_inactive_block_done_is_ignored(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=1)

    assert_dispatcher(
        dut,
        core_start=0b0001,
        kernel_done=0,
        msg="inactive done setup",
    )

    # core1 is not active, so this must not count.
    await pulse_block_done(dut, 0b0010)

    assert_dispatcher(
        dut,
        core_start=0b0001,
        kernel_done=0,
        block_indices=[0, None, None, None],
        msg="inactive block_done ignored",
    )

    await pulse_block_done(dut, 0b0001)

    assert_dispatcher(
        dut,
        core_start=0b0000,
        kernel_done=1,
        msg="active core completion",
    )


@cocotb.test()
async def test_partial_completion_before_final_done(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=4)

    await pulse_block_done(dut, 0b0101)

    assert_dispatcher(
        dut,
        core_start=0b1010,
        kernel_done=0,
        msg="partial completion",
    )

    await pulse_block_done(dut, 0b1010)

    assert_dispatcher(
        dut,
        core_start=0b0000,
        kernel_done=1,
        msg="partial then final completion",
    )


@cocotb.test()
async def test_kernel_done_stays_high_until_next_launch(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=1)
    await pulse_block_done(dut, 0b0001)

    assert_dispatcher(dut, kernel_done=1, core_start=0, msg="done high")

    await wait_cycles(dut, 3)

    assert_dispatcher(dut, kernel_done=1, core_start=0, msg="done sticky")


@cocotb.test()
async def test_back_to_back_kernel_launches(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=1)
    await pulse_block_done(dut, 0b0001)

    assert_dispatcher(dut, kernel_done=1, core_start=0, msg="first kernel done")

    await launch_kernel(dut, num_blocks=4)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        kernel_done=0,
        block_indices=[0, 1, 2, 3],
        msg="second kernel launched",
    )

    await pulse_block_done(dut, 0b1111)

    assert_dispatcher(
        dut,
        core_start=0,
        kernel_done=1,
        msg="second kernel done",
    )


@cocotb.test()
async def test_dispatch_en_ignored_while_running(dut):
    await setup_dut(dut)

    await launch_kernel(dut, num_blocks=8)

    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[0, 1, 2, 3],
        kernel_done=0,
        msg="running before extra dispatch",
    )

    # Try to launch a new kernel while still running.
    dut.num_blocks.value = 2
    dut.dispatch_en.value = 1
    await step(dut)
    dut.dispatch_en.value = 0

    # Existing kernel must continue unchanged.
    assert_dispatcher(
        dut,
        core_start=0b1111,
        block_indices=[0, 1, 2, 3],
        kernel_done=0,
        msg="dispatch ignored while running",
    )