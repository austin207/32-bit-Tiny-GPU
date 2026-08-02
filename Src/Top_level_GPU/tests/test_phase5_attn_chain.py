import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, set_params, u32_to_signed
from .memory_models import program_memory_model, data_memory_model
from .attn_reference import reference_attention


def load_hex_file(path):
    instructions = {}
    with open(path) as f:
        for i, line in enumerate(f):
            line = line.strip()
            if line:
                instructions[i] = int(line, 16)
    return instructions


BUILD_HEX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../../assembler/builds/hex")
)


@cocotb.test()
async def test_phase5_attn_chain(dut):
    """
    Full Phase 5.1 attention pipeline on real GPU RTL: attn_scores ->
    attn_softmax -> attn_weighted_v, three separate axelcc-compiled kernels
    launched sequentially (fresh DUT reset between each, per launch_kernel's
    default) sharing one data_memory dict -- same mechanism proven by
    test_axelcc_chain, now exercising the real attention math end to end
    including the STMT_IF divergence fix and the exp8()/DIV additions from
    this session.

    Q=K (self-attention) reuses test_phase5_attn_scores's matrix; V is
    test_phase5_attn_weighted_v's matrix. Expected scores/weights/output are
    computed by reference_attention() above, a straightforward Python
    reimplementation of the same integer pipeline (including the real
    EXP8 LUT transcribed from alu.sv) -- independent of both axelcc's
    codegen and the RTL simulation.
    """
    Q_real = [
        [1, 2, 0, 0],
        [0, 1, 1, 0],
        [2, 0, 0, 1],
        [0, 0, 1, 1],
    ]
    V_real = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
        [13, 14, 15, 16],
    ]
    _, _, expected_out_q8 = reference_attention(Q_real, Q_real, V_real)

    instr_scores = load_hex_file(os.path.join(BUILD_HEX, "attn_scores.hex"))
    instr_softmax = load_hex_file(os.path.join(BUILD_HEX, "attn_softmax.hex"))
    instr_wv = load_hex_file(os.path.join(BUILD_HEX, "attn_weighted_v.hex"))

    data_memory = {}
    for i in range(4):
        for k in range(4):
            data_memory[i * 4 + k] = Q_real[i][k] * 256          # Q
            data_memory[16 + i * 4 + k] = Q_real[i][k] * 256     # K = Q
            data_memory[32 + i * 4 + k] = V_real[i][k] * 256     # V

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instr_scores]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(data_memory, 0, 16, 48)  # q_base, k_base, scores_base
    cyc1 = await launch_kernel(dut, instructions_ref, instr_scores, blockDim=4)
    assert cyc1 is not None, "TIMEOUT: attn_scores stage did not finish"

    set_params(data_memory, 48, 64)  # scores_base, weights_base
    cyc2 = await launch_kernel(dut, instructions_ref, instr_softmax, blockDim=4)
    assert cyc2 is not None, "TIMEOUT: attn_softmax stage did not finish"

    set_params(data_memory, 32, 64, 80)  # v_base, weights_base, out_base
    cyc3 = await launch_kernel(dut, instructions_ref, instr_wv, blockDim=4)
    assert cyc3 is not None, "TIMEOUT: attn_weighted_v stage did not finish"

    got = [[None] * 4 for _ in range(4)]
    for i in range(4):
        for k in range(4):
            got[i][k] = u32_to_signed(data_memory.get(80 + i * 4 + k))

    for i in range(4):
        for k in range(4):
            assert got[i][k] == expected_out_q8[i][k], (
                f"out[{i}][{k}]={got[i][k]}, expected {expected_out_q8[i][k]} "
                f"(full got={got}, full expected={expected_out_q8})"
            )

    cocotb.log.info(
        f"attn_chain PASSED: out={got}, cycles=({cyc1},{cyc2},{cyc3})"
    )
