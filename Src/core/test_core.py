import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.clock import Clock

async def program_memory_model(dut, instructions):
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.prog_mem_req_valid.value == 1:
            addr = dut.prog_mem_req_addr.value
            dut.prog_mem_resp_valid.value = 1
            dut.prog_mem_resp_data.value = instructions.get(int(addr), 0)
        else:
            dut.prog_mem_resp_valid.value = 0

@cocotb.test()
async def test_core_basic(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # Initialize all inputs
    dut.blockIdx.value = 0
    dut.blockDim.value = 4
    dut.core_start.value = 0
    dut.prog_mem_resp_valid.value = 0
    dut.prog_mem_resp_data.value = 0
    dut.data_mem_resp_valid.value = 0
    for i in range(4):
        dut.data_mem_resp_data[i].value = 0

    # Reset
    dut.rst.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    # Build instructions
    # ADD R1, R2, R3
    add_instr = (0x01 << 26) | (1 << 21) | (2 << 16) | (3 << 11)
    # RET
    ret_instr = (0x12 << 26)

    instructions = {0: add_instr, 1: ret_instr}

    # Start memory model
    cocotb.start_soon(program_memory_model(dut, instructions))

    # Start core
    dut.core_start.value = 1

    # Wait for block_done or timeout
    for _ in range(200):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.block_done.value == 1:
            break

    assert dut.block_done.value == 1, f"Core did not complete — block_done never went high"

    for _ in range(50):
        await RisingEdge(dut.clk)