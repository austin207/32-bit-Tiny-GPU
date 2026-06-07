import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


ADDR_NUM_BLOCKS = 0b00
ADDR_BLOCK_DIM  = 0b01
ADDR_START      = 0b10
ADDR_INVALID    = 0b11

MASK32 = 0xFFFFFFFF


def u32(v: int) -> int:
    return int(v) & MASK32


def val(signal) -> int:
    return int(signal.value) & MASK32


def bit(signal) -> int:
    return int(signal.value) & 1


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 0


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def reset_dut(dut):
    init_inputs(dut)

    dut.rst.value = 1
    await step(dut)
    await step(dut)

    assert_dcr(
        dut,
        num_blocks=0,
        blockDim=0,
        start=0,
        msg="reset",
    )

    dut.rst.value = 0
    await step(dut)


async def setup_dut(dut):
    await start_clock(dut)
    await reset_dut(dut)


async def write_dcr(dut, addr, data):
    """
    Performs one DCR write cycle and leaves outputs available for checking.

    Note:
      If addr == START, start is high after this cycle.
      It clears only on the next cycle unless start write is held active again.
    """
    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = addr & 0x3
    dut.dcr_data.value = u32(data)
    await step(dut)

    dut.dcr_write_en.value = 0
    await Timer(1, unit="ns")


async def idle_cycle(dut):
    dut.dcr_write_en.value = 0
    await step(dut)


def assert_dcr(
    dut,
    num_blocks=None,
    blockDim=None,
    start=None,
    msg="",
):
    if num_blocks is not None:
        got = val(dut.num_blocks)
        exp = u32(num_blocks)
        assert got == exp, (
            f"{msg}: num_blocks expected 0x{exp:08x}, got 0x{got:08x}"
        )

    if blockDim is not None:
        got = val(dut.blockDim)
        exp = u32(blockDim)
        assert got == exp, (
            f"{msg}: blockDim expected 0x{exp:08x}, got 0x{got:08x}"
        )

    if start is not None:
        got = bit(dut.start)
        exp = start & 1
        assert got == exp, (
            f"{msg}: start expected {exp}, got {got}"
        )