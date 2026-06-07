import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_defaults(dut):
    await setup_dut(dut)

    assert_state(dut, IDLE, "reset")
    assert_outputs(
        dut,
        fetcher_en=0,
        lsu_en=0,
        execute_en=0,
        write_back_en=0,
        block_done=0,
        pc_en=0,
        active_mask=ALL_THREADS,
        msg="reset defaults",
    )


@cocotb.test()
async def test_idle_holds_without_core_start(dut):
    await setup_dut(dut)

    for i in range(5):
        await step(dut)
        assert_state(dut, IDLE, f"idle hold cycle {i}")
        assert_outputs(dut, fetcher_en=0, block_done=0, pc_en=0, msg=f"idle cycle {i}")


@cocotb.test()
async def test_core_start_enters_fetch(dut):
    await setup_dut(dut)

    await start_block(dut)


@cocotb.test()
async def test_fetch_holds_until_fetcher_done(dut):
    await setup_dut(dut)

    await start_block(dut)

    for i in range(3):
        dut.fetcher_done.value = 0
        await step(dut)
        assert_state(dut, FETCH, f"fetch hold cycle {i}")
        assert_outputs(dut, fetcher_en=1, msg=f"fetch hold cycle {i}")


@cocotb.test()
async def test_fetch_done_goes_to_decode(dut):
    await setup_dut(dut)

    await start_block(dut)
    await complete_fetch_to_decode(dut)


@cocotb.test()
async def test_non_memory_instruction_flow(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_normal_to_fetch(dut)


@cocotb.test()
async def test_memory_read_instruction_flow(dut):
    await setup_dut(dut)

    await run_to_update_mem(dut, read=True, write=False)
    await update_normal_to_fetch(dut)


@cocotb.test()
async def test_memory_write_instruction_flow(dut):
    await setup_dut(dut)

    await run_to_update_mem(dut, read=False, write=True)
    await update_normal_to_fetch(dut)


@cocotb.test()
async def test_request_state_asserts_lsu_en_one_cycle(dut):
    await setup_dut(dut)

    await start_block(dut)
    await complete_fetch_to_decode(dut)
    await decode_to_request_mem(dut, read=True, write=False)
    await request_to_wait(dut)

    await step(dut)
    assert_state(dut, WAIT, "after request")
    assert_outputs(dut, lsu_en=0, msg="lsu_en pulse cleared")


@cocotb.test()
async def test_wait_holds_until_all_lsu_done(dut):
    await setup_dut(dut)

    await start_block(dut)
    await complete_fetch_to_decode(dut)
    await decode_to_request_mem(dut, read=True, write=False)
    await request_to_wait(dut)

    for value in [0b0000, 0b0001, 0b0011, 0b0111, 0b1011]:
        dut.lsu_done.value = value
        await step(dut)
        assert_state(dut, WAIT, f"wait partial lsu_done={value:04b}")

    await wait_to_execute(dut)


@cocotb.test()
async def test_execute_en_is_one_cycle_pulse(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)

    await step(dut)
    assert_outputs(dut, execute_en=0, msg="execute_en cleared after EXECUTE")


@cocotb.test()
async def test_update_normal_asserts_writeback_and_pc_en(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_normal_to_fetch(dut)


@cocotb.test()
async def test_ret_instruction_sets_block_done_and_returns_idle(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_ret_to_idle(dut)


@cocotb.test()
async def test_ret_priority_over_divergence_and_sync(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)

    dut.ret.value = 1
    dut.divergence_detected.value = 1
    dut.sync_en.value = 1
    dut.taken_mask.value = 0b1010
    dut.saved_mask.value = 0b0101

    await step(dut)

    assert_state(dut, IDLE, "ret priority")
    assert_outputs(
        dut,
        write_back_en=1,
        block_done=1,
        pc_en=0,
        active_mask=ALL_THREADS,
        msg="ret priority",
    )


@cocotb.test()
async def test_divergence_flow_updates_active_mask(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_diverge_to_diverge_state(dut, taken_mask=0b1010)
    await diverge_to_fetch(dut, expected_mask=0b1010)


@cocotb.test()
async def test_sync_flow_restores_saved_mask(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_sync_to_sync_pop_state(dut, saved_mask=0b0110)
    await sync_pop_to_fetch(dut, expected_mask=0b0110)


@cocotb.test()
async def test_divergence_priority_over_sync(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)

    dut.ret.value = 0
    dut.divergence_detected.value = 1
    dut.taken_mask.value = 0b0011
    dut.sync_en.value = 1
    dut.saved_mask.value = 0b1100

    await step(dut)

    assert_state(dut, DIVERGE, "divergence priority over sync")
    assert_outputs(dut, write_back_en=1, pc_en=1, msg="divergence priority")

    await diverge_to_fetch(dut, expected_mask=0b0011)


@cocotb.test()
async def test_core_start_resets_active_mask_to_all_ones(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_diverge_to_diverge_state(dut, taken_mask=0b0010)
    await diverge_to_fetch(dut, expected_mask=0b0010)

    # Finish current block with RET.
    await complete_fetch_to_decode(dut)
    await decode_to_execute_nonmem(dut)
    await execute_to_update(dut)
    await update_ret_to_idle(dut)

    # New block should restore active_mask to all threads.
    await start_block(dut)
    assert_outputs(dut, active_mask=ALL_THREADS, msg="new block restores active mask")


@cocotb.test()
async def test_block_done_is_one_cycle_pulse(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_ret_to_idle(dut)

    await step(dut)
    assert_outputs(dut, block_done=0, msg="block_done pulse cleared")
    assert_state(dut, IDLE, "after block_done pulse")


@cocotb.test()
async def test_pc_en_only_asserts_in_update_non_ret_paths(dut):
    await setup_dut(dut)

    await run_to_update_nonmem(dut)
    await update_normal_to_fetch(dut)

    await complete_fetch_to_decode(dut)
    await decode_to_execute_nonmem(dut)
    await execute_to_update(dut)
    await update_sync_to_sync_pop_state(dut, saved_mask=0b1111)

    await sync_pop_to_fetch(dut, expected_mask=0b1111)
    assert_outputs(dut, pc_en=0, msg="pc_en cleared after sync_pop")