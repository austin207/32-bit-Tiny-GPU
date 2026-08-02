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
        "../../../assembler/builds/hex/test_regreuse_stress.hex"
    )
)


@cocotb.test()
async def test_axelcc_regreuse_stress(dut):
    """
    Regression test proving the register-reuse rework raises the practical
    complexity ceiling, not just shortens code that already worked. Under
    the old bump-until-end-of-statement allocator, this single 9-term sum
    would have needed roughly 2 temps per mem[] load (address + value)
    plus 1 per ADD destination, with zero reuse -- around 18+ simultaneous
    temps against an 8-slot budget, failing to compile with "codegen: out
    of temporary registers". With mark/reset/reuse, hex decode confirms
    peak usage stays at just 4 slots (R20-R23) regardless of chain depth.

    mem[0..8] = 1..9 -> mem[9] = sum(1..9) = 45
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = {i: v for i, v in enumerate(range(1, 10))}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions)
    assert cyc is not None, "TIMEOUT: regreuse_stress did not finish"

    got = u32_to_signed(data_memory.get(9))
    assert got == 45, f"regreuse_stress: mem[9]={got}, expected 45"
    cocotb.log.info(f"axelcc regreuse_stress PASSED: mem[9]={got}")
