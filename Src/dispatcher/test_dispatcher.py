import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def get_block_idx(dut, core_id):
    packed = int(dut.blockIdx_out.value)
    return (packed >> (core_id * 32)) & 0xFFFFFFFF


async def reset_dut(dut):
    dut.rst.value = 1
    dut.dispatch_en.value = 0
    dut.num_blocks.value = 0
    dut.blockDim.value = 4
    dut.block_done.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    dut.rst.value = 0
    await Timer(1, unit="ns")


@cocotb.test()
async def test_single_block(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    dut.num_blocks.value = 1
    dut.dispatch_en.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.core_start.value == 0b0001, f"Expected core 0 to start, got {dut.core_start.value}"
    assert get_block_idx(dut, 0) == 0, f"Expected blockIdx 0, got {get_block_idx(dut, 0)}"

    dut.block_done.value = 0b0001
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.block_done.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.kernel_done.value == 1, f"Expected kernel_done=1, got {dut.kernel_done.value}"


@cocotb.test()
async def test_multiple_blocks_multiple_cores(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    dut.num_blocks.value = 4
    dut.dispatch_en.value = 1

    for _ in range(4):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    assert dut.core_start.value == 0b1111, f"Expected all cores to start, got {dut.core_start.value}"
    assert get_block_idx(dut, 0) == 0, f"Expected blockIdx 0 for core 0, got {get_block_idx(dut, 0)}"
    assert get_block_idx(dut, 1) == 1, f"Expected blockIdx 1 for core 1, got {get_block_idx(dut, 1)}"
    assert get_block_idx(dut, 2) == 2, f"Expected blockIdx 2 for core 2, got {get_block_idx(dut, 2)}"
    assert get_block_idx(dut, 3) == 3, f"Expected blockIdx 3 for core 3, got {get_block_idx(dut, 3)}"

    dut.block_done.value = 0b1111
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.block_done.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.kernel_done.value == 1, f"Expected kernel_done=1, got {dut.kernel_done.value}"


@cocotb.test()
async def test_more_blocks_than_cores(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    dut.num_blocks.value = 6
    dut.dispatch_en.value = 1

    for _ in range(4):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

    assert dut.core_start.value == 0b1111, f"Expected all cores to start, got {dut.core_start.value}"
    assert get_block_idx(dut, 0) == 0
    assert get_block_idx(dut, 1) == 1
    assert get_block_idx(dut, 2) == 2
    assert get_block_idx(dut, 3) == 3

    dut.block_done.value = 0b0001
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.block_done.value = 0b0000
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert get_block_idx(dut, 0) == 4, f"Expected core 0 to get block 4, got {get_block_idx(dut, 0)}"

    dut.block_done.value = 0b0010
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.block_done.value = 0b0000
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert get_block_idx(dut, 1) == 5, f"Expected core 1 to get block 5, got {get_block_idx(dut, 1)}"

    dut.block_done.value = 0b1111
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.block_done.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.kernel_done.value == 1, f"Expected kernel_done=1, got {dut.kernel_done.value}"