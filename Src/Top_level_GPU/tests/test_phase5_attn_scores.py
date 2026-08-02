import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, set_params, u32_to_signed
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
        "../../../assembler/builds/hex/attn_scores.hex"
    )
)


@cocotb.test()
async def test_phase5_attn_scores(dut):
    """
    Phase 5.1 stage 1: scores = Q * K^T on real GPU RTL. seq_len=4,
    d_model=4, one thread per query row (thread i computes scores[i][*]),
    Q8 fixed-point, self-attention (K = Q) so the expected result is the
    symmetric Gram matrix Q @ Q^T, which is hand-checkable without a
    reference softmax/attention implementation.

    Q_real (also used as K_real):
      r0 = [1, 2, 0, 0]
      r1 = [0, 1, 1, 0]
      r2 = [2, 0, 0, 1]
      r3 = [0, 0, 1, 1]

    expected = Q @ Q^T =
      [[5, 2, 2, 0],
       [2, 2, 0, 1],
       [2, 0, 5, 1],
       [0, 1, 1, 2]]

    Values stay small (max 5) so Q8-scaled raw products (real*256 each
    side, real_dot*65536 accumulated) can't overflow 32 bits, and the
    kernel's single SAR-by-8 after full accumulation exactly recovers
    expected_q8 = expected_real * 256 with no intermediate rounding loss.
    """
    Q_real = [
        [1, 2, 0, 0],
        [0, 1, 1, 0],
        [2, 0, 0, 1],
        [0, 0, 1, 1],
    ]
    expected = [
        [5, 2, 2, 0],
        [2, 2, 0, 1],
        [2, 0, 5, 1],
        [0, 1, 1, 2],
    ]

    data_memory = {}
    for i in range(4):
        for k in range(4):
            data_memory[i * 4 + k] = Q_real[i][k] * 256          # Q
            data_memory[16 + i * 4 + k] = Q_real[i][k] * 256     # K = Q

    instructions = load_hex_file(HEX_PATH)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(data_memory, 0, 16, 48)  # q_base, k_base, scores_base
    cyc = await launch_kernel(dut, instructions_ref, instructions, blockDim=4)
    assert cyc is not None, "TIMEOUT: attn_scores did not finish"

    got = [[None] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            got[i][j] = u32_to_signed(data_memory.get(48 + i * 4 + j))

    for i in range(4):
        for j in range(4):
            exp_q8 = expected[i][j] * 256
            assert got[i][j] == exp_q8, (
                f"scores[{i}][{j}]={got[i][j]}, expected {exp_q8} "
                f"(full got={got}, full expected_q8=" +
                str([[e * 256 for e in row] for row in expected]) + ")"
            )

    cocotb.log.info(f"attn_scores PASSED: {got}, cycles={cyc}")
