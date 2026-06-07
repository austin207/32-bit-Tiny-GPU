import random
import cocotb

from tests.common import *


RNG_SEED = 0x5C4ED1


@cocotb.test()
async def test_random_nonmem_normal_instructions(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    for i in range(50):
        await run_to_update_nonmem(dut)
        await update_normal_to_fetch(dut)

        assert_state(dut, FETCH, f"random nonmem normal iter={i}")
        assert_outputs(dut, pc_en=1, write_back_en=1, msg=f"random nonmem normal iter={i}")

        # Continue from FETCH directly for next instruction.


@cocotb.test()
async def test_random_memory_wait_lengths(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    for i in range(50):
        await start_block(dut)
        await complete_fetch_to_decode(dut)
        read, write = random.choice([
            (1, 0),  # read
            (0, 1),  # write
            (1, 1),  # both high, still memory path
        ])

        await decode_to_request_mem(
            dut,
            read=read,
            write=write,
        )
        await request_to_wait(dut)

        waits = random.randint(0, 5)
        for j in range(waits):
            dut.lsu_done.value = random.choice([0b0000, 0b0001, 0b0011, 0b0111])
            await step(dut)
            assert_state(dut, WAIT, f"random mem wait iter={i} cycle={j}")

        await wait_to_execute(dut)
        await execute_to_update(dut)
        await update_ret_to_idle(dut)


@cocotb.test()
async def test_random_divergence_masks(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    for i in range(50):
        taken = random.randint(0, 15)

        await run_to_update_nonmem(dut)
        await update_diverge_to_diverge_state(dut, taken_mask=taken)
        await diverge_to_fetch(dut, expected_mask=taken)

        # Finish block cleanly.
        await complete_fetch_to_decode(dut)
        await decode_to_execute_nonmem(dut)
        await execute_to_update(dut)
        await update_ret_to_idle(dut)


@cocotb.test()
async def test_random_sync_saved_masks(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    for i in range(50):
        saved = random.randint(0, 15)

        await run_to_update_nonmem(dut)
        await update_sync_to_sync_pop_state(dut, saved_mask=saved)
        await sync_pop_to_fetch(dut, expected_mask=saved)

        # Finish block cleanly.
        await complete_fetch_to_decode(dut)
        await decode_to_execute_nonmem(dut)
        await execute_to_update(dut)
        await update_ret_to_idle(dut)


@cocotb.test()
async def test_random_update_action_priority(dut):
    random.seed(RNG_SEED + 4)
    await setup_dut(dut)

    for i in range(100):
        await run_to_update_nonmem(dut)

        ret = random.randint(0, 1)
        div = random.randint(0, 1)
        sync = random.randint(0, 1)
        taken = random.randint(0, 15)
        saved = random.randint(0, 15)

        dut.ret.value = ret
        dut.divergence_detected.value = div
        dut.sync_en.value = sync
        dut.taken_mask.value = taken
        dut.saved_mask.value = saved

        await step(dut)

        if ret:
            assert_state(dut, IDLE, f"priority ret iter={i}")
            assert_outputs(dut, block_done=1, write_back_en=1, pc_en=0, msg=f"priority ret iter={i}")

        elif div:
            assert_state(dut, DIVERGE, f"priority div iter={i}")
            assert_outputs(dut, write_back_en=1, pc_en=1, block_done=0, msg=f"priority div iter={i}")
            await diverge_to_fetch(dut, expected_mask=taken)

            await complete_fetch_to_decode(dut)
            await decode_to_execute_nonmem(dut)
            await execute_to_update(dut)
            await update_ret_to_idle(dut)

        elif sync:
            assert_state(dut, SYNC_POP, f"priority sync iter={i}")
            assert_outputs(dut, write_back_en=1, pc_en=1, block_done=0, msg=f"priority sync iter={i}")
            await sync_pop_to_fetch(dut, expected_mask=saved)

            await complete_fetch_to_decode(dut)
            await decode_to_execute_nonmem(dut)
            await execute_to_update(dut)
            await update_ret_to_idle(dut)

        else:
            assert_state(dut, FETCH, f"priority normal iter={i}")
            assert_outputs(dut, write_back_en=1, pc_en=1, block_done=0, msg=f"priority normal iter={i}")

            await complete_fetch_to_decode(dut)
            await decode_to_execute_nonmem(dut)
            await execute_to_update(dut)
            await update_ret_to_idle(dut)

        dut.ret.value = 0
        dut.divergence_detected.value = 0
        dut.sync_en.value = 0