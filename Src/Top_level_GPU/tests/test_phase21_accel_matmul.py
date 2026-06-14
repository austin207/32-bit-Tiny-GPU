import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

from .common import init_bus, NUM_CORES
from .memory_models import (
    program_memory_model,
    data_memory_model,
    accel_data_memory_model,
)

def load_hex_file(path):
    """Load a .hex file into {pc: instruction} dict."""
    instructions = {}
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions

# ── Constants ────────────────────────────────────────────────────────────────
PHASE20_CYCLES = 342          # baseline: phase20 tiled matmul 4x4 K=16
TIMEOUT_CYCLES = 100_000      # sanity ceiling

# Expected C = A x B^T  (4x4, K=16, DOT4, SCALE=0)
# Identical to matmul_accelerator unit test and phase20.
EXPECTED_C = [
    [16, 32,  8,  8],   # C[0]  -> mem[32..35]
    [32, 64, 16, 16],   # C[1]  -> mem[36..39]
    [28, 56, 16, 12],   # C[2]  -> mem[40..43]
    [40, 80, 16, 24],   # C[3]  -> mem[44..47]
]

# ── Memory layout ─────────────────────────────────────────────────────────────
#   mem[0..15]   A rows  (4 chunks x 4 rows, packed INT8)
#   mem[16..31]  B^T cols (4 chunks x 4 cols, packed INT8)
#   mem[32..47]  C output — written by accelerator (INT32 words)
def _build_data_memory():
    m = {}
    for i in range(4): m[ 0 + i] = 0x01010101   # A row0 [1,1,1,1] x4
    for i in range(4): m[ 4 + i] = 0x02020202   # A row1 [2,2,2,2] x4
    for i in range(4): m[ 8 + i] = 0x00040300   # A row2 [0,3,4,0] x4
    for i in range(4): m[12 + i] = 0x04030201   # A row3 [1,2,3,4] x4
    for i in range(4): m[16 + i] = 0x01010101   # B^T col0 [1,1,1,1] x4
    for i in range(4): m[20 + i] = 0x02020202   # B^T col1 [2,2,2,2] x4
    for i in range(4): m[24 + i] = 0x00010001   # B^T col2 [1,0,1,0] x4
    for i in range(4): m[28 + i] = 0x01000100   # B^T col3 [0,1,0,1] x4
    return m


# ── Test ──────────────────────────────────────────────────────────────────────
@cocotb.test()
async def test_phase21_accel_matmul(dut):
    """
    Phase 21: MMIO matmul accelerator end-to-end.

    4 blocks x 4 threads.  All 16 threads:
      1. Write ctrl regs to 0x1F0-0x1F7 via STR.
      2. Write START=1 to 0x1F7.
      3. Spin on LDR from 0x1F8 (DONE) until DONE=1.
      4. RET.

    RTL intercepts addr >= 0x1F0:
      - Writes land in accelerator ctrl registers.
      - Reads from 0x1F8 return accel DONE register.

    Accelerator computes C = A x B (4x4, K=16, 4 DOT4 chunks)
    via its own dedicated data memory port (accel_data_req/resp).

    Asserts: all 16 C-matrix elements match EXPECTED_C.
    Prints:  cycle count vs phase20 baseline (342).

    Note: sequential accelerator is expected to be SLOWER than the
    parallel phase20 GPU kernel for this small matrix size.
    That is architecturally correct, not a failure.
    """

    # ── Hex ──────────────────────────────────────────────────────────────────
    base = os.path.dirname(__file__)
    hex_path = os.path.join(
        base, "../../../assembler/builds/hex/phase21_accel_matmul.hex"
    )
    instructions = load_hex_file(hex_path)
    cocotb.log.info(f"Loaded {len(instructions)} instructions from {hex_path}")

    # ── Data memory ──────────────────────────────────────────────────────────
    # Shared dict: data_memory_model serves GPU thread reads/writes (addr < 0x1F0);
    # accel_data_memory_model serves accelerator matrix reads and C writes.
    data_memory = _build_data_memory()

    # ── Bus init ─────────────────────────────────────────────────────────────
    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    # ── Reset ────────────────────────────────────────────────────────────────
    dut.rst.value = 1
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # ── Memory models — start BEFORE dispatch ────────────────────────────────
    # data_memory_model   : GPU thread LDR/STR for addr < 0x1F0;
    #                       skips addr >= 0x1F0 (RTL mux handles ctrl resp)
    # accel_data_memory_model : accelerator matrix port (A/B read, C write)
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))
    cocotb.start_soon(accel_data_memory_model(dut, data_memory))

    # ── DCR configure: 4 blocks x blockDim=4, then start ────────────────────
    dut.dcr_write_en.value = 1

    dut.dcr_addr.value = 0          # num_blocks
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)

    dut.dcr_addr.value = 1          # blockDim
    dut.dcr_data.value = 4
    await RisingEdge(dut.clk)

    dut.dcr_addr.value = 2          # start pulse
    dut.dcr_data.value = 1
    await RisingEdge(dut.clk)

    dut.dcr_write_en.value = 0

    # ── Wait for kernel_done ─────────────────────────────────────────────────
    cycle_count = 0
    for _ in range(TIMEOUT_CYCLES):
        await RisingEdge(dut.clk)
        cycle_count += 1
        if dut.kernel_done.value == 1:
            break
    else:
        assert False, (
            f"TIMEOUT: kernel_done never asserted after {TIMEOUT_CYCLES} cycles"
        )

    await Timer(1, unit="ns")       # let NBA settle before reading memory

    delta = cycle_count - PHASE20_CYCLES
    cocotb.log.info(
        f"Phase 21 cycles : {cycle_count}"
    )
    cocotb.log.info(
        f"Phase 20 baseline: {PHASE20_CYCLES}  delta: {delta:+d}"
    )

    # ── Verify C matrix ──────────────────────────────────────────────────────
    fail = 0
    for row in range(4):
        for col in range(4):
            addr = 32 + row * 4 + col
            got  = data_memory.get(addr)
            exp  = EXPECTED_C[row][col]
            ok   = (got == exp)
            if ok:
                cocotb.log.info(
                    f"  C[{row}][{col}]  addr=0x{addr:03X}  got={got}  PASS"
                )
            else:
                cocotb.log.error(
                    f"  C[{row}][{col}]  addr=0x{addr:03X}  got={got}  "
                    f"expected={exp}  FAIL"
                )
                fail += 1

    assert fail == 0, f"C matrix: {fail}/16 elements wrong"
    cocotb.log.info(
        f"Phase 21 PASSED: 16/16 elements correct  cycles={cycle_count}"
    )