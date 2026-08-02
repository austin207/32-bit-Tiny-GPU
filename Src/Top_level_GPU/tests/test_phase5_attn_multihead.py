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

HEAD_STRIDE = 96


@cocotb.test()
async def test_phase5_attn_multihead(dut):
    """
    Multi-head attention: two independent heads (distinct Q/K/V per head --
    not the Q=K self-attention shortcut the single-head tests use), computed
    by the *same* compiled attn_scores/attn_softmax/attn_weighted_v
    binaries, driven with different base addresses via the kernel parameter
    ABI (docs/memory_map.md) instead of a recompile per head. This is the
    reuse the parameter ABI was built for.

    Each head gets its own HEAD_STRIDE=96-word region, head h's regions
    starting at h*96: Q[0:16] K[16:32] V[32:48] scores[48:64] weights[64:80]
    out[80:96]. H=2 is a hard ceiling for this layout, not just "enough
    realism": a 3rd head's region would start at 288, colliding with
    PARAM_BASE (0x100 = 256).

    Concatenating each head's 4x4 output into one [4][8] tensor happens only
    in this test's read-back, matching real multi-head attention's
    concat-then-project structure minus the (out-of-scope) output
    projection.
    """
    heads = [
        {
            "Q": [[1, 2, 0, 0], [0, 1, 1, 0], [2, 0, 0, 1], [0, 0, 1, 1]],
            "K": [[2, 0, 1, 0], [0, 2, 0, 1], [1, 0, 2, 0], [0, 1, 0, 2]],
            "V": [[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16]],
        },
        {
            "Q": [[0, 1, 2, 1], [1, 0, 1, 2], [2, 1, 0, 1], [1, 2, 1, 0]],
            "K": [[1, 1, 0, 0], [0, 1, 1, 0], [0, 0, 1, 1], [1, 0, 0, 1]],
            "V": [[2, 1, 0, 3], [1, 3, 2, 0], [0, 2, 3, 1], [3, 0, 1, 2]],
        },
    ]

    instr_scores = load_hex_file(os.path.join(BUILD_HEX, "attn_scores.hex"))
    instr_softmax = load_hex_file(os.path.join(BUILD_HEX, "attn_softmax.hex"))
    instr_wv = load_hex_file(os.path.join(BUILD_HEX, "attn_weighted_v.hex"))

    data_memory = {}
    expected_out = []
    for h, head in enumerate(heads):
        base = h * HEAD_STRIDE
        q_base, k_base, v_base = base, base + 16, base + 32

        for i in range(4):
            for k in range(4):
                data_memory[q_base + i * 4 + k] = head["Q"][i][k] * 256
                data_memory[k_base + i * 4 + k] = head["K"][i][k] * 256
                data_memory[v_base + i * 4 + k] = head["V"][i][k] * 256

        _, _, out_q8 = reference_attention(head["Q"], head["K"], head["V"])
        expected_out.append(out_q8)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instr_scores]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    for h in range(len(heads)):
        base = h * HEAD_STRIDE
        q_base, k_base, v_base = base, base + 16, base + 32
        scores_base, weights_base, out_base = base + 48, base + 64, base + 80

        set_params(data_memory, q_base, k_base, scores_base)
        cyc = await launch_kernel(dut, instructions_ref, instr_scores, blockDim=4)
        assert cyc is not None, f"TIMEOUT: head {h} attn_scores did not finish"

        set_params(data_memory, scores_base, weights_base)
        cyc = await launch_kernel(dut, instructions_ref, instr_softmax, blockDim=4)
        assert cyc is not None, f"TIMEOUT: head {h} attn_softmax did not finish"

        set_params(data_memory, v_base, weights_base, out_base)
        cyc = await launch_kernel(dut, instructions_ref, instr_wv, blockDim=4)
        assert cyc is not None, f"TIMEOUT: head {h} attn_weighted_v did not finish"

    got_out = []
    for h in range(len(heads)):
        out_base = h * HEAD_STRIDE + 80
        got = [[None] * 4 for _ in range(4)]
        for i in range(4):
            for k in range(4):
                got[i][k] = u32_to_signed(data_memory.get(out_base + i * 4 + k))
        got_out.append(got)

    for h in range(len(heads)):
        for i in range(4):
            for k in range(4):
                assert got_out[h][i][k] == expected_out[h][i][k], (
                    f"head {h} out[{i}][{k}]={got_out[h][i][k]}, "
                    f"expected {expected_out[h][i][k]} "
                    f"(full got={got_out[h]}, full expected={expected_out[h]})"
                )

    cocotb.log.info(f"attn_multihead PASSED: out={got_out}")
