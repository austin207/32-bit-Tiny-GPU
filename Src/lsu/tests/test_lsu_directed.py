import cocotb

from tests.common import *


@cocotb.test()
async def test_reset_clears_core_outputs(dut):
    await setup_dut(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        req_addr=0,
        mem_read_data=0,
        done=0,
        msg="reset",
    )


@cocotb.test()
async def test_idle_core_en_low_no_request(dut):
    await setup_dut(dut)

    dut.core_en.value = 0
    dut.mem_read_en.value = 1
    dut.mem_write_en.value = 1
    dut.mem_data_address.value = 42
    dut.mem_write_data.value = 1234
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=0,
        msg="idle core_en low",
    )


@cocotb.test()
async def test_core_en_high_no_mem_op_no_request(dut):
    await setup_dut(dut)

    dut.core_en.value = 1
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.mem_data_address.value = 42
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=0,
        msg="core_en no mem op",
    )


@cocotb.test()
async def test_basic_read(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=42)
    await complete_read_response(dut, data=1234)

    assert_lsu_outputs(
        dut,
        done=1,
        mem_read_data=1234,
        read_write_switch=1,
        msg="basic read",
    )


@cocotb.test()
async def test_basic_write(dut):
    await setup_dut(dut)

    await issue_write(dut, addr=42, data=5678)
    await complete_write_response(dut)

    assert_lsu_outputs(
        dut,
        done=1,
        write_data=5678,
        read_write_switch=0,
        msg="basic write",
    )


@cocotb.test()
async def test_read_multicycle_wait(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=0x100)
    await wait_no_response(dut, cycles=4)
    await complete_read_response(dut, data=0xCAFEBABE)

    assert_lsu_outputs(
        dut,
        done=1,
        mem_read_data=0xCAFEBABE,
        msg="read multicycle wait",
    )


@cocotb.test()
async def test_write_multicycle_wait(dut):
    await setup_dut(dut)

    await issue_write(dut, addr=0x200, data=0xDEADBEEF)
    await wait_no_response(dut, cycles=4)
    await complete_write_response(dut)

    assert_lsu_outputs(
        dut,
        done=1,
        write_data=0xDEADBEEF,
        msg="write multicycle wait",
    )


@cocotb.test()
async def test_req_valid_is_one_cycle_pulse_read(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=5)
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=0,
        msg="read req_valid one-cycle pulse",
    )


@cocotb.test()
async def test_req_valid_is_one_cycle_pulse_write(dut):
    await setup_dut(dut)

    await issue_write(dut, addr=5, data=99)
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        done=0,
        req_addr=0,
        msg="write req_valid one-cycle pulse",
    )


@cocotb.test()
async def test_done_is_one_cycle_pulse_read(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=5)
    await complete_read_response(dut, data=0x11111111)

    await step(dut)

    assert_lsu_outputs(
        dut,
        done=0,
        mem_read_data=0x11111111,
        msg="read done pulse cleared",
    )


@cocotb.test()
async def test_done_is_one_cycle_pulse_write(dut):
    await setup_dut(dut)

    await issue_write(dut, addr=5, data=0x22222222)
    await complete_write_response(dut)

    await step(dut)

    assert_lsu_outputs(
        dut,
        done=0,
        write_data=0x22222222,
        msg="write done pulse cleared",
    )


@cocotb.test()
async def test_resp_valid_ignored_in_idle(dut):
    await setup_dut(dut)

    dut.core_en.value = 0
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    dut.resp_valid.value = 1
    dut.resp_data.value = 0xAAAAAAAA
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        done=0,
        mem_read_data=0,
        msg="idle resp_valid ignored",
    )


@cocotb.test()
async def test_simultaneous_core_en_and_resp_valid_in_idle_starts_request_only(dut):
    await setup_dut(dut)

    dut.core_en.value = 1
    dut.mem_read_en.value = 1
    dut.mem_write_en.value = 0
    dut.mem_data_address.value = 0x44
    dut.resp_valid.value = 1
    dut.resp_data.value = 0x12345678
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=1,
        done=0,
        req_addr=0x44,
        mem_read_data=0,
        read_write_switch=1,
        msg="core_en and resp_valid in IDLE",
    )


@cocotb.test()
async def test_read_has_priority_when_read_and_write_both_high(dut):
    await setup_dut(dut)

    dut.core_en.value = 1
    dut.mem_read_en.value = 1
    dut.mem_write_en.value = 1
    dut.mem_data_address.value = 0x55
    dut.mem_write_data.value = 0xDEADBEEF
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=1,
        req_addr=0x55,
        done=0,
        read_write_switch=1,
        msg="read priority over write",
    )

    dut.core_en.value = 0
    dut.mem_read_en.value = 0
    dut.mem_write_en.value = 0
    await complete_read_response(dut, data=0xCAFEBABE)

    assert_lsu_outputs(
        dut,
        done=1,
        mem_read_data=0xCAFEBABE,
        msg="read priority completion",
    )


@cocotb.test()
async def test_reset_during_read_clears_state_and_outputs(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=42)
    await wait_no_response(dut, cycles=1)

    dut.rst.value = 1
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        req_addr=0,
        mem_read_data=0,
        done=0,
        msg="reset during read",
    )


@cocotb.test()
async def test_reset_during_write_clears_state_outputs_except_write_data_contract(dut):
    await setup_dut(dut)

    await issue_write(dut, addr=42, data=0x12345678)
    await wait_no_response(dut, cycles=1)

    dut.rst.value = 1
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=0,
        req_addr=0,
        mem_read_data=0,
        done=0,
        msg="reset during write",
    )

    # write_data is intentionally not checked.
    # Current RTL does not reset write_data.


@cocotb.test()
async def test_read_after_reset_during_pending_read(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=1)

    dut.rst.value = 1
    await step(dut)
    dut.rst.value = 0
    await step(dut)

    await issue_read(dut, addr=2)
    await complete_read_response(dut, data=0x22222222)

    assert_lsu_outputs(
        dut,
        done=1,
        mem_read_data=0x22222222,
        msg="read after reset",
    )


@cocotb.test()
async def test_back_to_back_read_then_write(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=0x10)
    await complete_read_response(dut, data=0xAAAA0001)
    await step(dut)

    await issue_write(dut, addr=0x20, data=0xBBBB0002)
    await complete_write_response(dut)

    assert_lsu_outputs(
        dut,
        done=1,
        write_data=0xBBBB0002,
        msg="back-to-back read then write",
    )


@cocotb.test()
async def test_back_to_back_write_then_read(dut):
    await setup_dut(dut)

    await issue_write(dut, addr=0x20, data=0xBBBB0002)
    await complete_write_response(dut)
    await step(dut)

    await issue_read(dut, addr=0x10)
    await complete_read_response(dut, data=0xAAAA0001)

    assert_lsu_outputs(
        dut,
        done=1,
        mem_read_data=0xAAAA0001,
        msg="back-to-back write then read",
    )


@cocotb.test()
async def test_core_en_held_high_relaunches_after_read_done(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=0x10, keep_core_en=True, keep_read_en=True)

    dut.resp_valid.value = 1
    dut.resp_data.value = 0x11111111
    await step(dut)

    assert_lsu_outputs(
        dut,
        done=1,
        mem_read_data=0x11111111,
        msg="held core_en read response",
    )

    dut.resp_valid.value = 0
    dut.mem_data_address.value = 0x20
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=1,
        req_addr=0x20,
        done=0,
        read_write_switch=1,
        msg="held core_en read relaunch",
    )

    deassert_controls(dut)


@cocotb.test()
async def test_core_en_held_high_relaunches_after_write_done(dut):
    await setup_dut(dut)

    await issue_write(dut, addr=0x10, data=0x11111111, keep_core_en=True, keep_write_en=True)

    dut.resp_valid.value = 1
    await step(dut)

    assert_lsu_outputs(
        dut,
        done=1,
        write_data=0x11111111,
        msg="held core_en write response",
    )

    dut.resp_valid.value = 0
    dut.mem_data_address.value = 0x20
    dut.mem_write_data.value = 0x22222222
    await step(dut)

    assert_lsu_outputs(
        dut,
        req_valid=1,
        req_addr=0x20,
        write_data=0x22222222,
        done=0,
        read_write_switch=0,
        msg="held core_en write relaunch",
    )

    deassert_controls(dut)


@cocotb.test()
async def test_boundary_address_zero_read_write(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=0)
    await complete_read_response(dut, data=0x1234)

    await step(dut)

    await issue_write(dut, addr=0, data=0x5678)
    await complete_write_response(dut)

    assert_lsu_outputs(
        dut,
        write_data=0x5678,
        done=1,
        msg="boundary address zero",
    )


@cocotb.test()
async def test_boundary_address_max_u32_read_write(dut):
    await setup_dut(dut)

    await issue_read(dut, addr=0xFFFFFFFF)
    await complete_read_response(dut, data=0xAAAA5555)

    await step(dut)

    await issue_write(dut, addr=0xFFFFFFFF, data=0x5555AAAA)
    await complete_write_response(dut)

    assert_lsu_outputs(
        write_data=0x5555AAAA,
        done=1,
        dut=dut,
        msg="boundary address max",
    )