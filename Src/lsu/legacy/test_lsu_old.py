"""
Basic read — assert mem_read_en, give address, simulate memory responding with data, check mem_read_data and done==1
Basic write — assert mem_write_en, give address and write data, simulate memory ack, check done==1 and write_data was sent correctly
Reset during operation — start a read, assert rst before response, check everything clears
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer

@cocotb.test()
async def test_read(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.mem_data_address.value = 0
    dut.mem_write_data.value = 0
    dut.core_en.value = 1

    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.mem_read_en.value = 1
    dut.mem_data_address.value = 42

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.resp_data.value = 1234
    dut.resp_valid.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.mem_read_data.value == 1234, f"Expected mem_read_data to be 1234 got {dut.mem_read_data.value}"
    assert dut.done.value == 1, f"Expected done to be 1 got {dut.done.value}"

@cocotb.test()
async def test_write(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.mem_data_address.value = 0
    dut.mem_write_data.value = 0
    dut.core_en.value = 1

    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.mem_write_en.value = 1
    dut.mem_data_address.value = 42
    dut.mem_write_data.value = 5678

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.resp_valid.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.done.value == 1, f"Expected done to be 1 got {dut.done.value}"
    assert dut.write_data.value == 5678, f"Expected write_data to be 5678 got {dut.write_data.value}"

@cocotb.test()
async def test_reset_during_read(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.mem_data_address.value = 0
    dut.mem_write_data.value = 0
    dut.core_en.value = 1
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.mem_read_en.value = 1
    dut.mem_data_address.value = 42

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.rst.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.mem_read_data.value == 0, f"Expected mem_read_data to be reset to 0 got {dut.mem_read_data.value}"
    assert dut.done.value == 0, f"Expected done to be reset to 0 got {dut.done.value}"