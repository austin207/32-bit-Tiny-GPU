import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


async def init_inputs(dut):
    dut.pc_en.value = 0
    dut.branch_en.value = 0
    dut.branch_offset.value = 0
    dut.nzp_en.value = 0
    dut.nzp_flag.value = 0
    dut.nzp_mask.value = 0


async def reset_dut(dut):
    dut.rst.value = 1
    await Timer(1, unit="ns")
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 0, f"Expected PC reset to 0, got {dut.pc_out.value}"

    dut.rst.value = 0
    await Timer(1, unit="ns")


@cocotb.test()
async def test_reset(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await init_inputs(dut)
    await reset_dut(dut)


@cocotb.test()
async def test_increment(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await init_inputs(dut)
    await reset_dut(dut)

    dut.pc_en.value = 1

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 1, f"Expected PC to increment to 1, got {dut.pc_out.value}"

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 2, f"Expected PC to increment to 2, got {dut.pc_out.value}"

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 3, f"Expected PC to increment to 3, got {dut.pc_out.value}"


@cocotb.test()
async def test_nzp_store(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await init_inputs(dut)
    await reset_dut(dut)

    # First normal PC increment: PC = 1
    dut.pc_en.value = 1
    dut.branch_en.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 1, f"Expected PC to be 1, got {dut.pc_out.value}"

    # Store NZP without updating PC
    dut.pc_en.value = 0
    dut.nzp_en.value = 1
    dut.nzp_flag.value = 0b001
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 1, f"Expected PC to stay 1 during NZP store, got {dut.pc_out.value}"

    # Branch should now be taken: PC = 1 + 5 = 6
    dut.nzp_en.value = 0
    dut.pc_en.value = 1
    dut.branch_en.value = 1
    dut.nzp_mask.value = 0b001
    dut.branch_offset.value = 5

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 6, f"Expected PC to branch to 6, got {dut.pc_out.value}"


@cocotb.test()
async def test_branch_taken(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await init_inputs(dut)
    await reset_dut(dut)

    # PC = 1
    dut.pc_en.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 1, f"Expected PC to be 1, got {dut.pc_out.value}"

    # Store NZP = positive, without incrementing PC
    dut.pc_en.value = 0
    dut.nzp_en.value = 1
    dut.nzp_flag.value = 0b001
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Branch on positive: PC = 1 + 5 = 6
    dut.nzp_en.value = 0
    dut.pc_en.value = 1
    dut.branch_en.value = 1
    dut.nzp_mask.value = 0b001
    dut.branch_offset.value = 5

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 6, f"Expected PC to branch to 6, got {dut.pc_out.value}"


@cocotb.test()
async def test_branch_not_taken(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await init_inputs(dut)
    await reset_dut(dut)

    # PC = 1
    dut.pc_en.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 1, f"Expected PC to be 1, got {dut.pc_out.value}"

    # Store NZP = positive, without incrementing PC
    dut.pc_en.value = 0
    dut.nzp_en.value = 1
    dut.nzp_flag.value = 0b001
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    # Mask checks negative instead of positive, so branch is not taken.
    # PC should increment normally: PC = 1 + 1 = 2
    dut.nzp_en.value = 0
    dut.pc_en.value = 1
    dut.branch_en.value = 1
    dut.nzp_mask.value = 0b100
    dut.branch_offset.value = 5

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.pc_out.value == 2, f"Expected PC to increment to 2, got {dut.pc_out.value}"