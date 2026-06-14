from cocotb.triggers import RisingEdge, Timer

TIMEOUT_CYCLES = 50000


def safe_int(sig, default=0):
    try:
        return int(sig.value)
    except Exception:
        return default


def u32(v):
    return v & 0xFFFFFFFF


def u32_to_signed(v):
    v &= 0xFFFFFFFF
    return v - 0x100000000 if v >= 0x80000000 else v


async def reset_dut(dut):
    dut.rst.value = 1
    dut.ctrl_wr_valid.value = 0
    dut.ctrl_wr_addr.value  = 0
    dut.ctrl_wr_data.value  = 0
    dut.ctrl_rd_addr.value  = 8    # hold pointing at DONE for polling
    dut.data_resp_valid.value = 0
    dut.data_resp_data.value  = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


async def write_ctrl(dut, offset, data):
    """Write one ctrl register. offset = addr[3:0] (0..8)."""
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.ctrl_wr_valid.value = 1
    dut.ctrl_wr_addr.value  = offset
    dut.ctrl_wr_data.value  = u32(data)
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.ctrl_wr_valid.value = 0


async def poll_done(dut, timeout=TIMEOUT_CYCLES):
    """
    Spin until DONE register (offset 8) reads 1.
    ctrl_rd_addr should already be driven to 8.
    Returns cycle count or None on timeout.
    """
    for cycle in range(timeout):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        if safe_int(dut.ctrl_rd_data) & 1:
            return cycle + 1
    return None


async def accel_mem_model(dut, memory, *, debug=False):
    """
    Standalone data memory model for matmul_accelerator unit test.
    Serves dut.data_req_* / drives dut.data_resp_*.
    Reads and writes share the same Python dict (memory).
    """
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        # default: no response
        dut.data_resp_valid.value = 0
        dut.data_resp_data.value  = 0

        if safe_int(dut.data_req_valid) == 0:
            continue

        addr = safe_int(dut.data_req_addr)
        rw   = safe_int(dut.data_req_rw)   # 1 = read, 0 = write
        data = safe_int(dut.data_req_data)

        if rw == 0:                         # write
            memory[addr] = u32(data)
            dut.data_resp_data.value = 0
            if debug:
                print(f"[ACCEL_MEM] WRITE mem[{addr}] <= 0x{u32(data):08x}")
        else:                               # read
            val = memory.get(addr, 0) & 0xFFFFFFFF
            dut.data_resp_data.value = val
            if debug:
                print(f"[ACCEL_MEM] READ  mem[{addr}] => 0x{val:08x}")

        dut.data_resp_valid.value = 1