import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer

@cocotb.test()
async def test_basic_fetch(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.core_en.value = 1
    dut.pc_value.value = 5  
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.req_valid.value == 1, f"Expected req_valid to be 1 got {dut.req_valid.value}"

    dut.resp_valid.value = 1
    assert dut.req_addr.value == 5, f"Expected req_addr to be 5 got {dut.req_addr.value}"
    dut.resp_data.value = 0xDEADBEEF
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.done.value == 1, f"Expected done to be 1 got {dut.done.value}"
    assert dut.instruction.value == 0xDEADBEEF, f"Expected instruction to be 0xDEADBEEF got {dut.instruction.value}"

@cocotb.test()
async def test_memory_mutlicycle(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.core_en.value = 1
    dut.pc_value.value = 5 
    await RisingEdge(dut.clk)
    assert dut.req_valid.value == 1, f"Expected req_valid to be 1 got {dut.req_valid.value}"

    dut.resp_valid.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.done.value == 0, f"Expected done to be 0 got {dut.done.value}"

    dut.resp_valid.value = 1
    dut.resp_data.value = 0xCAFEBABE
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.done.value == 1, f"Expected done to be 1 got {dut.done.value}"
    assert dut.instruction.value == 0xCAFEBABE, f"Expected instruction to be 0xCAFEBABE got {dut.instruction.value}"

@cocotb.test()
async def test_reset_during_fetch(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.core_en.value = 1
    dut.pc_value.value = 5 
    await RisingEdge(dut.clk)
    assert dut.req_valid.value == 1, f"Expected req_valid to be 1 got {dut.req_valid.value}"

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.req_valid.value == 0, f"Expected req_valid to be 0 got {dut.req_valid.value}"
    assert dut.done.value == 0, f"Expected done to be 0 got {dut.done.value}"
    assert dut.instruction.value == 0, f"Expected instruction to be 0 got {dut.instruction.value}"