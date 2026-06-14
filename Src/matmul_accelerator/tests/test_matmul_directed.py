"""
Directed tests for matmul_accelerator.sv

test_matmul_2x2_k4   : 2x2 output, K=4  (1 DOT4 chunk)  — smoke test
test_matmul_4x4_k16  : 4x4 output, K=16 (4 DOT4 chunks) — matches phase20 data
test_matmul_scale    : 2x2 output, K=4, SCALE=1          — verifies right-shift

Memory layout (B stored transposed):
    A[i][chunk]     at  A_BASE + i*(K//4) + chunk
    B^T[j][chunk]   at  B_BASE + j*(K//4) + chunk
    C[i][j]         at  C_BASE + i*N + j
"""

import cocotb
from cocotb.clock import Clock

from tests.common import (
    accel_mem_model,
    poll_done,
    reset_dut,
    u32,
    u32_to_signed,
    write_ctrl,
)

# ctrl register offsets
A_BASE_OFF  = 0
B_BASE_OFF  = 1
C_BASE_OFF  = 2
M_OFF       = 3
N_OFF       = 4
K_OFF       = 5
SCALE_OFF   = 6
START_OFF   = 7
DONE_OFF    = 8


async def _run_accel(dut, memory, a_base, b_base, c_base, m, n, k, scale=0):
    """Write all ctrl regs, fire START, wait for DONE. Returns cycle count."""
    await write_ctrl(dut, A_BASE_OFF, a_base)
    await write_ctrl(dut, B_BASE_OFF, b_base)
    await write_ctrl(dut, C_BASE_OFF, c_base)
    await write_ctrl(dut, M_OFF,      m)
    await write_ctrl(dut, N_OFF,      n)
    await write_ctrl(dut, K_OFF,      k)
    await write_ctrl(dut, SCALE_OFF,  scale)
    await write_ctrl(dut, START_OFF,  1)     # launch

    cycles = await poll_done(dut)
    return cycles


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_matmul_2x2_k4(dut):
    """
    2x2 INT8 matmul, K=4, SCALE=0.

    A = [[1,1,1,1],   packed: [0x01010101, 0x01010101]
         [2,2,2,2]]           [0x02020202, 0x02020202]

    B^T = [[1,1,1,1], packed: [0x01010101, 0x01010101]
           [2,2,2,2]]         [0x02020202, 0x02020202]

    Expected C:
        C[0][0] = 4   C[0][1] = 8
        C[1][0] = 8   C[1][1] = 16
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    A_BASE = 0
    B_BASE = 2    # 2 rows × 1 chunk = 2 words
    C_BASE = 4    # 2 cols × 1 chunk = 2 words
    M, N, K = 2, 2, 4

    memory = {
        # A rows (1 chunk each)
        0: 0x01010101,   # A[0] = [1,1,1,1]
        1: 0x02020202,   # A[1] = [2,2,2,2]
        # B^T cols (1 chunk each)
        2: 0x01010101,   # B^T[0] = [1,1,1,1]
        3: 0x02020202,   # B^T[1] = [2,2,2,2]
    }

    expected = {
        4: 4,   # C[0][0]
        5: 8,   # C[0][1]
        6: 8,   # C[1][0]
        7: 16,  # C[1][1]
    }

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF
    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await _run_accel(dut, memory, A_BASE, B_BASE, C_BASE, M, N, K)
    assert cycles is not None, "accelerator hung — DONE never asserted"

    print(f"\n[test_matmul_2x2_k4] DONE in {cycles} cycles")

    for addr, exp in expected.items():
        got = u32_to_signed(memory.get(addr, 0xDEADBEEF))
        assert got == exp, f"C[{(addr-C_BASE)//N}][{(addr-C_BASE)%N}]: expected {exp}, got {got}"
        print(f"  mem[{addr}] = {got}  ✓")


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_matmul_4x4_k16(dut):
    """
    4x4 INT8 matmul, K=16 (4 DOT4 chunks), SCALE=0.
    Same data and expected output as phase20.

    A rows (4 identical chunks each):
        row0 = [1,1,1,1] × 4   0x01010101
        row1 = [2,2,2,2] × 4   0x02020202
        row2 = [0,3,4,0] × 4   0x00040300
        row3 = [1,2,3,4] × 4   0x04030201

    B^T cols (4 identical chunks each):
        col0 = [1,1,1,1] × 4   0x01010101
        col1 = [2,2,2,2] × 4   0x02020202
        col2 = [1,0,1,0] × 4   0x00010001
        col3 = [0,1,0,1] × 4   0x01000100

    Expected C:
        row0: [16, 32,  8,  8]
        row1: [32, 64, 16, 16]
        row2: [28, 56, 16, 12]
        row3: [40, 80, 16, 24]
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    A_BASE = 0
    B_BASE = 16   # 4 rows × 4 chunks = 16 words
    C_BASE = 32   # 4 cols × 4 chunks = 16 words
    M, N, K = 4, 4, 16

    memory = {}
    # A: row i, chunk c → mem[i*4 + c]
    for c in range(4): memory[0  + c] = 0x01010101  # row0
    for c in range(4): memory[4  + c] = 0x02020202  # row1
    for c in range(4): memory[8  + c] = 0x00040300  # row2
    for c in range(4): memory[12 + c] = 0x04030201  # row3
    # B^T: col j, chunk c → mem[16 + j*4 + c]
    for c in range(4): memory[16 + c] = 0x01010101  # col0
    for c in range(4): memory[20 + c] = 0x02020202  # col1
    for c in range(4): memory[24 + c] = 0x00010001  # col2
    for c in range(4): memory[28 + c] = 0x01000100  # col3

    expected_c = [
        [16, 32,  8,  8],
        [32, 64, 16, 16],
        [28, 56, 16, 12],
        [40, 80, 16, 24],
    ]

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF
    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await _run_accel(dut, memory, A_BASE, B_BASE, C_BASE, M, N, K)
    assert cycles is not None, "accelerator hung — DONE never asserted"

    print(f"\n[test_matmul_4x4_k16] DONE in {cycles} cycles")

    errors = []
    for i in range(M):
        for j in range(N):
            addr = C_BASE + i * N + j
            got  = u32_to_signed(memory.get(addr, 0xDEADBEEF))
            exp  = expected_c[i][j]
            status = "✓" if got == exp else f"✗ expected {exp}"
            print(f"  C[{i}][{j}] mem[{addr}] = {got:4d}  {status}")
            if got != exp:
                errors.append(f"C[{i}][{j}]: expected {exp}, got {got}")

    assert not errors, "\n".join(errors)


# ─────────────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_matmul_scale(dut):
    """
    2x2 INT8 matmul, K=4, SCALE=2.
    Same A/B as test_matmul_2x2_k4. Accumulator right-shifted by 2 before store.

    Raw acc values: [4, 8, 8, 16]
    After SCALE=2 (>>> 2): [1, 2, 2, 4]
    """
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    A_BASE = 0
    B_BASE = 2
    C_BASE = 4
    M, N, K = 2, 2, 4

    memory = {
        0: 0x01010101,
        1: 0x02020202,
        2: 0x01010101,
        3: 0x02020202,
    }

    expected = {
        4: 1,   # 4  >> 2
        5: 2,   # 8  >> 2
        6: 2,   # 8  >> 2
        7: 4,   # 16 >> 2
    }

    await reset_dut(dut)
    dut.ctrl_rd_addr.value = DONE_OFF
    cocotb.start_soon(accel_mem_model(dut, memory))

    cycles = await _run_accel(dut, memory, A_BASE, B_BASE, C_BASE, M, N, K, scale=2)
    assert cycles is not None, "accelerator hung — DONE never asserted"

    print(f"\n[test_matmul_scale] DONE in {cycles} cycles")

    for addr, exp in expected.items():
        got = u32_to_signed(memory.get(addr, 0xDEADBEEF))
        assert got == exp, f"C[{(addr-C_BASE)//N}][{(addr-C_BASE)%N}]: expected {exp}, got {got}"
        print(f"  mem[{addr}] = {got}  ✓")