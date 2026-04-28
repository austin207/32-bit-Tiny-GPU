import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.test()
async def test_registers(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.w_en.value = 0
    dut.w_addr.value = 0
    dut.w_data.value = 0
    dut.threadIdx.value = 0
    dut.blockIdx.value = 0
    dut.blockDim.value = 0
    dut.r_addr1.value = 0
    dut.r_addr2.value = 0

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    dut.r_addr1.value = 5
    await RisingEdge(dut.clk)
    assert dut.r_data1.value == 0, f"Expected 0 got {dut.r_data1.value}"
    dut.r_addr2.value = 15
    await RisingEdge(dut.clk)
    assert dut.r_data2.value == 0, f"Expected 0 got {dut.r_data2.value}"

@cocotb.test()
async def test_write_and_read(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.w_en.value = 0
    dut.w_addr.value = 0
    dut.w_data.value = 0
    dut.threadIdx.value = 0
    dut.blockIdx.value = 0
    dut.blockDim.value = 0
    dut.r_addr1.value = 0
    dut.r_addr2.value = 0

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    dut.w_en.value = 1
    dut.w_addr.value = 5
    dut.w_data.value = 42
    await RisingEdge(dut.clk)
    dut.w_en.value = 0
    dut.r_addr1.value = 5
    await RisingEdge(dut.clk)
    assert dut.r_data1.value == 42, f"Expected 42 got {dut.r_data1.value}"

@cocotb.test()
async def test_R0_is_Zero(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.w_en.value = 0
    dut.w_addr.value = 0
    dut.w_data.value = 0
    dut.threadIdx.value = 0
    dut.blockIdx.value = 0
    dut.blockDim.value = 0
    dut.r_addr1.value = 0
    dut.r_addr2.value = 0

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    dut.w_en.value = 1
    dut.w_addr.value = 0
    dut.w_data.value = 99
    await RisingEdge(dut.clk)
    dut.r_addr1.value = 0
    assert dut.r_data1.value == 0, f"Expected 0 got {dut.r_data1.value}"

@cocotb.test()
async def test_Hardware_injected(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.w_en.value = 0
    dut.w_addr.value = 0
    dut.w_data.value = 0
    dut.threadIdx.value = 0
    dut.blockIdx.value = 0
    dut.blockDim.value = 0
    dut.r_addr1.value = 0
    dut.r_addr2.value = 0

    dut.threadIdx.value = 7
    dut.blockIdx.value = 2
    dut.blockDim.value = 4
    dut.r_addr1.value = 29
    dut.r_addr2.value = 30
    await RisingEdge(dut.clk)
    assert dut.r_data1.value == 7, f"Expected 7 got {dut.r_data1.value}"
    assert dut.r_data2.value == 2, f"Expected 2 got {dut.r_data2.value}"