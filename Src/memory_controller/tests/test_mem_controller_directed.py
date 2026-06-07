import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_clears_outputs(dut):
    await setup_dut(dut)

    assert_mem_req(dut, valid=0, addr=0, rw=0, data=0, msg="reset")
    assert int(dut.resp_valid.value) == 0, "reset resp_valid should be zero"


@cocotb.test()
async def test_idle_no_requests_no_memory_request(dut):
    await setup_dut(dut)

    clear_reqs(dut)
    await step(dut)

    assert_mem_req(dut, valid=0, msg="idle no request")
    assert int(dut.resp_valid.value) == 0, "idle resp_valid should be zero"


@cocotb.test()
async def test_single_read_thread0(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=0, addr=42, rw=1)

    assert_mem_req(dut, valid=1, addr=42, rw=1, msg="single read T0 request")

    await memory_response(dut, data=0xDEADBEEF)

    assert_only_thread_response(dut, 0, data=0xDEADBEEF, msg="single read T0 response")


@cocotb.test()
async def test_single_write_thread1(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=1, addr=10, rw=0, data=99)

    assert_mem_req(dut, valid=1, addr=10, rw=0, data=99, msg="single write T1 request")

    await memory_response(dut, data=0)

    assert_only_thread_response(dut, 1, data=0, msg="single write T1 response")


@cocotb.test()
async def test_read_thread3_routes_response_lane3(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=3, addr=0x3333, rw=1)

    assert_mem_req(dut, valid=1, addr=0x3333, rw=1, msg="read T3 request")

    await memory_response(dut, data=0x33334444)

    assert_only_thread_response(dut, 3, data=0x33334444, msg="read T3 response")


@cocotb.test()
async def test_mem_req_valid_held_while_waiting(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=0, addr=0x100, rw=1)

    for i in range(3):
        await step(dut)
        assert_mem_req(
            dut,
            valid=1,
            addr=0x100,
            rw=1,
            msg=f"mem_req_valid held while waiting cycle {i}",
        )
        assert int(dut.resp_valid.value) == 0, "no response before mem_resp_valid"


@cocotb.test()
async def test_response_valid_is_one_cycle_pulse(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=0, addr=0x100, rw=1)
    await memory_response(dut, data=0x11111111)

    assert_only_thread_response(dut, 0, data=0x11111111, msg="response pulse cycle")

    await step(dut)

    assert int(dut.resp_valid.value) == 0, "resp_valid should clear after one cycle"


@cocotb.test()
async def test_round_robin_two_simultaneous_requests(dut):
    await setup_dut(dut)

    await pulse_requests(dut, [
        {"thread": 0, "addr": 100, "rw": 1},
        {"thread": 1, "addr": 200, "rw": 1},
    ])

    assert_mem_req(dut, valid=1, addr=100, rw=1, msg="RR first T0")

    await memory_response(dut, data=0xAAAA)
    assert_only_thread_response(dut, 0, data=0xAAAA, msg="RR T0 response")

    await step(dut)
    assert_mem_req(dut, valid=1, addr=200, rw=1, msg="RR second T1")

    await memory_response(dut, data=0xBBBB)
    assert_only_thread_response(dut, 1, data=0xBBBB, msg="RR T1 response")


@cocotb.test()
async def test_round_robin_all_four_simultaneous_requests(dut):
    await setup_dut(dut)

    await pulse_requests(dut, [
        {"thread": 0, "addr": 0x10, "rw": 1},
        {"thread": 1, "addr": 0x20, "rw": 1},
        {"thread": 2, "addr": 0x30, "rw": 1},
        {"thread": 3, "addr": 0x40, "rw": 1},
    ])

    expected = [
        (0, 0x10, 0xA0),
        (1, 0x20, 0xB0),
        (2, 0x30, 0xC0),
        (3, 0x40, 0xD0),
    ]

    for idx, (thread_id, addr, data) in enumerate(expected):
        if idx > 0:
            await step(dut)

        assert_mem_req(dut, valid=1, addr=addr, rw=1, msg=f"RR all request T{thread_id}")

        await memory_response(dut, data=data)
        assert_only_thread_response(dut, thread_id, data=data, msg=f"RR all response T{thread_id}")


@cocotb.test()
async def test_request_pulse_buffered_while_waiting(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=0, addr=0x100, rw=1)
    assert_mem_req(dut, valid=1, addr=0x100, rw=1, msg="initial T0 request")

    # While T0 is in flight, T2 fires a one-cycle req_valid pulse.
    await pulse_requests(dut, [
        {"thread": 2, "addr": 0x222, "rw": 1},
    ])

    # Still waiting on T0. T2 must be buffered, not lost.
    assert_mem_req(dut, valid=1, addr=0x100, rw=1, msg="still T0 in flight")

    await memory_response(dut, data=0xAAAA0000)
    assert_only_thread_response(dut, 0, data=0xAAAA0000, msg="T0 response")

    # Now buffered T2 should be issued.
    await step(dut)
    assert_mem_req(dut, valid=1, addr=0x222, rw=1, msg="buffered T2 issued")

    await memory_response(dut, data=0xBBBB2222)
    assert_only_thread_response(dut, 2, data=0xBBBB2222, msg="buffered T2 response")


@cocotb.test()
async def test_write_request_buffered_while_read_waiting(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=1, addr=0x111, rw=1)
    assert_mem_req(dut, valid=1, addr=0x111, rw=1, msg="initial T1 read")

    await pulse_requests(dut, [
        {"thread": 3, "addr": 0x333, "rw": 0, "data": 0x33333333},
    ])

    assert_mem_req(dut, valid=1, addr=0x111, rw=1, msg="still T1 in flight")

    await memory_response(dut, data=0x11111111)
    assert_only_thread_response(dut, 1, data=0x11111111, msg="T1 response")

    await step(dut)
    assert_mem_req(
        dut,
        valid=1,
        addr=0x333,
        rw=0,
        data=0x33333333,
        msg="buffered T3 write issued",
    )

    await memory_response(dut, data=0)
    assert_only_thread_response(dut, 3, data=0, msg="buffered T3 write response")


@cocotb.test()
async def test_same_thread_new_request_overwrites_pending_payload_before_served(dut):
    """
    Current RTL behavior:
    If a thread already has a pending request and fires another req_valid before
    being served, pending_addr/rw/data are overwritten with the latest pulse.

    This documents the contract.
    """
    await setup_dut(dut)

    # T0 in flight.
    await issue_single_request(dut, thread_id=0, addr=0x100, rw=1)

    # T2 pending first value.
    await pulse_requests(dut, [
        {"thread": 2, "addr": 0x222, "rw": 1},
    ])

    # T2 overwrites pending with new value before T0 completes.
    await pulse_requests(dut, [
        {"thread": 2, "addr": 0x333, "rw": 1},
    ])

    await memory_response(dut, data=0xAAAA0000)
    assert_only_thread_response(dut, 0, data=0xAAAA0000, msg="T0 response")

    await step(dut)
    assert_mem_req(dut, valid=1, addr=0x333, rw=1, msg="T2 latest pending payload wins")


@cocotb.test()
async def test_reset_clears_pending_buffer(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=0, addr=0x100, rw=1)

    await pulse_requests(dut, [
        {"thread": 2, "addr": 0x222, "rw": 1},
    ])

    dut.rst.value = 1
    await step(dut)
    dut.rst.value = 0
    await step(dut)

    assert_mem_req(dut, valid=0, addr=0, rw=0, data=0, msg="reset clears pending")
    assert int(dut.resp_valid.value) == 0, "reset clears responses"

    # No buffered T2 should appear after reset.
    await step(dut)
    assert_mem_req(dut, valid=0, msg="no request after reset-cleared pending")


@cocotb.test()
async def test_round_robin_wraparound_after_thread3(dut):
    await setup_dut(dut)

    # First serve T3 so rr_ptr becomes 0 after T3.
    await issue_single_request(dut, thread_id=3, addr=0x300, rw=1)
    assert_mem_req(dut, valid=1, addr=0x300, rw=1, msg="T3 request")

    await memory_response(dut, data=0x3333)
    assert_only_thread_response(dut, 3, data=0x3333, msg="T3 response")

    # Now T0 and T1 request. rr_ptr should wrap to 0, so T0 wins.
    await step(dut)
    await pulse_requests(dut, [
        {"thread": 0, "addr": 0x100, "rw": 1},
        {"thread": 1, "addr": 0x200, "rw": 1},
    ])

    assert_mem_req(dut, valid=1, addr=0x100, rw=1, msg="wraparound T0 wins")


@cocotb.test()
async def test_boundary_addresses_and_data(dut):
    await setup_dut(dut)

    await issue_single_request(dut, thread_id=0, addr=0x00000000, rw=1)
    assert_mem_req(dut, valid=1, addr=0x00000000, rw=1, msg="addr zero read")
    await memory_response(dut, data=0x00000000)
    assert_only_thread_response(dut, 0, data=0x00000000, msg="addr zero response")

    await step(dut)

    await issue_single_request(
        dut,
        thread_id=1,
        addr=0xFFFFFFFF,
        rw=0,
        data=0xFFFFFFFF,
    )
    assert_mem_req(
        dut,
        valid=1,
        addr=0xFFFFFFFF,
        rw=0,
        data=0xFFFFFFFF,
        msg="addr/data max write",
    )
    await memory_response(dut, data=0x12345678)
    assert_only_thread_response(dut, 1, data=0x12345678, msg="max write response lane")