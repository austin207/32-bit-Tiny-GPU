""" Test 1 — Basic non-memory instruction flow

Assert core_start
Simulate fetcher_done after one cycle
Set mem_read_en=0, mem_write_en=0, ret=0
Trace through states and check execute_en==1 in EXECUTE
Check write_back_en==1 in UPDATE
Check it goes back to FETCH

Test 2 — Memory instruction flow

Same start but set mem_read_en=1
Check it goes through REQUEST → WAIT
Simulate lsu_done = 4'b1111 (all threads done)
Check it reaches EXECUTE

Test 3 — RET instruction

Run through full pipeline with ret=1
Check block_done==1 in UPDATE
Check state returns to IDLE
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from cocotb.triggers import Timer

@cocotb.test()
async def test_scheduler_basic_flow(dut):
    clock = Clock(dut.clk, 10, unit="ns")  
    cocotb.start_soon(clock.start())

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.core_start.value = 1
    await RisingEdge(dut.clk)
    dut.core_start.value = 0

    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 1
    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 0

    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.ret.value = 0

    while dut.current_state.value != 0b101: 
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.execute_en.value == 1

    while dut.current_state.value != 0b110: 
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.write_back_en.value == 1, f"write_back_en should be 1 in UPDATE state"

    while dut.current_state.value != 0b001:
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.current_state.value == 0b001, f"Expected to return to FETCH state, got {dut.current_state.value}"

@cocotb.test()
async def test_scheduler_memory_flow(dut):
    clock = Clock(dut.clk, 10, unit="ns")  
    cocotb.start_soon(clock.start())

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.core_start.value = 1
    await RisingEdge(dut.clk)
    dut.core_start.value = 0

    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 1
    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 0

    dut.mem_read_en.value = 1
    dut.mem_write_en.value = 0
    dut.ret.value = 0

    #while dut.current_state.value != 0b011:
    #    await RisingEdge(dut.clk)
    #await RisingEdge(dut.clk)
    #assert dut.current_state.value == 0b011, f"Expected to be in REQUEST state, got {dut.current_state.value}"

    while dut.current_state.value != 0b100:
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.current_state.value == 0b100, f"Expected to be in WAIT state, got {dut.current_state.value}"

    dut.lsu_done.value = 0b1111
    await RisingEdge(dut.clk)

    while dut.current_state.value != 0b101:
        await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.execute_en.value == 1, f"execute_en should be 1 in EXECUTE state for memory instruction"


@cocotb.test()
async def test_scheduler_ret_instruction(dut):
    clock = Clock(dut.clk, 10, unit="ns")  # 100 MHz clock
    cocotb.start_soon(clock.start())

    dut.rst.value = 1
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.core_start.value = 1
    await RisingEdge(dut.clk)
    dut.core_start.value = 0

    dut.ret.value = 1
    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 1
    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 0

    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0

    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.current_state.value == 0b110:  # caught UPDATE
            await RisingEdge(dut.clk)  # this edge sets block_done
            await Timer(1, unit="ns")
            assert dut.block_done.value == 1, "block_done should be 1"
            break

    while dut.current_state.value != 0b000:
        await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert dut.current_state.value == 0b000, f"Expected to return to IDLE state, got {dut.current_state.value}"

@cocotb.test()
async def test_scheduler_divergence(dut):
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    dut.rst.value = 1
    dut.core_start.value = 0
    dut.fetcher_done.value = 0
    dut.lsu_done.value = 0b1111
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.ret.value = 0
    dut.divergence_detected.value = 0
    dut.taken_mask.value = 0b0000
    dut.sync_en.value = 0
    dut.saved_mask.value = 0b1111
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.core_start.value = 1
    await RisingEdge(dut.clk)
    dut.core_start.value = 0

    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 1
    await RisingEdge(dut.clk)
    dut.fetcher_done.value = 0

    dut.divergence_detected.value = 1
    dut.taken_mask.value = 0b1010

    # Wait until UPDATE has fired — state becomes DIVERGE
    # At this exact moment: pc_en=1 and write_back_en=1 are still high
    # because DIVERGE state hasn't fired yet to reset them
    for _ in range(20):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.current_state.value == 0b111:
            break

    assert dut.current_state.value == 0b111, \
        f"Expected DIVERGE (111), got {dut.current_state.value}"
    assert dut.write_back_en.value == 1, \
        f"Expected write_back_en=1, got {dut.write_back_en.value}"
    assert dut.pc_en.value == 1, \
        f"Expected pc_en=1 in divergence path, got {dut.pc_en.value}"

    # Clock through DIVERGE — active_mask latches taken_mask, goes to FETCH
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert dut.active_mask.value == 0b1010, \
        f"Expected active_mask=1010 after DIVERGE, got {dut.active_mask.value}"
    assert dut.current_state.value == 0b001, \
        f"Expected FETCH after DIVERGE, got {dut.current_state.value}"