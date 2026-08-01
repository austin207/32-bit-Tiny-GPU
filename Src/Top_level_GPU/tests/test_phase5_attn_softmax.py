import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, u32_to_signed
from .memory_models import program_memory_model, data_memory_model


def load_hex_file(path):
    instructions = {}
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions


HEX_PATH = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../../assembler/builds/hex/attn_softmax.hex"
    )
)


@cocotb.test()
async def test_phase5_attn_softmax(dut):
    """
    Phase 5.1 stage 2: weights = softmax(scores) on real GPU RTL, seq_len=4,
    Q8 fixed-point. Each row is a cyclic rotation of base_vals real =
    [0, -0.5, -1.0, -2.5] so the row max sits at column j=i (exercises the
    per-thread base/obase addressing, not just the math), and every row
    shares the same multiset of (max - score) gaps, so all four rows reduce
    to one hand-checkable LUT lookup.

    Gaps -> Q6 (>>2 of the Q8 gap) -> hardware EXP8 LUT (alu.sv, hand-read):
      gap=0.0  -> Q6   0 -> exp8 = 127 (x>=0 saturates)
      gap=0.5  -> Q6 -32 -> exp8 =  77
      gap=1.0  -> Q6 -64 -> exp8 =  47
      gap=2.5  -> Q6 -160, clamped to -128 -> exp8 = 17
    sum = 127+77+47+17 = 268
    weight_q8 = exp8*256/268 (integer division): 121, 73, 44, 16
    """
    base_vals = [0.0, -0.5, -1.0, -2.5]
    weight_lut = [121, 73, 44, 16]  # for gap index 0,1,2,3 respectively

    data_memory = {}
    expected = [[0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            gap_idx = (j - i) % 4
            score_real = base_vals[gap_idx]
            data_memory[48 + i * 4 + j] = int(round(score_real * 256)) & 0xFFFFFFFF
            expected[i][j] = weight_lut[gap_idx]

    instructions = load_hex_file(HEX_PATH)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions, blockDim=4)
    assert cyc is not None, "TIMEOUT: attn_softmax did not finish"

    got = [[None] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            got[i][j] = u32_to_signed(data_memory.get(64 + i * 4 + j))

    for i in range(4):
        for j in range(4):
            assert got[i][j] == expected[i][j], (
                f"weights[{i}][{j}]={got[i][j]}, expected {expected[i][j]} "
                f"(full got={got}, full expected={expected})"
            )

    cocotb.log.info(f"attn_softmax PASSED: {got}, cycles={cyc}")
