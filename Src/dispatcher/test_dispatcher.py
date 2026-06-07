import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def as_int(sig, default=0):
    try:
        return int(sig.value)
    except Exception:
        return default


def get_block_idx(dut, core_id):
    """
    blockIdx_out is logic [NUM_CORES-1:0][31:0].
    Cocotb exposes it as packed bits in Icarus.
    """
    packed = as_int(dut.blockIdx_out)
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
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def launch_kernel(dut, num_blocks, block_dim=4):
    """
    dispatch_en is a ONE-CYCLE launch pulse.
    Do not hold it high, or the dispatcher may start a new kernel after finishing.
    """
    dut.num_blocks.value = num_blocks
    dut.blockDim.value = block_dim
    dut.dispatch_en.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dispatch_en.value = 0

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def pulse_block_done(dut, mask):
    dut.block_done.value = mask
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.block_done.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def wait_cycles(dut, n):
    for _ in range(n):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


@cocotb.test()
async def test_single_block(dut):
    """
    1 block should launch on core0.
    kernel_done should assert after core0 raises block_done.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    await launch_kernel(dut, num_blocks=1, block_dim=4)

    assert as_int(dut.core_start) == 0b0001, (
        f"Expected core0 active, got {as_int(dut.core_start):04b}"
    )
    assert get_block_idx(dut, 0) == 0, (
        f"Expected core0 blockIdx=0, got {get_block_idx(dut, 0)}"
    )
    assert as_int(dut.kernel_done) == 0, (
        f"kernel_done should not assert before block_done, got {as_int(dut.kernel_done)}"
    )

    await pulse_block_done(dut, 0b0001)

    assert as_int(dut.kernel_done) == 1, (
        f"Expected kernel_done=1, got {as_int(dut.kernel_done)}"
    )
    assert as_int(dut.core_start) == 0b0000, (
        f"Expected all cores idle, got {as_int(dut.core_start):04b}"
    )


@cocotb.test()
async def test_multiple_blocks_multiple_cores(dut):
    """
    4 blocks should launch across all 4 cores:
      core0 -> block 0
      core1 -> block 1
      core2 -> block 2
      core3 -> block 3
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    await launch_kernel(dut, num_blocks=4, block_dim=4)

    assert as_int(dut.core_start) == 0b1111, (
        f"Expected all cores active, got {as_int(dut.core_start):04b}"
    )

    assert get_block_idx(dut, 0) == 0, f"core0 expected block 0, got {get_block_idx(dut, 0)}"
    assert get_block_idx(dut, 1) == 1, f"core1 expected block 1, got {get_block_idx(dut, 1)}"
    assert get_block_idx(dut, 2) == 2, f"core2 expected block 2, got {get_block_idx(dut, 2)}"
    assert get_block_idx(dut, 3) == 3, f"core3 expected block 3, got {get_block_idx(dut, 3)}"

    await pulse_block_done(dut, 0b1111)

    assert as_int(dut.kernel_done) == 1, (
        f"Expected kernel_done=1, got {as_int(dut.kernel_done)}"
    )
    assert as_int(dut.core_start) == 0b0000, (
        f"Expected all cores idle, got {as_int(dut.core_start):04b}"
    )


@cocotb.test()
async def test_more_blocks_than_cores(dut):
    """
    6 blocks with 4 cores.

    Initial dispatch:
      core0 -> block 0
      core1 -> block 1
      core2 -> block 2
      core3 -> block 3

    Then:
      core0 finishes -> gets block 4
      core1 finishes -> gets block 5

    Then all remaining active cores finish -> kernel_done.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    await launch_kernel(dut, num_blocks=6, block_dim=4)

    assert as_int(dut.core_start) == 0b1111, (
        f"Expected all cores active, got {as_int(dut.core_start):04b}"
    )

    assert get_block_idx(dut, 0) == 0
    assert get_block_idx(dut, 1) == 1
    assert get_block_idx(dut, 2) == 2
    assert get_block_idx(dut, 3) == 3

    # core0 finishes block 0, should receive block 4
    await pulse_block_done(dut, 0b0001)

    assert as_int(dut.core_start) == 0b1111, (
        f"Expected all cores still active after assigning block 4, got {as_int(dut.core_start):04b}"
    )
    assert get_block_idx(dut, 0) == 4, (
        f"Expected core0 to get block 4, got {get_block_idx(dut, 0)}"
    )

    # core1 finishes block 1, should receive block 5
    await pulse_block_done(dut, 0b0010)

    assert as_int(dut.core_start) == 0b1111, (
        f"Expected all cores still active after assigning block 5, got {as_int(dut.core_start):04b}"
    )
    assert get_block_idx(dut, 1) == 5, (
        f"Expected core1 to get block 5, got {get_block_idx(dut, 1)}"
    )

    # Remaining active blocks:
    # core0 -> block4
    # core1 -> block5
    # core2 -> block2
    # core3 -> block3
    await pulse_block_done(dut, 0b1111)

    assert as_int(dut.kernel_done) == 1, (
        f"Expected kernel_done=1, got {as_int(dut.kernel_done)}"
    )
    assert as_int(dut.core_start) == 0b0000, (
        f"Expected all cores idle, got {as_int(dut.core_start):04b}"
    )


@cocotb.test()
async def test_back_to_back_kernel_launches(dut):
    """
    Verify dispatcher can run one kernel, finish, then accept a new launch pulse.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    # First kernel: 1 block
    await launch_kernel(dut, num_blocks=1, block_dim=4)
    assert as_int(dut.core_start) == 0b0001
    await pulse_block_done(dut, 0b0001)
    assert as_int(dut.kernel_done) == 1

    # Second kernel: 4 blocks
    await launch_kernel(dut, num_blocks=4, block_dim=4)

    assert as_int(dut.kernel_done) == 0, (
        "kernel_done should clear on new launch"
    )
    assert as_int(dut.core_start) == 0b1111
    assert get_block_idx(dut, 0) == 0
    assert get_block_idx(dut, 1) == 1
    assert get_block_idx(dut, 2) == 2
    assert get_block_idx(dut, 3) == 3

    await pulse_block_done(dut, 0b1111)

    assert as_int(dut.kernel_done) == 1
    assert as_int(dut.core_start) == 0b0000