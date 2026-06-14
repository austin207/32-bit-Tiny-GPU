"""
Random tests for matmul_accelerator.sv

test_random_correctness     : random M/N/K, random INT8 data, Python reference check
test_random_scale           : fixed 2x2 K=4, random SCALE 0..7
test_random_sequential      : 10 sequential launches — verify DONE clears between runs
test_random_negative_data   : random negative INT8 values — checks sign extension in DOT4
"""

import random
import cocotb
from cocotb.clock import Clock

from tests.common import (
    accel_mem_model,
    poll_done,
    reset_dut,
    u32,
    u32_to_signed,
    write_ctrl,
    TIMEOUT_CYCLES,
)

RNG_SEED = 0xACC31E4A

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
# Python reference implementation
# ─────────────────────────────────────────────────────────────────────────────

def _s8(byte):
    """Interpret 8-bit value as signed."""
    byte &= 0xFF
    return byte - 256 if byte >= 128 else byte


def _dot4(a_word, b_word):
    """Signed INT8x4 dot product — matches accelerator hardware."""
    acc = 0
    for lane in range(4):
        a = _s8((a_word >> (8 * lane)) & 0xFF)
        b = _s8((b_word >> (8 * lane)) & 0xFF)
        acc += a * b
    return acc


def _arith_rshift32(val, shift):
    """Arithmetic right shift on INT32 value — matches $signed(acc) >>> scale."""
    val &= 0xFFFFFFFF
    if val >= 0x80000000:
        val -= 0x100000000
    if shift == 0:
        return val
    return val >> shift


def _ref_matmul(a_mem, b_mem, a_base, b_base, m, n, k, scale):
    """
    Compute expected C[m][n] using same algorithm as accelerator FSM.
    a_mem / b_mem : Python dict (data_memory)
    Returns list-of-lists C[i][j].
    """
    num_chunks = k // 4
    C = []
    for i in range(m):
        row = []
        for j in range(n):
            acc = 0
            for kc in range(num_chunks):
                a_addr = a_base + i * num_chunks + kc
                b_addr = b_base + j * num_chunks + kc
                acc += _dot4(a_mem.get(a_addr, 0), b_mem.get(b_addr, 0))
            row.append(_arith_rshift32(acc, scale))
        C.append(row)
    return C


async def _run_accel(dut, memory, a_base, b_base, c_base, m, n, k, scale=0):
    await write_ctrl(dut, A_BASE_OFF, a_base)
    await write_ctrl(dut, B_BASE_OFF, b_base)
    await write_ctrl(dut, C_BASE_OFF, c_base)
    await write_ctrl(dut, M_OFF,      m)
    await write_ctrl(dut, N_OFF,      n)
    await write_ctrl(dut, K_OFF,      k)
    await write_ctrl(dut, SCALE_OFF,  scale)
    await write_ctrl(dut, START_OFF,  1)
    return await poll_done(dut)


def _rand_k():
    """K must be multiple of 4, range 4..16."""
    return random.choice([4, 8, 12, 16])


def _rand_packed_int8():
    """Random 32-bit word where each byte is a random unsigned value 0..127 (positive INT8)."""
    return random.getrandbits(32) & 0x7F7F7F7F


def _rand_packed_int8_signed():
    """Random 32-bit word where each byte is a full INT8 range (-128..127)."""
    return random.getrandbits(32)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_random_correctness(dut):
    """
    50 iterations: random M (1..4), N (1..4), K (4/8/12/16),
    random positive INT8 data. Python reference verifies every C element.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    random.seed(RNG_SEED)

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    memory = {}
    cocotb.start_soon(accel_mem_model(dut, memory))

    for iteration in range(50):
        m = random.randint(1, 4)
        n = random.randint(1, 4)
        k = _rand_k()
        num_chunks = k // 4

        a_base = 0
        b_base = m * num_chunks
        c_base = b_base + n * num_chunks

        # fill A and B^T with random positive INT8 data
        memory.clear()
        for i in range(m):
            for kc in range(num_chunks):
                memory[a_base + i * num_chunks + kc] = _rand_packed_int8()
        for j in range(n):
            for kc in range(num_chunks):
                memory[b_base + j * num_chunks + kc] = _rand_packed_int8()

        # compute expected before accelerator overwrites C region
        expected = _ref_matmul(memory, memory, a_base, b_base, m, n, k, scale=0)

        cycles = await _run_accel(dut, memory, a_base, b_base, c_base, m, n, k)
        assert cycles is not None, f"iter={iteration} M={m} N={n} K={k}: accelerator hung"

        errors = []
        for i in range(m):
            for j in range(n):
                addr = c_base + i * n + j
                got  = u32_to_signed(memory.get(addr, 0xDEADBEEF))
                exp  = expected[i][j]
                if got != exp:
                    errors.append(
                        f"iter={iteration} C[{i}][{j}] exp={exp} got={got} "
                        f"(M={m} N={n} K={k})"
                    )

        assert not errors, "\n".join(errors)

    print(f"\n[test_random_correctness] 50 iterations all passed")


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_random_scale(dut):
    """
    Fixed 2x2 K=4, random SCALE 0..7 across 30 iterations.
    Verifies $signed(acc) >>> scale matches Python arithmetic right-shift.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    random.seed(RNG_SEED + 1)

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    memory = {}
    cocotb.start_soon(accel_mem_model(dut, memory))

    A_BASE, B_BASE, C_BASE = 0, 2, 4
    M, N, K = 2, 2, 4

    for iteration in range(30):
        scale = random.randint(0, 7)

        memory.clear()
        for i in range(M):
            memory[A_BASE + i] = _rand_packed_int8()
        for j in range(N):
            memory[B_BASE + j] = _rand_packed_int8()

        expected = _ref_matmul(memory, memory, A_BASE, B_BASE, M, N, K, scale)

        cycles = await _run_accel(dut, memory, A_BASE, B_BASE, C_BASE, M, N, K, scale)
        assert cycles is not None, f"iter={iteration} scale={scale}: accelerator hung"

        errors = []
        for i in range(M):
            for j in range(N):
                addr = C_BASE + i * N + j
                got  = u32_to_signed(memory.get(addr, 0xDEADBEEF))
                exp  = expected[i][j]
                if got != exp:
                    errors.append(f"iter={iteration} scale={scale} C[{i}][{j}] exp={exp} got={got}")

        assert not errors, "\n".join(errors)

    print(f"\n[test_random_scale] 30 iterations all passed")


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_random_sequential(dut):
    """
    10 sequential launches with different random data each time.
    Verifies DONE clears between runs and each result is independently correct.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    random.seed(RNG_SEED + 2)

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    memory = {}
    cocotb.start_soon(accel_mem_model(dut, memory))

    A_BASE, B_BASE, C_BASE = 0, 4, 8   # fixed 2x2 K=4 layout
    M, N, K = 2, 2, 4

    for run in range(10):
        memory.clear()
        for i in range(M):
            memory[A_BASE + i] = _rand_packed_int8()
        for j in range(N):
            memory[B_BASE + j] = _rand_packed_int8()

        expected = _ref_matmul(memory, memory, A_BASE, B_BASE, M, N, K, scale=0)

        cycles = await _run_accel(dut, memory, A_BASE, B_BASE, C_BASE, M, N, K)
        assert cycles is not None, f"run={run}: accelerator hung"

        errors = []
        for i in range(M):
            for j in range(N):
                addr = C_BASE + i * N + j
                got  = u32_to_signed(memory.get(addr, 0xDEADBEEF))
                exp  = expected[i][j]
                if got != exp:
                    errors.append(f"run={run} C[{i}][{j}] exp={exp} got={got}")

        assert not errors, "\n".join(errors)

    print(f"\n[test_random_sequential] 10 sequential runs all passed")


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_random_negative_data(dut):
    """
    30 iterations with full signed INT8 range (-128..127).
    Critical: verifies sign extension in DOT4 and signed accumulation.
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    random.seed(RNG_SEED + 3)

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF

    memory = {}
    cocotb.start_soon(accel_mem_model(dut, memory))

    for iteration in range(30):
        m = random.randint(1, 3)
        n = random.randint(1, 3)
        k = random.choice([4, 8])
        num_chunks = k // 4

        a_base = 0
        b_base = m * num_chunks
        c_base = b_base + n * num_chunks

        memory.clear()
        for i in range(m):
            for kc in range(num_chunks):
                memory[a_base + i * num_chunks + kc] = _rand_packed_int8_signed()
        for j in range(n):
            for kc in range(num_chunks):
                memory[b_base + j * num_chunks + kc] = _rand_packed_int8_signed()

        expected = _ref_matmul(memory, memory, a_base, b_base, m, n, k, scale=0)

        cycles = await _run_accel(dut, memory, a_base, b_base, c_base, m, n, k)
        assert cycles is not None, f"iter={iteration} M={m} N={n} K={k}: accelerator hung"

        errors = []
        for i in range(m):
            for j in range(n):
                addr = c_base + i * n + j
                got  = u32_to_signed(memory.get(addr, 0xDEADBEEF))
                exp  = expected[i][j]
                if got != exp:
                    errors.append(
                        f"iter={iteration} C[{i}][{j}] exp={exp} got={got} "
                        f"(M={m} N={n} K={k})"
                    )

        assert not errors, "\n".join(errors)

    print(f"\n[test_random_negative_data] 30 iterations all passed")