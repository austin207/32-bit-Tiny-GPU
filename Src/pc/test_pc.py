import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer

@cocotb.test()
async def test_reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0

    dut.rst.value = 1
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    assert dut.pc_out.value == 0, f"Expected PC to be reset to 0 got {dut.pc_out.value}"

@cocotb.test()
async def test_increment(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0

    dut.rst.value = 1
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 1, f"Expected PC to increment to 1 got {dut.pc_out.value}"
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 2, f"Expected PC to increment to 2 got {dut.pc_out.value}"
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 3, f"Expected PC to increment to 3 got {dut.pc_out.value}"

@cocotb.test()
async def test_nzp_store(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0

    dut.rst.value = 1
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    dut.nzp_en.value = 1
    dut.nzp_flag.value = 0b001
    await RisingEdge(dut.clk)

    dut.nzp_en.value = 0
    dut.branch_en.value = 1
    dut.nzp_mask.value = 0b001
    dut.branch_offset.value = 5
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 6, f"Expected PC to be incremented got {dut.pc_out.value}"

@cocotb.test()
async def test_branch_taken(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0

    dut.rst.value = 1
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    dut.nzp_en.value = 1
    dut.nzp_flag.value = 0b001
    await RisingEdge(dut.clk)
    dut.nzp_en.value = 0
    dut.branch_en.value = 1
    dut.nzp_mask.value = 0b001
    dut.branch_offset.value = 5
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 6, f"Expected PC to be incremented got {dut.pc_out.value}"

@cocotb.test()
async def test_branch_not_taken(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0

    dut.rst.value = 1
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    dut.nzp_en.value = 1
    dut.nzp_flag.value = 0b001
    await RisingEdge(dut.clk)
    dut.nzp_en.value = 0
    dut.branch_en.value = 1
    dut.nzp_mask.value = 0b100
    dut.branch_offset.value = 5
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 2, f"Expected PC to be incremented got {dut.pc_out.value}"
