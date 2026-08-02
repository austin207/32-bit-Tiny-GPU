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
        "../../../assembler/builds/hex/dscnn_dwconv.hex"
    )
)


@cocotb.test()
async def test_dscnn_dwconv(dut):
    """
    Isolated synthetic test for the DS-CNN depthwise 3x3 conv kernel -- the
    riskiest/most novel kernel in the DS-CNN plan: first 3-level nested
    for-loop (row/col/tap) and first param-driven (non-constant) loop bound
    in this codebase, plus the first real use of the tap/3, tap%3 DIV/MOD
    idiom to flatten a 3x3 window into one loop.

    Test data is deliberately a one-hot weight (only tap=4, the 3x3 center,
    is 1; every other tap is 0), so acc = bias_eff[channel] + input[row+1][col+1]
    exactly -- fully hand-verifiable without needing a separate reference
    implementation, and still exercises every real code path (channel
    mapping, 3-level nesting, DIV/MOD tap decode, FMA accumulate across all
    9 taps -- including the 8 zero-weight ones, addressing, and the full
    requant+clamp pipeline with an identity-scale (mult=256, shift=8 ->
    round_bias=1<<7=128 derived in-kernel, out_zp=0) so output == acc
    exactly. mult/shift are per-channel arrays (mult_base/shift_base), not
    scalars -- the real model's per-channel weight quantization means each
    invocation genuinely uses a different scale per output channel; every
    channel gets the same identity scale here for hand-verifiability, but
    the array-indexed ABI itself is exercised for real).

    Layout: C=4 channels, H_padded=W_padded=4, H_out=W_out=2, stride=1
    (a "valid" 3x3 conv over the 4x4 input, no real padding involved --
    padding correctness is a host-tooling concern proven separately at the
    full end-to-end chain test).

    input[r][col] = r - col for all channels (4x4 grid, values -3..3):
        row 1: [1, 0, -1, -2]
        row 2: [2, 1, 0, -1]
    so the only taps that matter (row+1, col+1 for row,col in 0..1):
        (0,0)->input[1][1]=0   (0,1)->input[1][2]=-1
        (1,0)->input[2][1]=1   (1,1)->input[2][2]=0
    bias_eff[c] = c*10 (0, 10, 20, 30)

    Expected acc[c][row][col] = bias_eff[c] + centertap:
        c=0: [[0,-1],[1,0]]    c=1: [[10,9],[11,10]]
        c=2: [[20,19],[21,20]] c=3: [[30,29],[31,30]]
    """
    C, H_padded, W_padded, H_out, W_out, stride = 4, 4, 4, 2, 2, 1

    in_base, w_base, bias_eff_base, out_base = 0, 64, 100, 200
    mult_base, shift_base = 300, 320

    data_memory = {}

    # Input: same 4x4 grid for every channel, input[r][col] = r - col.
    for c in range(C):
        for r in range(4):
            for col in range(4):
                data_memory[in_base + c * H_padded * W_padded + r * W_padded + col] = \
                    (r - col) & 0xFFFFFFFF

    # Weights: one-hot, only tap=4 (center) is 1, all others 0.
    for c in range(C):
        for tap in range(9):
            data_memory[w_base + c * 9 + tap] = 1 if tap == 4 else 0

    # Bias (already zero-point-folded in the real pipeline; here just a
    # plain per-channel offset since this test isn't modeling real
    # TFLite zero-points).
    for c in range(C):
        data_memory[bias_eff_base + c] = c * 10

    # Per-channel mult/shift arrays: identity rescale (mult=256, shift=8)
    # for every channel, so acc passes through unchanged (round_bias=1<<7
    # is derived in-kernel from shift).
    for c in range(C):
        data_memory[mult_base + c] = 256
        data_memory[shift_base + c] = 8

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions = load_hex_file(HEX_PATH)
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    # mult_base/shift_base point to identity-rescale arrays, out_zp=0 ->
    # output == acc exactly (see docstring derivation).
    set_params(
        data_memory,
        in_base, out_base, w_base, bias_eff_base,
        H_out, W_out, H_padded, W_padded,
        stride, mult_base, shift_base, 0,
    )

    cyc = await launch_kernel(
        dut, instructions_ref, instructions, num_blocks=1, blockDim=4
    )
    assert cyc is not None, "TIMEOUT: dscnn_dwconv did not finish"

    expected = {
        0: [[0, -1], [1, 0]],
        1: [[10, 9], [11, 10]],
        2: [[20, 19], [21, 20]],
        3: [[30, 29], [31, 30]],
    }
    got = {}
    for c in range(C):
        got[c] = [
            [
                u32_to_signed(data_memory.get(out_base + c * H_out * W_out + row * W_out + col))
                for col in range(W_out)
            ]
            for row in range(H_out)
        ]

    assert got == expected, f"dscnn_dwconv: got={got}, expected={expected}"
    cocotb.log.info(f"dscnn_dwconv PASSED: {got}")
