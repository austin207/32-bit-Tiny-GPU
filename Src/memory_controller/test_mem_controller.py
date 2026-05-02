"""
Test 1 — Single read request

Set req_avail[0]=1, req_addr[0]=42, read_write_switch[0]=1 (read), req_data[0]=0
Wait Timer
Check mem_req_valid[0]==1, mem_req_addr[0]==42, mem_req_rw[0]==1

Test 2 — Single write request

Set req_avail[0]=1, req_addr[0]=10, read_write_switch[0]=0 (write), req_data[0]=99
Wait Timer
Check mem_req_valid[0]==1, mem_req_data[0]==99

Test 3 — Memory response passes back

Set mem_resp_valid[0]=1, mem_resp_data[0]=1234
Wait Timer
Check resp_valid[0]==1, resp_data[0]==1234
"""

import cocotb
from cocotb.triggers import Timer

@cocotb.test()
async def test_single_read_request(dut):

    dut.req_avail.value = 0b0001
    dut.req_addr[0].value = 42
    dut.read_write_switch.value = 0b0001 
    dut.req_data[0].value = 0

    await Timer(1, unit="ns")
    assert dut.mem_req_valid.value == 0b0001, f"Expected mem_req_valid[0] to be 1 got {dut.mem_req_valid[0].value}"
    assert dut.mem_req_addr[0].value == 42, f"Expected mem_req_addr[0] to be 42 got {dut.mem_req_addr[0].value}"
    assert dut.mem_req_rw.value == 0b0001, f"Expected mem_req_rw[0] to be 1 got {dut.mem_req_rw[0].value}"

@cocotb.test()
async def test_single_write_request(dut):

    dut.req_avail.value = 0b0001
    dut.req_addr[0].value = 10
    dut.read_write_switch.value = 0b0000 
    dut.req_data[0].value = 99

    await Timer(1, unit="ns")
    assert dut.mem_req_valid.value == 0b0001, f"Expected mem_req_valid[0] to be 1 got {dut.mem_req_valid[0].value}"
    assert dut.mem_req_data[0].value == 99, f"Expected mem_req_data[0] to be 99 got {dut.mem_req_data[0].value}"

@cocotb.test()
async def test_memory_response(dut):

    dut.mem_resp_valid.value = 0b0001
    dut.mem_resp_data[0].value = 1234

    await Timer(1, unit="ns")
    assert dut.resp_valid.value == 0b0001, f"Expected resp_valid[0] to be 1 got {dut.resp_valid[0].value}"
    assert dut.resp_data[0].value == 1234, f"Expected resp_data[0] to be 1234 got {dut.resp_data[0].value}"
