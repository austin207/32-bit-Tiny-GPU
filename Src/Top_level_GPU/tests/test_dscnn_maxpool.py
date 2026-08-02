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
        "../../../assembler/builds/hex/dscnn_maxpool.hex"
    )
)


@cocotb.test()
async def test_dscnn_maxpool(dut):
    """
    Isolated synthetic test for the DS-CNN global max-pool kernel -- proves
    the running-max reduction (if nested inside for, generalized from
    attn_softmax.axelc's 4-term hand unroll to a real loop) and the
    blockIdx*4+threadIdx channel mapping across more blocks than fit in a
    single wave (num_blocks=2 > NUM_CORES... actually 2 <= 4 cores, so
    both blocks dispatch in parallel -- still proves multi-block dispatch
    combined with a real per-channel reduction, distinct coverage from
    test_axelcc_blockidx.py's pure-arithmetic smoke test).

    C=8 channels (2 blocks of 4), HW=5 spatial positions per channel.
    input[channel][i] = a small sequence per channel with the max placed at
    a different position each time, to prove the reduction doesn't just
    happen to pick position 0 or the last position:
        channel c: values = [c, c+5, c-3, c+2, c+1] except the max is c+5,
        always at index 1 -- pick a DIFFERENT max index per channel instead
        so the test can't accidentally pass via an off-by-one that always
        lands on the same index.

    Values chosen: channel c's 5 values put its max (c*10+50) at index c%5
    and smaller values everywhere else, so channels 0..7 exercise every
    index position 0..4 (with wraparound) as the true max location.

    Expected: out[c] = c*10 + 50 for c in 0..7.
    """
    C, HW = 8, 5
    in_base, out_base = 0, 100

    data_memory = {}
    for c in range(C):
        max_idx = c % HW
        max_val = c * 10 + 50
        for i in range(HW):
            data_memory[in_base + c * HW + i] = max_val if i == max_idx else (c * 10 + i)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions = load_hex_file(HEX_PATH)
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(data_memory, in_base, out_base, HW)

    cyc = await launch_kernel(
        dut, instructions_ref, instructions, num_blocks=2, blockDim=4
    )
    assert cyc is not None, "TIMEOUT: dscnn_maxpool did not finish"

    expected = {c: c * 10 + 50 for c in range(C)}
    got = {c: u32_to_signed(data_memory.get(out_base + c)) for c in range(C)}

    assert got == expected, f"dscnn_maxpool: got={got}, expected={expected}"
    cocotb.log.info(f"dscnn_maxpool PASSED: {got}")
