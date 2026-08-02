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
        "../../../assembler/builds/hex/test_fma_alias.hex"
    )
)


@cocotb.test()
async def test_axelcc_fma_alias(dut):
    """
    Regression test for the register-reuse rework's riskiest aliasing
    shape: `fma(a, b, x + y)` with a/b/x/y all permanent parameter
    registers means only `x + y` allocates a temp, and that temp's slot is
    reclaimed and reused as FMA's own destination -- rd == rs3 (the
    accumulate operand), confirmed by hex decode: instruction [5] is
    `FMA R20, R1, R2, R20`. Existing FMA/DOT4 kernels never naturally
    produce this shape (their operands are plain variables/mem loads with
    no reused-temp accumulate argument), and it's a different hazard shape
    than the only previously-proven rd==rs1 case (the for-loop increment).
    This kernel exists purely to force and verify it on real RTL, the same
    empirical-proof discipline used for DIV/MOD and the STMT_IF divergence
    bug earlier this project.

    a=2, b=3, x=4, y=5 -> r = a*b + (x+y) = 6 + 9 = 15
    """
    instructions = load_hex_file(HEX_PATH)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    data_memory = {}
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    set_params(data_memory, 2, 3, 4, 5)  # a, b, x, y
    cyc = await launch_kernel(dut, instructions_ref, instructions)
    assert cyc is not None, "TIMEOUT: fma_alias did not finish"

    got = u32_to_signed(data_memory.get(0))
    assert got == 15, f"fma_alias: mem[0]={got}, expected 15"
    cocotb.log.info(f"axelcc fma_alias PASSED: mem[0]={got}")
