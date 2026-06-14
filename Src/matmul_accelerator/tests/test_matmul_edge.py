"""
Edge/protocol tests for matmul_accelerator.sv

Covers:
- reset defaults
- ctrl register read/write behavior
- invalid register access
- DONE clear on START
- runtime config latching
- config writes ignored while running
- START ignored while running
- non-zero memory bases
- exact read/write address order
- memory response stalls
- arithmetic right shift on negative accumulators
- no false DONE when memory never responds
"""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from tests.common import (
    accel_mem_model,
    poll_done,
    reset_dut,
    safe_int,
    u32,
    u32_to_signed,
    write_ctrl,
)

# ctrl register offsets
A_BASE_OFF = 0
B_BASE_OFF = 1
C_BASE_OFF = 2
M_OFF      = 3
N_OFF      = 4
K_OFF      = 5
SCALE_OFF  = 6
START_OFF  = 7
DONE_OFF   = 8


# ─────────────────────────────────────────────────────────────────────────────
# Reference helpers
# ─────────────────────────────────────────────────────────────────────────────

def s8(v):
    v &= 0xFF
    return v - 256 if v >= 128 else v


def pack_s8(vals):
    """
    Pack 4 signed INT8 values into one 32-bit word.
    Lane 0 goes into bits [7:0], lane 3 into bits [31:24].
    """
    assert len(vals) == 4
    word = 0
    for lane, val in enumerate(vals):
        word |= (val & 0xFF) << (8 * lane)
    return word & 0xFFFFFFFF


def dot4(a_word, b_word):
    acc = 0
    for lane in range(4):
        a = s8((a_word >> (8 * lane)) & 0xFF)
        b = s8((b_word >> (8 * lane)) & 0xFF)
        acc += a * b
    return acc


def arith_shift_32(v, shift):
    v &= 0xFFFFFFFF
    if v >= 0x80000000:
        v -= 0x100000000
    return v >> shift


def ref_matmul(memory, a_base, b_base, m, n, k, scale=0):
    chunks = k // 4
    out = []
    for row in range(m):
        out_row = []
        for col in range(n):
            acc = 0
            for kc in range(chunks):
                a_addr = a_base + row * chunks + kc
                b_addr = b_base + col * chunks + kc
                acc += dot4(memory.get(a_addr, 0), memory.get(b_addr, 0))
            out_row.append(arith_shift_32(acc, scale))
        out.append(out_row)
    return out


async def run_accel(dut, a_base, b_base, c_base, m, n, k, scale=0):
    await write_ctrl(dut, A_BASE_OFF, a_base)
    await write_ctrl(dut, B_BASE_OFF, b_base)
    await write_ctrl(dut, C_BASE_OFF, c_base)
    await write_ctrl(dut, M_OFF,      m)
    await write_ctrl(dut, N_OFF,      n)
    await write_ctrl(dut, K_OFF,      k)
    await write_ctrl(dut, SCALE_OFF,  scale)
    await write_ctrl(dut, START_OFF,  1)
    return await poll_done(dut)


async def read_ctrl(dut, offset):
    dut.ctrl_rd_addr.value = offset
    await Timer(1, unit="ns")
    return safe_int(dut.ctrl_rd_data)


async def accel_mem_model_recording(dut, memory, reads, writes, *, debug=False):
    """
    Same as common accel_mem_model, but records read/write order.
    """
    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        dut.data_resp_valid.value = 0
        dut.data_resp_data.value = 0

        if safe_int(dut.data_req_valid) == 0:
            continue

        addr = safe_int(dut.data_req_addr)
        rw   = safe_int(dut.data_req_rw)
        data = safe_int(dut.data_req_data)

        if rw == 0:
            memory[addr] = u32(data)
            writes.append((addr, u32(data)))
            dut.data_resp_data.value = 0
            if debug:
                print(f"[REC_MEM] WRITE mem[{addr}] <= 0x{u32(data):08x}")
        else:
            val = memory.get(addr, 0) & 0xFFFFFFFF
            reads.append(addr)
            dut.data_resp_data.value = val
            if debug:
                print(f"[REC_MEM] READ  mem[{addr}] => 0x{val:08x}")

        dut.data_resp_valid.value = 1


async def accel_mem_model_latency(
    dut,
    memory,
    *,
    read_latency=3,
    write_latency=2,
    debug=False,
):
    """
    Memory model with delayed responses.
    Used to verify accelerator waits in WAIT_A / WAIT_B / WAIT_STORE.
    """
    pending = []

    while True:
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")

        dut.data_resp_valid.value = 0
        dut.data_resp_data.value = 0

        next_pending = []
        responded = False

        for delay, addr, rw, data in pending:
            delay -= 1

            if delay <= 0 and not responded:
                if rw == 0:
                    memory[addr] = u32(data)
                    dut.data_resp_data.value = 0
                    if debug:
                        print(f"[LAT_MEM] WRITE mem[{addr}] <= 0x{u32(data):08x}")
                else:
                    val = memory.get(addr, 0) & 0xFFFFFFFF
                    dut.data_resp_data.value = val
                    if debug:
                        print(f"[LAT_MEM] READ  mem[{addr}] => 0x{val:08x}")

                dut.data_resp_valid.value = 1
                responded = True
            else:
                next_pending.append((delay, addr, rw, data))

        pending = next_pending

        if safe_int(dut.data_req_valid) == 1:
            addr = safe_int(dut.data_req_addr)
            rw   = safe_int(dut.data_req_rw)
            data = safe_int(dut.data_req_data)

            latency = read_latency if rw else write_latency
            pending.append((max(1, latency), addr, rw, data))


def assert_matrix(memory, c_base, expected):
    m = len(expected)
    n = len(expected[0])

    errors = []
    for i in range(m):
        for j in range(n):
            addr = c_base + i * n + j
            got = u32_to_signed(memory.get(addr, 0xDEADBEEF))
            exp = expected[i][j]
            if got != exp:
                errors.append(f"C[{i}][{j}] addr={addr}: expected {exp}, got {got}")

    assert not errors, "\n".join(errors)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_reset_defaults_and_idle_outputs(dut):
    """
    Reset should clear config regs, DONE, data request outputs, and return IDLE.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    for offset in range(9):
        val = await read_ctrl(dut, offset)
        assert val == 0, f"ctrl[{offset}] expected reset value 0, got 0x{val:08x}"

    assert safe_int(dut.data_req_valid) == 0, "data_req_valid should be 0 after reset"
    assert safe_int(dut.data_req_addr) == 0, "data_req_addr should be 0 after reset"
    assert safe_int(dut.data_req_data) == 0, "data_req_data should be 0 after reset"

    # Internal state is useful for debug; available in Icarus hierarchy.
    assert safe_int(dut.state) == 0, "FSM should reset to IDLE"


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_ctrl_register_write_readback_and_invalid_access(dut):
    """
    Write all writable config regs while IDLE and read them back.
    DONE is read-only. Invalid read should return 0.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)

    values = {
        A_BASE_OFF:  0x00000011,
        B_BASE_OFF:  0x00000022,
        C_BASE_OFF:  0x00000033,
        M_OFF:       0x00000004,
        N_OFF:       0x00000003,
        K_OFF:       0x00000010,
        SCALE_OFF:   0x00000002,
    }

    for off, val in values.items():
        await write_ctrl(dut, off, val)

    for off, exp in values.items():
        got = await read_ctrl(dut, off)
        assert got == exp, f"ctrl[{off}] expected 0x{exp:08x}, got 0x{got:08x}"

    # DONE is read-only. Writing offset 8 should not set DONE.
    await write_ctrl(dut, DONE_OFF, 1)
    done = await read_ctrl(dut, DONE_OFF)
    assert done == 0, f"DONE should remain 0 after write attempt, got {done}"

    # Invalid read offset should return 0.
    invalid = await read_ctrl(dut, 15)
    assert invalid == 0, f"invalid ctrl read should return 0, got 0x{invalid:08x}"


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_done_clears_on_new_start(dut):
    """
    After a completed run, DONE should be 1.
    A new START should clear DONE before the second run completes.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    memory = {
        0: pack_s8([1, 1, 1, 1]),
        1: pack_s8([2, 2, 2, 2]),
    }

    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await run_accel(dut, 0, 1, 2, 1, 1, 4, 0)
    assert cycles is not None, "first run hung"
    assert u32_to_signed(memory[2]) == 8

    done = await read_ctrl(dut, DONE_OFF)
    assert done & 1, "DONE should be 1 after first run"

    # Prepare second run.
    memory.clear()
    memory[10] = pack_s8([3, 3, 3, 3])
    memory[11] = pack_s8([4, 4, 4, 4])

    await write_ctrl(dut, A_BASE_OFF, 10)
    await write_ctrl(dut, B_BASE_OFF, 11)
    await write_ctrl(dut, C_BASE_OFF, 12)
    await write_ctrl(dut, M_OFF, 1)
    await write_ctrl(dut, N_OFF, 1)
    await write_ctrl(dut, K_OFF, 4)
    await write_ctrl(dut, SCALE_OFF, 0)

    await write_ctrl(dut, START_OFF, 1)

    done_after_start = await read_ctrl(dut, DONE_OFF)
    assert (done_after_start & 1) == 0, "DONE should clear immediately after new START"

    cycles = await poll_done(dut)
    assert cycles is not None, "second run hung"
    assert u32_to_signed(memory[12]) == 48


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_config_writes_ignored_while_running_runtime_latch(dut):
    """
    Start a long 4x4 K=16 run.
    While running, attempt to corrupt all config regs and START again.
    Expected: original latched config remains in effect and result is correct.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 0
    B_BASE = 16
    C_BASE = 32
    M, N, K = 4, 4, 16

    memory = {}
    for c in range(4):
        memory[0  + c] = pack_s8([1, 1, 1, 1])
        memory[4  + c] = pack_s8([2, 2, 2, 2])
        memory[8  + c] = pack_s8([0, 3, 4, 0])
        memory[12 + c] = pack_s8([1, 2, 3, 4])

        memory[16 + c] = pack_s8([1, 1, 1, 1])
        memory[20 + c] = pack_s8([2, 2, 2, 2])
        memory[24 + c] = pack_s8([1, 0, 1, 0])
        memory[28 + c] = pack_s8([0, 1, 0, 1])

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, 0)

    cocotb.start_soon(accel_mem_model(dut, memory))

    # Configure and start.
    await write_ctrl(dut, A_BASE_OFF, A_BASE)
    await write_ctrl(dut, B_BASE_OFF, B_BASE)
    await write_ctrl(dut, C_BASE_OFF, C_BASE)
    await write_ctrl(dut, M_OFF, M)
    await write_ctrl(dut, N_OFF, N)
    await write_ctrl(dut, K_OFF, K)
    await write_ctrl(dut, SCALE_OFF, 0)
    await write_ctrl(dut, START_OFF, 1)

    # Let it leave IDLE and enter active FSM.
    for _ in range(20):
        await RisingEdge(dut.clk)

    # Try to corrupt config while running. These must be ignored.
    await write_ctrl(dut, A_BASE_OFF, 200)
    await write_ctrl(dut, B_BASE_OFF, 210)
    await write_ctrl(dut, C_BASE_OFF, 220)
    await write_ctrl(dut, M_OFF, 1)
    await write_ctrl(dut, N_OFF, 1)
    await write_ctrl(dut, K_OFF, 4)
    await write_ctrl(dut, SCALE_OFF, 7)
    await write_ctrl(dut, START_OFF, 1)

    cycles = await poll_done(dut)
    assert cycles is not None, "accelerator hung after ignored config writes"

    assert_matrix(memory, C_BASE, expected)

    # Bad C base should not receive output.
    assert 220 not in memory, "corrupt C_BASE write while running should be ignored"


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_nonzero_bases_and_gap_memory_layout(dut):
    """
    Use non-zero A/B/C base addresses with gaps to catch bad address math.
    Shape: M=3, N=2, K=12.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 50
    B_BASE = 80
    C_BASE = 120
    M, N, K = 3, 2, 12
    chunks = K // 4

    memory = {}

    # A rows
    a_rows = [
        [pack_s8([1, 2, 3, 4]), pack_s8([2, 2, 2, 2]), pack_s8([1, 0, 1, 0])],
        [pack_s8([0, 1, 0, 1]), pack_s8([3, 3, 3, 3]), pack_s8([4, 0, 0, 4])],
        [pack_s8([-1, 2, -3, 4]), pack_s8([1, -1, 1, -1]), pack_s8([2, 2, -2, -2])],
    ]

    # B^T cols
    b_cols = [
        [pack_s8([1, 1, 1, 1]), pack_s8([2, 0, 2, 0]), pack_s8([-1, 1, -1, 1])],
        [pack_s8([2, 2, 2, 2]), pack_s8([1, 1, 1, 1]), pack_s8([0, 1, 0, 1])],
    ]

    for i in range(M):
        for kc in range(chunks):
            memory[A_BASE + i * chunks + kc] = a_rows[i][kc]

    for j in range(N):
        for kc in range(chunks):
            memory[B_BASE + j * chunks + kc] = b_cols[j][kc]

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, 0)

    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await run_accel(dut, A_BASE, B_BASE, C_BASE, M, N, K, 0)
    assert cycles is not None, "accelerator hung on non-zero base test"

    assert_matrix(memory, C_BASE, expected)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_exact_read_and_write_address_order_row_major(dut):
    """
    Verify read order and write order for M=2, N=3, K=4.
    Expected output write order:
      C[0][0], C[0][1], C[0][2], C[1][0], C[1][1], C[1][2]
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 10
    B_BASE = 20
    C_BASE = 30
    M, N, K = 2, 3, 4
    chunks = K // 4

    memory = {
        10: pack_s8([1, 1, 1, 1]),
        11: pack_s8([2, 2, 2, 2]),

        20: pack_s8([1, 0, 0, 0]),
        21: pack_s8([0, 1, 0, 0]),
        22: pack_s8([0, 0, 1, 0]),
    }

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, 0)

    reads = []
    writes = []
    cocotb.start_soon(accel_mem_model_recording(dut, memory, reads, writes))

    cycles = await run_accel(dut, A_BASE, B_BASE, C_BASE, M, N, K, 0)
    assert cycles is not None, "accelerator hung on address-order test"

    expected_reads = []
    expected_writes = []

    for i in range(M):
        for j in range(N):
            for kc in range(chunks):
                expected_reads.append(A_BASE + i * chunks + kc)
                expected_reads.append(B_BASE + j * chunks + kc)
            expected_writes.append(C_BASE + i * N + j)

    got_write_addrs = [addr for addr, _ in writes]

    assert reads == expected_reads, f"read order mismatch\nexpected={expected_reads}\ngot={reads}"
    assert got_write_addrs == expected_writes, (
        f"write order mismatch\nexpected={expected_writes}\ngot={got_write_addrs}"
    )

    assert_matrix(memory, C_BASE, expected)

    assert (C_BASE + M * N) not in memory, "accelerator wrote past expected C output range"


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_memory_response_stalls_are_handled(dut):
    """
    Memory responds after multiple cycles.
    Accelerator must wait in WAIT_A / WAIT_B / WAIT_STORE and still complete.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 0
    B_BASE = 4
    C_BASE = 8
    M, N, K = 2, 2, 8
    chunks = K // 4

    memory = {}

    # A: 2 rows, 2 chunks each
    memory[0] = pack_s8([1, 2, 3, 4])
    memory[1] = pack_s8([1, 1, 1, 1])
    memory[2] = pack_s8([2, 2, 2, 2])
    memory[3] = pack_s8([3, 0, 3, 0])

    # B^T: 2 cols, 2 chunks each
    memory[4] = pack_s8([1, 1, 1, 1])
    memory[5] = pack_s8([2, 2, 2, 2])
    memory[6] = pack_s8([0, 1, 0, 1])
    memory[7] = pack_s8([1, 0, 1, 0])

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, 0)

    cocotb.start_soon(
        accel_mem_model_latency(
            dut,
            memory,
            read_latency=4,
            write_latency=3,
        )
    )

    cycles = await run_accel(dut, A_BASE, B_BASE, C_BASE, M, N, K, 0)
    assert cycles is not None, "accelerator hung with stalled memory responses"

    # Should be slower than the zero-stall 2x2 K=4 smoke test.
    assert cycles > 33, f"stalled memory test unexpectedly too fast: cycles={cycles}"

    assert_matrix(memory, C_BASE, expected)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_signed_extreme_int8_values(dut):
    """
    Full INT8 edge values:
    -128, -1, 0, 1, 2, 127.
    Verifies signed byte interpretation and sign extension.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 0
    B_BASE = 4
    C_BASE = 8
    M, N, K = 2, 2, 8

    memory = {
        # A rows, 2 chunks each
        0: pack_s8([-128, -1, 0, 127]),
        1: pack_s8([1, -2, 3, -4]),

        2: pack_s8([127, 0, -128, 1]),
        3: pack_s8([-1, -1, -1, -1]),

        # B^T cols, 2 chunks each
        4: pack_s8([1, 1, 1, 1]),
        5: pack_s8([2, 2, 2, 2]),

        6: pack_s8([-1, 0, 1, 2]),
        7: pack_s8([3, -3, 4, -4]),
    }

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, 0)

    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await run_accel(dut, A_BASE, B_BASE, C_BASE, M, N, K, 0)
    assert cycles is not None, "accelerator hung on signed INT8 extreme test"

    assert_matrix(memory, C_BASE, expected)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_negative_accumulator_arithmetic_scale(dut):
    """
    Negative accumulator with SCALE.
    Verifies arithmetic right shift, not logical right shift.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 0
    B_BASE = 1
    C_BASE = 2
    M, N, K = 1, 1, 4
    SCALE = 2

    # Dot = (-1*1) + (-2*1) + (-3*1) + (-4*1) = -10
    # -10 >>> 2 = -3
    memory = {
        0: pack_s8([-1, -2, -3, -4]),
        1: pack_s8([1, 1, 1, 1]),
    }

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, SCALE)

    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await run_accel(dut, A_BASE, B_BASE, C_BASE, M, N, K, SCALE)
    assert cycles is not None, "accelerator hung on negative scale test"

    assert expected == [[-3]], f"reference sanity failed: expected {expected}"
    assert_matrix(memory, C_BASE, expected)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_minimal_1x1_k4_shape(dut):
    """
    Smallest valid shape: M=1, N=1, K=4.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 5
    B_BASE = 6
    C_BASE = 7
    M, N, K = 1, 1, 4

    memory = {
        5: pack_s8([4, 3, 2, 1]),
        6: pack_s8([1, 2, 3, 4]),
    }

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, 0)

    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await run_accel(dut, A_BASE, B_BASE, C_BASE, M, N, K, 0)
    assert cycles is not None, "accelerator hung on minimal shape"

    assert_matrix(memory, C_BASE, expected)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_large_supported_4x4_k16_all_negative(dut):
    """
    Max current tested shape: M=4, N=4, K=16.
    All lanes negative/positive mixed to stress signed accumulation.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    A_BASE = 0
    B_BASE = 16
    C_BASE = 32
    M, N, K = 4, 4, 16
    chunks = K // 4

    memory = {}

    a_patterns = [
        pack_s8([-1, -1, -1, -1]),
        pack_s8([-2, -2, -2, -2]),
        pack_s8([1, -1, 1, -1]),
        pack_s8([127, -128, 1, -1]),
    ]

    b_patterns = [
        pack_s8([1, 1, 1, 1]),
        pack_s8([-1, -1, -1, -1]),
        pack_s8([2, -2, 2, -2]),
        pack_s8([-128, 127, -1, 1]),
    ]

    for i in range(M):
        for kc in range(chunks):
            memory[A_BASE + i * chunks + kc] = a_patterns[(i + kc) % len(a_patterns)]

    for j in range(N):
        for kc in range(chunks):
            memory[B_BASE + j * chunks + kc] = b_patterns[(j + kc) % len(b_patterns)]

    expected = ref_matmul(memory, A_BASE, B_BASE, M, N, K, 0)

    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await run_accel(dut, A_BASE, B_BASE, C_BASE, M, N, K, 0)
    assert cycles is not None, "accelerator hung on large signed 4x4 K16 test"

    assert_matrix(memory, C_BASE, expected)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_no_memory_response_does_not_false_done(dut):
    """
    No memory model is started.
    Accelerator should not falsely assert DONE if memory never responds.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    # No accel_mem_model started here.
    await write_ctrl(dut, A_BASE_OFF, 0)
    await write_ctrl(dut, B_BASE_OFF, 1)
    await write_ctrl(dut, C_BASE_OFF, 2)
    await write_ctrl(dut, M_OFF, 1)
    await write_ctrl(dut, N_OFF, 1)
    await write_ctrl(dut, K_OFF, 4)
    await write_ctrl(dut, SCALE_OFF, 0)
    await write_ctrl(dut, START_OFF, 1)

    cycles = await poll_done(dut, timeout=64)
    assert cycles is None, "DONE should not assert when memory never responds"

    done = await read_ctrl(dut, DONE_OFF)
    assert (done & 1) == 0, "DONE register should remain 0 without memory responses"