from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


MASK32 = 0xFFFFFFFF

R0 = 0
THREAD_IDX = 29
BLOCK_IDX = 30
BLOCK_DIM = 31


def u32(v: int) -> int:
    return int(v) & MASK32


def s32(v: int) -> int:
    v = int(v) & MASK32
    return v - 0x100000000 if v & 0x80000000 else v


async def start_clock(dut):
    cocotb_clock = Clock(dut.clk, 10, unit="ns")
    import cocotb
    cocotb.start_soon(cocotb_clock.start())


def init_inputs(dut):
    dut.rst.value = 0
    dut.w_en.value = 0
    dut.w_addr.value = 0
    dut.w_data.value = 0
    dut.r_addr1.value = 0
    dut.r_addr2.value = 0
    dut.r_addr3.value = 0
    dut.threadIdx.value = 0
    dut.blockIdx.value = 0
    dut.blockDim.value = 4


async def reset_dut(dut):
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def setup_dut(dut):
    await start_clock(dut)
    init_inputs(dut)
    await reset_dut(dut)


async def write_reg(dut, addr: int, data: int):
    dut.w_en.value = 1
    dut.w_addr.value = addr & 0x1F
    dut.w_data.value = u32(data)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.w_en.value = 0
    await Timer(1, unit="ns")


async def write_reg_disabled(dut, addr: int, data: int):
    dut.w_en.value = 0
    dut.w_addr.value = addr & 0x1F
    dut.w_data.value = u32(data)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def read_port1(dut, addr: int) -> int:
    dut.r_addr1.value = addr & 0x1F
    await Timer(1, unit="ns")
    return int(dut.r_data1.value) & MASK32


async def read_port2(dut, addr: int) -> int:
    dut.r_addr2.value = addr & 0x1F
    await Timer(1, unit="ns")
    return int(dut.r_data2.value) & MASK32


async def read_port3(dut, addr: int) -> int:
    dut.r_addr3.value = addr & 0x1F
    await Timer(1, unit="ns")
    return int(dut.r_data3.value) & MASK32


async def read_all_ports(dut, a1: int, a2: int, a3: int):
    dut.r_addr1.value = a1 & 0x1F
    dut.r_addr2.value = a2 & 0x1F
    dut.r_addr3.value = a3 & 0x1F
    await Timer(1, unit="ns")
    return (
        int(dut.r_data1.value) & MASK32,
        int(dut.r_data2.value) & MASK32,
        int(dut.r_data3.value) & MASK32,
    )


def set_special_inputs(dut, thread_idx=0, block_idx=0, block_dim=4):
    dut.threadIdx.value = u32(thread_idx)
    dut.blockIdx.value = u32(block_idx)
    dut.blockDim.value = u32(block_dim)


def assert_u32(got, expected, msg=""):
    got = u32(got)
    exp = u32(expected)
    assert got == exp, f"{msg}: expected 0x{exp:08x}, got 0x{got:08x}"