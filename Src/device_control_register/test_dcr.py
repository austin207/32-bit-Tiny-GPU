import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

@cocotb.test()
async def test_write_num_blocks(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = 8
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.num_blocks.value == 8, f"Expected num_blocks=8, got {dut.num_blocks.value}"

@cocotb.test()
async def test_write_blockDim(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.blockDim.value == 4, f"Expected blockDim=4, got {dut.blockDim.value}"

@cocotb.test()
async def test_start_pulse(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.start.value == 1, f"Expected start=1, got {dut.start.value}"

    dut.dcr_write_en.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.start.value == 0, f"Expected start=0 after deassert, got {dut.start.value}"