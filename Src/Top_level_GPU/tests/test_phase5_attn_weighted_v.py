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
        "../../../assembler/builds/hex/attn_weighted_v.hex"
    )
)


@cocotb.test()
async def test_phase5_attn_weighted_v(dut):
    """
    Phase 5.1 stage 3: out = weights @ V on real GPU RTL, seq_len=4,
    d_model=4, Q8 fixed-point.

    V_real:
      r0=[1,2,3,4]  r1=[5,6,7,8]  r2=[9,10,11,12]  r3=[13,14,15,16]

    weights_real (row i = attention distribution for query i):
      row0 = [0.5, 0.5, 0, 0]  -> averages V0 and V1
      row1 = [0, 1, 0, 0]      -> one-hot, copies V1
      row2 = [0, 0, 1, 0]      -> one-hot, copies V2
      row3 = [0, 0, 0, 1]      -> one-hot, copies V3

    expected out_real:
      row0 = [3, 4, 5, 6]   (average of V0, V1)
      row1 = [5, 6, 7, 8]
      row2 = [9, 10, 11, 12]
      row3 = [13, 14, 15, 16]
    """
    V_real = [
        [1, 2, 3, 4],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
        [13, 14, 15, 16],
    ]
    weights_q8 = [
        [128, 128, 0, 0],
        [0, 256, 0, 0],
        [0, 0, 256, 0],
        [0, 0, 0, 256],
    ]
    expected = [
        [3, 4, 5, 6],
        [5, 6, 7, 8],
        [9, 10, 11, 12],
        [13, 14, 15, 16],
    ]

    data_memory = {}
    for j in range(4):
        for k in range(4):
            data_memory[32 + j * 4 + k] = (V_real[j][k] * 256) & 0xFFFFFFFF
    for i in range(4):
        for j in range(4):
            data_memory[64 + i * 4 + j] = weights_q8[i][j] & 0xFFFFFFFF

    instructions = load_hex_file(HEX_PATH)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(data_memory, 32, 64, 80)  # v_base, weights_base, out_base
    cyc = await launch_kernel(dut, instructions_ref, instructions, blockDim=4)
    assert cyc is not None, "TIMEOUT: attn_weighted_v did not finish"

    got = [[None] * 4 for _ in range(4)]
    for i in range(4):
        for k in range(4):
            got[i][k] = u32_to_signed(data_memory.get(80 + i * 4 + k))

    for i in range(4):
        for k in range(4):
            exp_q8 = expected[i][k] * 256
            assert got[i][k] == exp_q8, (
                f"out[{i}][{k}]={got[i][k]}, expected {exp_q8} "
                f"(full got={got}, full expected_q8=" +
                str([[e * 256 for e in row] for row in expected]) + ")"
            )

    cocotb.log.info(f"attn_weighted_v PASSED: {got}, cycles={cyc}")
