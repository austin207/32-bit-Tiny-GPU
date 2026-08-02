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
        "../../../assembler/builds/hex/dscnn_fc.hex"
    )
)


@cocotb.test()
async def test_dscnn_fc(dut):
    """
    Isolated synthetic test for the DS-CNN fully-connected kernel -- proves
    the blockDim=1/oc=blockIdx thread mapping (deliberately different from
    every other DS-CNN kernel here, since the real model's Cout=18 is not a
    multiple of 4) combined with the same dot4 chunking idiom already
    proven by test_dscnn_pwconv.py.

    Cin=8 (Cin4=2 chunks), Cout=6 (NOT a multiple of 4 -- the whole point
    of this thread-mapping choice). Weight is one-hot per output class: oc
    selects input channel oc, so acc[oc] = bias_eff[oc] + input[oc] exactly.

    input[channel] = channel*3, bias_eff[oc] = oc*2, so
    acc[oc] = oc*2 + oc*3 = oc*5 (identity requant via per-channel
    mult/shift arrays: mult=256, shift=8 for every channel -> round_bias=
    1<<7=128 derived in-kernel, out_zp=0 -> output == acc exactly, same
    derivation as test_dscnn_dwconv.py).

    Expected: oc=0:0 oc=1:5 oc=2:10 oc=3:15 oc=4:20 oc=5:25
    """
    Cin, Cout = 8, 6
    Cin4 = Cin // 4

    in_base, w_base, bias_eff_base, out_base = 0, 100, 200, 300
    mult_base, shift_base = 400, 420

    data_memory = {}

    # Input: input[channel] = channel*3.
    for channel in range(Cin):
        data_memory[in_base + channel] = channel * 3

    # Weight: one-hot per output class -- oc selects input channel oc.
    for oc in range(Cout):
        lanes = [[0, 0, 0, 0], [0, 0, 0, 0]]  # 2 chunks x 4 lanes
        lanes[oc // 4][oc % 4] = 1
        for chunk in range(Cin4):
            packed = 0
            for lane in range(4):
                packed |= (lanes[chunk][lane] & 0xFF) << (8 * lane)
            data_memory[w_base + oc * Cin4 + chunk] = packed

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
        Cin4, mult_base, shift_base, 0,
    )

    cyc = await launch_kernel(
        dut, instructions_ref, instructions, num_blocks=Cout, blockDim=1
    )
    assert cyc is not None, "TIMEOUT: dscnn_fc did not finish"

    expected = {oc: oc * 5 for oc in range(Cout)}
    got = {oc: u32_to_signed(data_memory.get(out_base + oc)) for oc in range(Cout)}

    assert got == expected, f"dscnn_fc: got={got}, expected={expected}"
    cocotb.log.info(f"dscnn_fc PASSED: {got}")
