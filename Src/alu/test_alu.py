import cocotb
from cocotb.triggers import Timer

"""Combinational Circuits Like ALU don't need a clock, but we can still use timers to wait for signal propagation.
"""

@cocotb.test()
async def test_ADD(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 5
    dut.operand2.value = 3
    dut.op_select.value = 0x01 # ADD
    await Timer(1, unit="ns")
    assert dut.result.value == 8, f"Expected 8 got {dut.result.value}"

@cocotb.test()
async def test_SUB(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 10
    dut.operand2.value = 4
    dut.op_select.value = 0x02 # SUB
    await Timer(1, unit="ns")
    assert dut.result.value == 6, f"Expected 6 got {dut.result.value}"

@cocotb.test()
async def test_CMP_equal(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 5
    dut.operand2.value = 5
    dut.op_select.value = 0x0D # CMP
    await Timer(1, unit="ns")
    assert dut.nzp_flag.value == 0b010, f"Expected zero flag set got {dut.nzp_flag.value}"

@cocotb.test()
async def test_CMP_greater(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 7
    dut.operand2.value = 3
    dut.op_select.value = 0x0D # CMP
    await Timer(1, unit="ns")
    assert dut.nzp_flag.value == 0b001, f"Expected positive flag set got {dut.nzp_flag.value}"

@cocotb.test()
async def test_CMP_less(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 2
    dut.operand2.value = 9
    dut.op_select.value = 0x0D # CMP
    await Timer(1, unit="ns")
    assert dut.nzp_flag.value == 0b100, f"Expected negative flag set got {dut.nzp_flag.value}"

@cocotb.test()
async def test_NOT(dut):

    dut.operand1.value = 0
    dut.operand2.value = 0
    dut.operand3.value = 0
    dut.op_select.value = 0

    dut.operand1.value = 0x00000000
    dut.op_select.value = 0x0B # NOT
    await Timer(1, unit="ns")
    assert dut.result.value == 0xFFFFFFFF, f"Expected 0xFFFFFFFF got {dut.result.value}"