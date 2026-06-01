import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

async def reset_dut(dut):
    dut.rst.value = 1
    dut.push.value = 0
    dut.pop.value = 0
    dut.push_sync_pc.value = 0
    dut.push_saved_mask.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0
    await Timer(1, unit="ns")

@cocotb.test()
async def test_push(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    assert dut.stack_empty.value == 1, \
        f"Expected stack_empty=1 after reset, got {dut.stack_empty.value}"

    dut.push.value = 1
    dut.push_sync_pc.value = 0xDEADBEEF
    dut.push_saved_mask.value = 0b0101
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.push.value = 0

    assert dut.stack_empty.value == 0, \
        f"Expected stack_empty=0 after push, got {dut.stack_empty.value}"
    assert dut.top_sync_pc.value == 0xDEADBEEF, \
        f"Expected top_sync_pc=0xDEADBEEF, got {hex(dut.top_sync_pc.value)}"
    assert dut.top_saved_mask.value == 0b0101, \
        f"Expected top_saved_mask=0101, got {dut.top_saved_mask.value}"

@cocotb.test()
async def test_pop(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Push one entry
    dut.push.value = 1
    dut.push_sync_pc.value = 0xCAFEBABE
    dut.push_saved_mask.value = 0b1010
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.push.value = 0

    # Pop it
    dut.pop.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.pop.value = 0

    assert dut.stack_empty.value == 1, \
        f"Expected stack_empty=1 after pop, got {dut.stack_empty.value}"

    # Pop on empty — should not underflow
    dut.pop.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.pop.value = 0

    assert dut.stack_empty.value == 1, \
        f"Expected stack_empty=1 after pop on empty, got {dut.stack_empty.value}"

@cocotb.test()
async def test_full_and_overflow(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # Push 4 entries to fill the stack
    for idx in range(4):
        dut.push.value = 1
        dut.push_sync_pc.value = 0x1000 + idx
        dut.push_saved_mask.value = idx
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
    dut.push.value = 0
    await Timer(1, unit="ns")

    assert dut.stack_full.value == 1, \
        f"Expected stack_full=1, got {dut.stack_full.value}"
    assert dut.stack_overflow.value == 0, \
        f"Expected stack_overflow=0 when not pushing, got {dut.stack_overflow.value}"

    # Attempt 5th push — overflow
    dut.push.value = 1
    dut.push_sync_pc.value = 0xDEAD
    dut.push_saved_mask.value = 0b1111
    await Timer(1, unit="ns")

    assert dut.stack_overflow.value == 1, \
        f"Expected stack_overflow=1, got {dut.stack_overflow.value}"

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.push.value = 0

    # Top should still show entry 3 (last valid push), not 0xDEAD
    assert dut.top_sync_pc.value == 0x1003, \
        f"Expected top_sync_pc=0x1003, got {hex(dut.top_sync_pc.value)}"
    assert dut.stack_full.value == 1, \
        f"Expected stack_full=1, got {dut.stack_full.value}"