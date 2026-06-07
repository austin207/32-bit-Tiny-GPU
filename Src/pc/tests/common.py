import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


MASK32 = 0xFFFFFFFF

NZP_N = 0b100
NZP_Z = 0b010
NZP_P = 0b001
NZP_ALL = 0b111


def u32(v: int) -> int:
    return int(v) & MASK32


def pc_value(dut) -> int:
    return int(dut.pc_out.value) & MASK32


def nzp_value(dut) -> int:
    return int(dut.nzp_out.value) & 0x7


async def start_clock(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.block_rst.value = 0
    dut.pc_en.value = 0
    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0


async def reset_dut(dut):
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert pc_value(dut) == 0, f"reset PC expected 0, got {pc_value(dut)}"
    assert nzp_value(dut) == 0, f"reset NZP expected 000, got {nzp_value(dut):03b}"

    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def setup_dut(dut):
    await start_clock(dut)
    init_inputs(dut)
    await reset_dut(dut)


async def step(dut):
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def increment_pc(dut, count=1):
    dut.pc_en.value = 1
    dut.branch_en.value = 0
    dut.nzp_en.value = 0
    for _ in range(count):
        await step(dut)
    dut.pc_en.value = 0
    await Timer(1, unit="ns")


async def store_nzp(dut, flag):
    dut.pc_en.value = 0
    dut.branch_en.value = 0
    dut.nzp_en.value = 1
    dut.nzp_flag.value = flag & 0x7
    await step(dut)
    dut.nzp_en.value = 0
    await Timer(1, unit="ns")


async def branch_cycle(dut, mask, offset):
    dut.pc_en.value = 1
    dut.branch_en.value = 1
    dut.nzp_mask.value = mask & 0x7
    dut.branch_offset.value = offset & 0xFFF
    dut.nzp_en.value = 0
    await step(dut)

    dut.pc_en.value = 0
    dut.branch_en.value = 0
    await Timer(1, unit="ns")


async def block_reset_cycle(dut):
    dut.block_rst.value = 1
    await step(dut)
    dut.block_rst.value = 0
    await Timer(1, unit="ns")


def assert_pc(dut, expected, msg=""):
    got = pc_value(dut)
    exp = u32(expected)
    assert got == exp, f"{msg}: expected PC {exp}, got {got}"


def assert_nzp(dut, expected, msg=""):
    got = nzp_value(dut)
    exp = expected & 0x7
    assert got == exp, f"{msg}: expected NZP {exp:03b}, got {got:03b}"