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
        "../../../assembler/builds/hex/dscnn_stem_conv.hex"
    )
)


@cocotb.test()
async def test_dscnn_stem_conv(dut):
    """
    Isolated synthetic test for the DS-CNN stem conv kernel (Cin=1, 5x3
    kernel) -- proves the 15-tap flattening (kh=tap/3, kw=tap%3 over a
    5-row x 3-col window) and that every output channel correctly reads
    the SAME single input plane (no per-channel input offset, unlike
    dscnn_dwconv.axelc), only the per-channel weight differs.

    Weight is one-hot at tap=7 (kh=7/3=2, kw=7%3=1 -- the 5x3 window's
    center) for every output channel, so
    acc[oc][row][col] = bias_eff[oc] + input[row*stride+2][col*stride+1]
    exactly -- fully hand-verifiable.

    Cout=4 (1 block), H_out=W_out=2, stride=1, input is a single 6x4 plane
    (large enough for a "valid" 5x3 conv at H_out=W_out=2:
    row*stride+kh needs rows 0..5, col*stride+kw needs cols 0..3).
    input[row][col] = row*10 + col.

    Center-tap values (row+2, col+1 for row,col in 0..1):
        (0,0)->input[2][1]=21  (0,1)->input[2][2]=22
        (1,0)->input[3][1]=31  (1,1)->input[3][2]=32
    bias_eff[oc] = oc*2 (0, 2, 4, 6), identity requant via per-channel
    mult/shift arrays (mult=256, shift=8 for every channel -> round_bias=
    1<<7=128 derived in-kernel, out_zp=0 -- same derivation as
    test_dscnn_dwconv.py).

    Expected: oc=0:[[21,22],[31,32]] oc=1:[[23,24],[33,34]]
              oc=2:[[25,26],[35,36]] oc=3:[[27,28],[37,38]]
    """
    Cout, H_out, W_out, stride = 4, 2, 2, 1
    H_in, W_padded = 6, 4

    in_base, w_base, bias_eff_base, out_base = 0, 100, 200, 300
    mult_base, shift_base = 400, 420

    data_memory = {}

    # Single shared input plane: input[row][col] = row*10 + col.
    for row in range(H_in):
        for col in range(W_padded):
            data_memory[in_base + row * W_padded + col] = row * 10 + col

    # Weight: one-hot at tap=7 (center of the 5x3 window) for every channel.
    for oc in range(Cout):
        for tap in range(15):
            data_memory[w_base + oc * 15 + tap] = 1 if tap == 7 else 0

    # Bias (already zero-point-folded in the real pipeline; here just a
    # plain per-channel offset, same convention as test_dscnn_dwconv.py).
    for oc in range(Cout):
        data_memory[bias_eff_base + oc] = oc * 2

    # Per-channel mult/shift arrays: identity rescale for every channel.
    for oc in range(Cout):
        data_memory[mult_base + oc] = 256
        data_memory[shift_base + oc] = 8

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions = load_hex_file(HEX_PATH)
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(
        data_memory,
        in_base, out_base, w_base, bias_eff_base,
        H_out, W_out, W_padded,
        stride, mult_base, shift_base, 0,
    )

    cyc = await launch_kernel(
        dut, instructions_ref, instructions, num_blocks=1, blockDim=4
    )
    assert cyc is not None, "TIMEOUT: dscnn_stem_conv did not finish"

    expected = {
        0: [[21, 22], [31, 32]],
        1: [[23, 24], [33, 34]],
        2: [[25, 26], [35, 36]],
        3: [[27, 28], [37, 38]],
    }
    got = {}
    for oc in range(Cout):
        got[oc] = [
            [
                u32_to_signed(data_memory.get(out_base + oc * H_out * W_out + row * W_out + col))
                for col in range(W_out)
            ]
            for row in range(H_out)
        ]

    assert got == expected, f"dscnn_stem_conv: got={got}, expected={expected}"
    cocotb.log.info(f"dscnn_stem_conv PASSED: {got}")
