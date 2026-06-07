import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_clears_outputs(dut):
    await setup_dut(dut)

    assert_fetch_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=0,
        instruction=0,
        msg="reset",
    )


@cocotb.test()
async def test_idle_core_en_low_no_request(dut):
    await setup_dut(dut)

    dut.core_en.value = 0
    dut.pc_value.value = 5
    await step(dut)

    assert_fetch_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=0,
        instruction=0,
        msg="idle core_en low",
    )


@cocotb.test()
async def test_basic_fetch_single_response(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=5)
    await complete_response(dut, data=0xDEADBEEF)

    assert_fetch_outputs(
        dut,
        req_valid=0,
        done=1,
        req_addr=5,
        instruction=0xDEADBEEF,
        msg="basic fetch",
    )


@cocotb.test()
async def test_multicycle_wait_before_response(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=5)
    await wait_no_response(dut, cycles=3)
    await complete_response(dut, data=0xCAFEBABE)

    assert_fetch_outputs(
        dut,
        done=1,
        req_addr=5,
        instruction=0xCAFEBABE,
        msg="multicycle wait",
    )


@cocotb.test()
async def test_req_valid_is_one_cycle_pulse(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=9)

    await step(dut)
    assert_fetch_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=9,
        msg="req_valid pulse after one cycle",
    )


@cocotb.test()
async def test_done_is_one_cycle_pulse(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=2)
    await complete_response(dut, data=0x11112222)

    await step(dut)
    assert_fetch_outputs(
        dut,
        req_valid=0,
        done=0,
        instruction=0x11112222,
        msg="done pulse cleared next cycle",
    )


@cocotb.test()
async def test_resp_valid_ignored_in_idle(dut):
    await setup_dut(dut)

    dut.core_en.value = 0
    dut.resp_valid.value = 1
    dut.resp_data.value = 0xAAAAAAAA
    await step(dut)

    assert_fetch_outputs(
        dut,
        req_valid=0,
        done=0,
        instruction=0,
        msg="idle resp_valid ignored",
    )


@cocotb.test()
async def test_simultaneous_core_en_and_resp_valid_in_idle_starts_request_only(dut):
    await setup_dut(dut)

    dut.core_en.value = 1
    dut.pc_value.value = 12
    dut.resp_valid.value = 1
    dut.resp_data.value = 0x12345678
    await step(dut)

    assert_fetch_outputs(
        dut,
        req_valid=1,
        done=0,
        req_addr=12,
        instruction=0,
        msg="core_en and resp_valid in IDLE",
    )


@cocotb.test()
async def test_pc_value_latched_into_req_addr(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=7)

    dut.pc_value.value = 99
    await wait_no_response(dut, cycles=2)

    assert_fetch_outputs(
        dut,
        req_addr=7,
        done=0,
        msg="req_addr latched while waiting",
    )


@cocotb.test()
async def test_response_updates_instruction_only_on_resp_valid(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=1)
    await wait_no_response(dut, cycles=2)

    assert_fetch_outputs(
        dut,
        instruction=0,
        done=0,
        msg="instruction unchanged before response",
    )

    await complete_response(dut, data=0xA5A5A5A5)

    assert_fetch_outputs(
        dut,
        instruction=0xA5A5A5A5,
        done=1,
        msg="instruction updated on response",
    )


@cocotb.test()
async def test_reset_during_fetch_clears_state_and_outputs(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=5)
    await wait_no_response(dut, cycles=1)

    dut.rst.value = 1
    await step(dut)

    assert_fetch_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=0,
        instruction=0,
        msg="reset during fetch",
    )


@cocotb.test()
async def test_fetch_after_reset_during_pending_request(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=5)

    dut.rst.value = 1
    await step(dut)
    dut.rst.value = 0
    await step(dut)

    await issue_request(dut, pc=8)
    await complete_response(dut, data=0xFEEDFACE)

    assert_fetch_outputs(
        dut,
        req_addr=8,
        instruction=0xFEEDFACE,
        done=1,
        msg="fetch after reset",
    )


@cocotb.test()
async def test_back_to_back_fetches_core_en_toggled(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=3)
    await complete_response(dut, data=0x11111111)

    await step(dut)

    await issue_request(dut, pc=4)
    await complete_response(dut, data=0x22222222)

    assert_fetch_outputs(
        dut,
        req_addr=4,
        instruction=0x22222222,
        done=1,
        msg="back to back fetches",
    )


@cocotb.test()
async def test_core_en_held_high_relaunches_after_done(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=5, keep_core_en=True)

    dut.resp_valid.value = 1
    dut.resp_data.value = 0xABCD1234
    await step(dut)

    assert_fetch_outputs(
        dut,
        done=1,
        instruction=0xABCD1234,
        msg="held core_en response",
    )

    dut.resp_valid.value = 0
    dut.pc_value.value = 9
    await step(dut)

    assert_fetch_outputs(
        dut,
        req_valid=1,
        req_addr=9,
        done=0,
        msg="held core_en relaunch",
    )

    dut.core_en.value = 0


@cocotb.test()
async def test_boundary_pc_zero(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=0)
    await complete_response(dut, data=0x00000001)

    assert_fetch_outputs(
        dut,
        req_addr=0,
        instruction=0x00000001,
        done=1,
        msg="PC zero",
    )


@cocotb.test()
async def test_boundary_pc_max_u32(dut):
    await setup_dut(dut)

    await issue_request(dut, pc=0xFFFFFFFF)
    await complete_response(dut, data=0xFFFFFFFF)

    assert_fetch_outputs(
        dut,
        req_addr=0xFFFFFFFF,
        instruction=0xFFFFFFFF,
        done=1,
        msg="PC max",
    )