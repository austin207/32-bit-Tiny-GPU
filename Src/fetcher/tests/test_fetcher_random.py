import random
import cocotb

from tests.common import *


RNG_SEED = 0xF37C4E


def rand_u32():
    return random.getrandbits(32)


@cocotb.test()
async def test_random_fetches_with_random_waits(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    for i in range(100):
        pc = rand_u32()
        data = rand_u32()
        wait_cycles = random.randint(0, 5)

        await issue_request(dut, pc=pc)
        await wait_no_response(dut, cycles=wait_cycles)
        await complete_response(dut, data=data)

        assert_fetch_outputs(
            dut,
            req_addr=pc,
            instruction=data,
            done=1,
            msg=f"random fetch iter={i}",
        )

        await step(dut)


@cocotb.test()
async def test_random_idle_response_noise_ignored(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    for i in range(100):
        dut.core_en.value = 0
        dut.resp_valid.value = random.randint(0, 1)
        dut.resp_data.value = rand_u32()
        dut.pc_value.value = rand_u32()

        await step(dut)

        assert_fetch_outputs(
            dut,
            req_valid=0,
            done=0,
            instruction=0,
            msg=f"random idle noise iter={i}",
        )


@cocotb.test()
async def test_random_reset_during_pending_fetch(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    for i in range(50):
        pc = rand_u32()

        await issue_request(dut, pc=pc)
        await wait_no_response(dut, cycles=random.randint(0, 3))

        dut.rst.value = 1
        await step(dut)

        assert_fetch_outputs(
            dut,
            req_valid=0,
            done=0,
            req_addr=0,
            instruction=0,
            msg=f"random reset pending iter={i}",
        )

        dut.rst.value = 0
        await step(dut)


@cocotb.test()
async def test_random_back_to_back_fetches(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    last_data = 0

    for i in range(100):
        pc = rand_u32()
        data = rand_u32()

        await issue_request(dut, pc=pc)
        await complete_response(dut, data=data)

        last_data = data

        assert_fetch_outputs(
            dut,
            req_addr=pc,
            instruction=last_data,
            done=1,
            msg=f"random back-to-back iter={i}",
        )

        await step(dut)


@cocotb.test()
async def test_random_core_en_held_high_relaunch_behavior(dut):
    random.seed(RNG_SEED + 4)
    await setup_dut(dut)

    for i in range(50):
        pc0 = rand_u32()
        pc1 = rand_u32()
        data0 = rand_u32()

        await issue_request(dut, pc=pc0, keep_core_en=True)

        dut.resp_valid.value = 1
        dut.resp_data.value = data0
        await step(dut)

        assert_fetch_outputs(
            dut,
            done=1,
            instruction=data0,
            msg=f"random held core_en response iter={i}",
        )

        dut.resp_valid.value = 0
        dut.pc_value.value = pc1
        await step(dut)

        assert_fetch_outputs(
            dut,
            req_valid=1,
            req_addr=pc1,
            done=0,
            msg=f"random held core_en relaunch iter={i}",
        )

        dut.core_en.value = 0

        # Complete the relaunched request so the FSM returns to IDLE before next iteration.
        await complete_response(dut, data=rand_u32())
        await step(dut)