import random
import cocotb

from tests.common import *


RNG_SEED = 0xC0A71011


def rand_u32():
    return random.getrandbits(32)


@cocotb.test()
async def test_random_single_requests_all_threads(dut):
    random.seed(RNG_SEED)
    await setup_dut(dut)

    for i in range(100):
        thread_id = random.randint(0, THREADS_PER_CORE - 1)
        rw = random.randint(0, 1)
        addr = rand_u32()
        data = rand_u32()
        resp = rand_u32()

        await issue_single_request(dut, thread_id=thread_id, addr=addr, rw=rw, data=data)

        assert_mem_req(
            dut,
            valid=1,
            addr=addr,
            rw=rw,
            data=data if rw == 0 else None,
            msg=f"random single request iter={i}",
        )

        await memory_response(dut, data=resp)
        assert_only_thread_response(
            dut,
            thread_id,
            data=resp,
            msg=f"random single response iter={i}",
        )

        await step(dut)


@cocotb.test()
async def test_random_simultaneous_requests_service_all(dut):
    random.seed(RNG_SEED + 1)
    await setup_dut(dut)

    for i in range(50):
        # reset between trials to make expected first winner simple.
        dut.rst.value = 1
        await step(dut)
        dut.rst.value = 0
        await step(dut)

        threads = sorted(random.sample(range(THREADS_PER_CORE), random.randint(1, THREADS_PER_CORE)))

        reqs = []
        expected_by_thread = {}

        for t in threads:
            req = {
                "thread": t,
                "addr": rand_u32(),
                "rw": random.randint(0, 1),
                "data": rand_u32(),
            }
            reqs.append(req)
            expected_by_thread[t] = req

        await pulse_requests(dut, reqs)

        for idx, t in enumerate(threads):
            if idx > 0:
                await step(dut)

            req = expected_by_thread[t]
            assert_mem_req(
                dut,
                valid=1,
                addr=req["addr"],
                rw=req["rw"],
                data=req["data"] if req["rw"] == 0 else None,
                msg=f"random simultaneous iter={i} T{t}",
            )

            resp = rand_u32()
            await memory_response(dut, data=resp)
            assert_only_thread_response(
                dut,
                t,
                data=resp,
                msg=f"random simultaneous response iter={i} T{t}",
            )


@cocotb.test()
async def test_random_buffered_requests_while_waiting(dut):
    random.seed(RNG_SEED + 2)
    await setup_dut(dut)

    for i in range(50):
        dut.rst.value = 1
        await step(dut)
        dut.rst.value = 0
        await step(dut)

        first_thread = random.randint(0, THREADS_PER_CORE - 1)
        first_addr = rand_u32()
        first_rw = random.randint(0, 1)
        first_data = rand_u32()

        await issue_single_request(
            dut,
            thread_id=first_thread,
            addr=first_addr,
            rw=first_rw,
            data=first_data,
        )

        assert_mem_req(
            dut,
            valid=1,
            addr=first_addr,
            rw=first_rw,
            data=first_data if first_rw == 0 else None,
            msg=f"random buffered first iter={i}",
        )

        # Pick a different thread to fire during WAIT.
        other_threads = [t for t in range(THREADS_PER_CORE) if t != first_thread]
        second_thread = random.choice(other_threads)
        second_addr = rand_u32()
        second_rw = random.randint(0, 1)
        second_data = rand_u32()

        await pulse_requests(dut, [
            {
                "thread": second_thread,
                "addr": second_addr,
                "rw": second_rw,
                "data": second_data,
            }
        ])

        # First request still in-flight.
        assert_mem_req(
            dut,
            valid=1,
            addr=first_addr,
            rw=first_rw,
            data=first_data if first_rw == 0 else None,
            msg=f"random buffered still first iter={i}",
        )

        first_resp = rand_u32()
        await memory_response(dut, data=first_resp)
        assert_only_thread_response(
            dut,
            first_thread,
            data=first_resp,
            msg=f"random buffered first response iter={i}",
        )

        await step(dut)

        assert_mem_req(
            dut,
            valid=1,
            addr=second_addr,
            rw=second_rw,
            data=second_data if second_rw == 0 else None,
            msg=f"random buffered second issued iter={i}",
        )

        second_resp = rand_u32()
        await memory_response(dut, data=second_resp)
        assert_only_thread_response(
            dut,
            second_thread,
            data=second_resp,
            msg=f"random buffered second response iter={i}",
        )


@cocotb.test()
async def test_random_reset_clears_pending_and_inflight(dut):
    random.seed(RNG_SEED + 3)
    await setup_dut(dut)

    for i in range(50):
        thread_id = random.randint(0, THREADS_PER_CORE - 1)
        await issue_single_request(
            dut,
            thread_id=thread_id,
            addr=rand_u32(),
            rw=random.randint(0, 1),
            data=rand_u32(),
        )

        await pulse_requests(dut, [
            {
                "thread": (thread_id + 1) % THREADS_PER_CORE,
                "addr": rand_u32(),
                "rw": random.randint(0, 1),
                "data": rand_u32(),
            }
        ])

        dut.rst.value = 1
        await step(dut)

        assert_mem_req(dut, valid=0, addr=0, rw=0, data=0, msg=f"random reset iter={i}")
        assert int(dut.resp_valid.value) == 0, f"random reset resp_valid expected zero iter={i}"

        dut.rst.value = 0
        await step(dut)

        assert_mem_req(dut, valid=0, msg=f"random reset no pending after release iter={i}")


@cocotb.test()
async def test_random_round_robin_after_prior_service(dut):
    random.seed(RNG_SEED + 4)
    await setup_dut(dut)

    for i in range(50):
        dut.rst.value = 1
        await step(dut)
        dut.rst.value = 0
        await step(dut)

        # Serve one thread first to move rr_ptr.
        first_thread = random.randint(0, THREADS_PER_CORE - 1)
        await issue_single_request(
            dut,
            thread_id=first_thread,
            addr=0x1000 + first_thread,
            rw=1,
        )
        await memory_response(dut, data=0xAAAA0000 | first_thread)

        rr_start = (first_thread + 1) % THREADS_PER_CORE

        # Now request all threads. First serviced should be rr_start.
        reqs = []
        for t in range(THREADS_PER_CORE):
            reqs.append({
                "thread": t,
                "addr": 0x2000 + t,
                "rw": 1,
            })

        await step(dut)
        await pulse_requests(dut, reqs)

        assert_mem_req(
            dut,
            valid=1,
            addr=0x2000 + rr_start,
            rw=1,
            msg=f"random RR after service iter={i}",
        )