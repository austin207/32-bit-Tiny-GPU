import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from .common import init_bus, launch_kernel, u32_to_signed
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
        "../../../assembler/builds/hex/test_clamp_builtin.hex"
    )
)


@cocotb.test()
async def test_axelcc_clamp_builtin(dut):
    """
    Regression test for the newly wired EXPR_CLAMP codegen (opcode 0x18,
    alu.sv: saturates to signed int8 range [-128, 127]). CLAMP was already
    decoded/wired in hardware (decoder.sv groups 0x18 with the other ALU
    write-back ops) but had zero axelcc frontend/backend support until now
    -- same shape as the earlier RELU gap, fixed identically. This op is
    load-bearing for the upcoming DS-CNN kernels' int8 requantization step
    (clamp(((acc*mult+round_bias)>>shift)+out_zp)), so it needs its own
    proof on real RTL before any conv kernel depends on it.

    mem[0..3] = [200, -200, 50, -50] -> mem[4..7] = [127, -128, 50, -50]
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = {0: 200, 1: 0xFFFFFF38, 2: 50, 3: 0xFFFFFFCE}  # -200, -50

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions, blockDim=4)
    assert cyc is not None, "TIMEOUT: clamp_builtin did not finish"

    expected = {4: 127, 5: -128, 6: 50, 7: -50}
    got = {addr: u32_to_signed(data_memory.get(addr)) for addr in expected}

    assert got == expected, f"clamp_builtin: got={got}, expected={expected}"
    cocotb.log.info(f"axelcc clamp_builtin PASSED: {got}")
