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
        "../../../assembler/builds/hex/dscnn_pwconv.hex"
    )
)


@cocotb.test()
async def test_dscnn_pwconv(dut):
    """
    Isolated synthetic test for the DS-CNN pointwise (1x1) conv kernel --
    proves the pack-4-planar-loads-then-dot4 idiom (4 LDRs + AND/SHL/OR
    packing into dot4's raw-signed-int8-per-lane layout, matching alu.sv's
    dot_p0..p3) and the multi-chunk accumulation loop (Cin4=2 chunks,
    exercising both chunk 0 and chunk 1, i.e. both dot4 packing groups).

    Cin=8 (Cin4=2 chunks), Cout=8 (2 blocks of 4), HW=2 pixels. Weight is
    one-hot per output channel: output channel oc's weight selects input
    channel oc and zeroes every other lane/chunk, so
    acc[oc][pixel] = bias_eff[oc] + input[oc][pixel] exactly -- fully
    hand-verifiable, and (since oc ranges 0..7) exercises the one-hot lane
    landing in every one of chunk 0's 4 lanes (oc 0-3) and every one of
    chunk 1's 4 lanes (oc 4-7).

    input[channel][pixel] = channel*2 + pixel, bias_eff[oc] = oc*5, so
    acc[oc][pixel] = oc*5 + oc*2 + pixel = oc*7 + pixel (identity requant
    via per-channel mult/shift arrays: mult=256, shift=8 for every channel
    -> round_bias=1<<7=128 derived in-kernel, out_zp=0 -> output == acc
    exactly, same derivation as test_dscnn_dwconv.py).

    Expected: oc=0:[0,1] oc=1:[7,8] oc=2:[14,15] oc=3:[21,22]
              oc=4:[28,29] oc=5:[35,36] oc=6:[42,43] oc=7:[49,50]
    """
    Cin, Cout, HW = 8, 8, 2
    Cin4 = Cin // 4

    in_base, w_base, bias_eff_base, out_base = 0, 100, 200, 300
    mult_base, shift_base = 400, 420

    data_memory = {}

    # Input: input[channel][pixel] = channel*2 + pixel.
    for channel in range(Cin):
        for pixel in range(HW):
            data_memory[in_base + channel * HW + pixel] = channel * 2 + pixel

    # Weight: one-hot per output channel -- oc selects input channel oc.
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
        data_memory[bias_eff_base + oc] = oc * 5

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
        Cin4, HW, mult_base, shift_base, 0,
    )

    cyc = await launch_kernel(
        dut, instructions_ref, instructions, num_blocks=2, blockDim=4
    )
    assert cyc is not None, "TIMEOUT: dscnn_pwconv did not finish"

    expected = {oc: [oc * 7 + pixel for pixel in range(HW)] for oc in range(Cout)}
    got = {
        oc: [u32_to_signed(data_memory.get(out_base + oc * HW + pixel)) for pixel in range(HW)]
        for oc in range(Cout)
    }

    assert got == expected, f"dscnn_pwconv: got={got}, expected={expected}"
    cocotb.log.info(f"dscnn_pwconv PASSED: {got}")
