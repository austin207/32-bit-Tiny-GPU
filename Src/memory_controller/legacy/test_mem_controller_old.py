import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

THREADS_PER_CORE = 4
WORD_W = 32


def resp_word(dut, thread_id):
    """
    resp_data is packed:
        logic [THREADS_PER_CORE-1:0][31:0] resp_data

    Thread N occupies:
        bits [N*32 + 31 : N*32]

    Cocotb cannot index packed HDL objects directly, so read the whole value
    and extract the 32-bit lane manually.
    """
    packed = int(dut.resp_data.value)
    return (packed >> (thread_id * WORD_W)) & 0xFFFFFFFF


async def reset_dut(dut):
    dut.rst.value       = 1
    dut.req_valid.value = 0
    dut.req_rw.value    = 0

    for i in range(THREADS_PER_CORE):
        dut.req_addr[i].value = 0
        dut.req_data[i].value = 0

    dut.mem_resp_valid.value = 0
    dut.mem_resp_data.value  = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    dut.rst.value = 0
    await Timer(1, unit="ns")


@cocotb.test()
async def test_single_read(dut):
    """
    T0 issues a read.
    Controller issues to memory.
    Memory responds.
    T0 gets resp_valid and correct resp_data lane.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # T0 requests a read from address 42
    dut.req_valid.value   = 0b0001
    dut.req_rw.value      = 0b0001   # 1 = read
    dut.req_addr[0].value = 42

    # Controller should pick T0 and issue to memory
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert int(dut.mem_req_valid.value) == 1, (
        f"Expected mem_req_valid=1, got {dut.mem_req_valid.value}"
    )
    assert int(dut.mem_req_addr.value) == 42, (
        f"Expected mem_req_addr=42, got {dut.mem_req_addr.value}"
    )
    assert int(dut.mem_req_rw.value) == 1, (
        f"Expected mem_req_rw=1, got {dut.mem_req_rw.value}"
    )

    # Memory responds with data 0xDEADBEEF
    dut.mem_resp_valid.value = 1
    dut.mem_resp_data.value  = 0xDEADBEEF

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert ((int(dut.resp_valid.value) >> 0) & 1) == 1, (
        f"Expected resp_valid[0]=1, got {dut.resp_valid.value}"
    )

    got = resp_word(dut, 0)
    assert got == 0xDEADBEEF, (
        f"Expected resp_data[0]=0xDEADBEEF, got 0x{got:08X}"
    )

    dut.mem_resp_valid.value = 0


@cocotb.test()
async def test_single_write(dut):
    """
    T1 issues a write.
    Controller issues to memory.
    Memory acks.
    T1 gets resp_valid.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # T1 requests a write of value 99 to address 10
    dut.req_valid.value   = 0b0010
    dut.req_rw.value      = 0b0000   # 0 = write
    dut.req_addr[1].value = 10
    dut.req_data[1].value = 99

    # Controller should issue write to memory
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert int(dut.mem_req_valid.value) == 1, (
        f"Expected mem_req_valid=1, got {dut.mem_req_valid.value}"
    )
    assert int(dut.mem_req_addr.value) == 10, (
        f"Expected mem_req_addr=10, got {dut.mem_req_addr.value}"
    )
    assert int(dut.mem_req_rw.value) == 0, (
        f"Expected mem_req_rw=0, got {dut.mem_req_rw.value}"
    )
    assert int(dut.mem_req_data.value) == 99, (
        f"Expected mem_req_data=99, got {dut.mem_req_data.value}"
    )

    # Memory acks the write
    dut.mem_resp_valid.value = 1
    dut.mem_resp_data.value  = 0

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert ((int(dut.resp_valid.value) >> 1) & 1) == 1, (
        f"Expected resp_valid[1]=1, got {dut.resp_valid.value}"
    )

    dut.mem_resp_valid.value = 0


@cocotb.test()
async def test_round_robin(dut):
    """
    T0 and T1 both request simultaneously.
    T0 wins first because rr_ptr=0.
    Then T1 wins second after rr_ptr advances.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await reset_dut(dut)

    # T0 and T1 request reads simultaneously
    dut.req_valid.value   = 0b0011
    dut.req_rw.value      = 0b0011   # both reads
    dut.req_addr[0].value = 100
    dut.req_addr[1].value = 200

    # First issued request should be T0
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert int(dut.mem_req_valid.value) == 1, (
        "Expected mem_req_valid=1 for T0"
    )
    assert int(dut.mem_req_addr.value) == 100, (
        f"Expected T0 addr=100, got {dut.mem_req_addr.value}"
    )
    assert int(dut.mem_req_rw.value) == 1, (
        f"Expected T0 read, got mem_req_rw={dut.mem_req_rw.value}"
    )

    # Memory responds to T0
    dut.mem_resp_valid.value = 1
    dut.mem_resp_data.value  = 0xAAAA

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert ((int(dut.resp_valid.value) >> 0) & 1) == 1, (
        f"Expected resp_valid[0]=1 after T0 served, got {dut.resp_valid.value}"
    )

    got_t0 = resp_word(dut, 0)
    assert got_t0 == 0xAAAA, (
        f"Expected resp_data[0]=0xAAAA, got 0x{got_t0:08X}"
    )

    dut.mem_resp_valid.value = 0

    # Next cycle: rr_ptr should have advanced, so T1 should win next
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert int(dut.mem_req_valid.value) == 1, (
        "Expected mem_req_valid=1 for T1"
    )
    assert int(dut.mem_req_addr.value) == 200, (
        f"Expected T1 addr=200, got {dut.mem_req_addr.value}"
    )
    assert int(dut.mem_req_rw.value) == 1, (
        f"Expected T1 read, got mem_req_rw={dut.mem_req_rw.value}"
    )

    # Memory responds to T1
    dut.mem_resp_valid.value = 1
    dut.mem_resp_data.value  = 0xBBBB

    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")

    assert ((int(dut.resp_valid.value) >> 1) & 1) == 1, (
        f"Expected resp_valid[1]=1 after T1 served, got {dut.resp_valid.value}"
    )

    got_t1 = resp_word(dut, 1)
    assert got_t1 == 0xBBBB, (
        f"Expected resp_data[1]=0xBBBB, got 0x{got_t1:08X}"
    )

    dut.mem_resp_valid.value = 0