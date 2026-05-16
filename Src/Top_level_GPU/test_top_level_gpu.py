import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

async def program_memory_model(dut):
    """Simulates program memory - responds with ADD then RET instructions"""
    add_instr = (0x01 << 26) | (1 << 21) | (2 << 16) | (3 << 11)
    ret_instr = (0x12 << 26)
    instructions = {0: add_instr, 1: ret_instr}

    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        for i in range(4):  
            try:
                if dut.prog_mem_req_valid.value[i] == 1:
                    addr = int(dut.prog_mem_req_addr[i].value)
                    dut.prog_mem_resp_valid.value = dut.prog_mem_resp_valid.value | (1 << i)
                    dut.prog_mem_resp_data[i].value = instructions.get(addr, ret_instr)
                else:
                    dut.prog_mem_resp_valid.value = dut.prog_mem_resp_valid.value & ~(1 << i)
            except Exception:
                pass

@cocotb.test()
async def test_gpu_full_pipeline(dut):
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    dut.rst.value = 1
    dut.dcr_write_en.value = 0
    dut.dcr_addr.value = 0
    dut.dcr_data.value = 0
    dut.prog_mem_resp_valid.value = 0
    for i in range(4):
        dut.prog_mem_resp_data[i].value = 0
    for i in range(16):
        dut.data_mem_resp_valid.value = 0
        dut.data_mem_resp_data[i].value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst.value = 0

    dut.dcr_write_en.value = 1
    dut.dcr_addr.value = 0b00
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b01
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    dut.dcr_addr.value = 0b10
    dut.dcr_data.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.dcr_write_en.value = 0

    cocotb.start_soon(program_memory_model(dut))

    for _ in range(500):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if dut.kernel_done.value == 1:
            break

    assert dut.kernel_done.value == 1, f"GPU did not complete — kernel_done never went high"
    cocotb.log.info("GPU pipeline test passed — kernel_done asserted")