import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


NUM_CORES = 4
MASK32 = 0xFFFFFFFF


def u32(v: int) -> int:
    return int(v) & MASK32


def as_int(sig, default=0):
    try:
        return int(sig.value)
    except Exception:
        return default


def core_mask(dut) -> int:
    return as_int(dut.core_start) & ((1 << NUM_CORES) - 1)


def kernel_done(dut) -> int:
    return as_int(dut.kernel_done) & 1


def get_block_idx(dut, core_id):
    """
    blockIdx_out is logic [NUM_CORES-1:0][31:0].
    Cocotb exposes it as packed bits in Icarus.
    """
    packed = as_int(dut.blockIdx_out)
    return (packed >> (core_id * 32)) & MASK32


def get_block_indices(dut):
    return [get_block_idx(dut, i) for i in range(NUM_CORES)]


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.num_blocks.value = 0
    dut.blockDim.value = 4
    dut.dispatch_en.value = 0
    dut.block_done.value = 0


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut):
    init_inputs(dut)

    dut.rst.value = 1
    await step(dut)
    await step(dut)

    dut.rst.value = 0
    await step(dut)

    assert_dispatcher(
        dut,
        core_start=0,
        kernel_done=0,
        msg="reset",
    )


async def setup_dut(dut):
    await start_clock(dut)
    await reset_dut(dut)


async def launch_kernel(dut, num_blocks, block_dim=4):
    """
    dispatch_en is a ONE-CYCLE launch pulse.
    """
    dut.num_blocks.value = u32(num_blocks)
    dut.blockDim.value = u32(block_dim)
    dut.dispatch_en.value = 1
    await step(dut)

    dut.dispatch_en.value = 0
    await Timer(1, unit="ns")


async def pulse_block_done(dut, mask):
    dut.block_done.value = mask & ((1 << NUM_CORES) - 1)
    await step(dut)

    dut.block_done.value = 0
    await Timer(1, unit="ns")


async def wait_cycles(dut, n):
    for _ in range(n):
        await step(dut)


def assert_dispatcher(
    dut,
    core_start=None,
    kernel_done=None,
    block_indices=None,
    msg="",
):
    if core_start is not None:
        got = core_mask(dut)
        exp = core_start & ((1 << NUM_CORES) - 1)
        assert got == exp, f"{msg}: core_start expected {exp:04b}, got {got:04b}"

    if kernel_done is not None:
        got = globals()["kernel_done"](dut)
        exp = kernel_done & 1
        assert got == exp, f"{msg}: kernel_done expected {exp}, got {got}"

    if block_indices is not None:
        got = get_block_indices(dut)

        for i, exp in enumerate(block_indices):
            if exp is None:
                continue

            assert got[i] == u32(exp), (
                f"{msg}: core{i} blockIdx expected {u32(exp)}, got {got[i]} "
                f"all_blockIdx={got}"
            )


async def finish_all_active(dut):
    await pulse_block_done(dut, core_mask(dut))