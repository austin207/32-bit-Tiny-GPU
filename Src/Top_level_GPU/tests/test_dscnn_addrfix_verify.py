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
async def test_dscnn_addrfix_verify(dut):
    """
    Regression guard for the accel ctrl address-decode fix
    (top_level_gpu.sv's accel_sel is bounded to 0x1F0-0x1FF, not an
    open-ended >= 0x1F0 -- see project memory
    project_accel_ctrl_address_ceiling.md for the full story: that open
    ceiling used to silently discard every data-memory write at address
    >= 496, capping every kernel to 496 usable words). Uses the same small
    Cin=8/Cout=8/HW=2 pwconv shape as test_dscnn_pwconv.py, just with
    out_base=600 (previously silently discarded) instead of a
    small-address workaround, to prove addresses >= 0x200 reach real data
    memory. Cheap (~1s), kept in the default regression to catch any
    future re-widening of that decode.
    """
    Cin, Cout, HW = 8, 8, 2
    Cin4 = Cin // 4

    in_base, w_base, bias_eff_base, out_base = 0, 100, 200, 600
    mult_base, shift_base = 400, 420

    data_memory = {}
    for channel in range(Cin):
        for pixel in range(HW):
            data_memory[in_base + channel * HW + pixel] = channel * 2 + pixel

    for oc in range(Cout):
        lanes = [[0, 0, 0, 0], [0, 0, 0, 0]]
        lanes[oc // 4][oc % 4] = 1
        for chunk in range(Cin4):
            packed = 0
            for lane in range(4):
                packed |= (lanes[chunk][lane] & 0xFF) << (8 * lane)
            data_memory[w_base + oc * Cin4 + chunk] = packed

    for oc in range(Cout):
        data_memory[bias_eff_base + oc] = oc * 5

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
    assert cyc is not None, "TIMEOUT"

    expected = {oc: [oc * 7 + pixel for pixel in range(HW)] for oc in range(Cout)}
    got = {
        oc: [u32_to_signed(data_memory.get(out_base + oc * HW + pixel)) for pixel in range(HW)]
        for oc in range(Cout)
    }

    assert got == expected, f"ADDR FIX NOT WORKING: out_base=600 writes missing/wrong: got={got}, expected={expected}"
    cocotb.log.info(f"ADDR FIX CONFIRMED: writes at out_base=600 (>= old 496 ceiling) landed correctly: {got}")
