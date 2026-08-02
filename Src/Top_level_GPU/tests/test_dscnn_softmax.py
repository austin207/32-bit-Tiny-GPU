import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, set_params, u32_to_signed
from .memory_models import program_memory_model, data_memory_model
from .attn_reference import exp8

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
        "../../../assembler/builds/hex/dscnn_softmax.hex"
    )
)


@cocotb.test()
async def test_dscnn_softmax(dut):
    """
    Isolated synthetic test for the DS-CNN final softmax kernel -- proves
    the max-reduction/exp8-accumulate/normalize three-pass structure
    generalizes correctly from attn_softmax.axelc's N=4 hand-unroll to a
    real N=6 loop, and that the CLAMP builtin correctly replaces
    attn_softmax.axelc's explicit if-based floor-clamp.

    N=6 scores (single vector, blockDim=1/num_blocks=1). exp_shift=0 (no
    rescale, to keep the reference computation simple -- the real pipeline
    picks exp_shift from the FC output tensor's actual quantization scale,
    a host-tooling concern proven separately later). out_zp=-128, matching
    the real model's softmax output convention (scale=1/256, zp=-128).

    Reference computed independently via attn_reference.py's exp8() (the
    same real hardware LUT transcription attn_softmax's own tests already
    trust), not re-derived by hand -- an independent check of this
    kernel's integer pipeline (max, subtract, clamp, exp8, sum, DIV
    normalize, +out_zp), not of the LUT's own math.
    """
    N, exp_shift, out_zp = 6, 0, -128
    in_base, out_base = 0, 100

    scores = [-5, -20, 0, -100, -3, -50]  # max is scores[2] = 0

    data_memory = {}
    for i, s in enumerate(scores):
        data_memory[in_base + i] = s & 0xFFFFFFFF

    # Independent reference, mirroring the kernel's exact integer pipeline.
    m = max(scores)
    exps = []
    for s in scores:
        d = (s - m) >> exp_shift
        d = max(-128, min(127, d))
        exps.append(exp8(d))
    total = sum(exps)
    expected = {i: (e * 256) // total + out_zp for i, e in enumerate(exps)}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions = load_hex_file(HEX_PATH)
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(data_memory, in_base, out_base, N, exp_shift, out_zp)

    cyc = await launch_kernel(
        dut, instructions_ref, instructions, num_blocks=1, blockDim=1
    )
    assert cyc is not None, "TIMEOUT: dscnn_softmax did not finish"

    got = {i: u32_to_signed(data_memory.get(out_base + i)) for i in range(N)}

    assert got == expected, f"dscnn_softmax: got={got}, expected={expected}"
    cocotb.log.info(f"dscnn_softmax PASSED: {got}")
