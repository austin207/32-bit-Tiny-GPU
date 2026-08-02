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
        "../../../assembler/builds/hex/test_constfold.hex"
    )
)


@cocotb.test()
async def test_axelcc_constfold(dut):
    """
    Regression test for compile-time constant folding: `int x = 2 + 3 * 4;`
    should collapse to a single CONST instead of a chain of literal-loads
    + runtime ops. Also exercises the case constant folding must decline:
    `int y = -(1 + 2);` folds the inner `1 + 2` (3, in range) but must NOT
    fold the outer negation into CONST, since CONST's 16-bit immediate is
    zero-extended by the hardware (core.sv), not sign-extended -- a folded
    CONST -3 would materialize as 0x0000fffd instead of 0xfffffffd. The
    negation must stay a runtime SUB(R0, x), which does real 32-bit
    arithmetic. Golden-output test (axelcc/tests/golden_test.py) confirms
    the exact instruction shape; this confirms the resulting values are
    correct on real GPU RTL.

    mem[0] = 2 + 3*4 = 14
    mem[1] = -(1+2)  = -3
    """
    instructions = load_hex_file(HEX_PATH)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    data_memory = {}
    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions)
    assert cyc is not None, "TIMEOUT: constfold did not finish"

    got_x = u32_to_signed(data_memory.get(0))
    got_y = u32_to_signed(data_memory.get(1))

    assert got_x == 14, f"constfold: mem[0]={got_x}, expected 14"
    assert got_y == -3, f"constfold: mem[1]={got_y}, expected -3"
    cocotb.log.info(f"axelcc constfold PASSED: mem[0]={got_x} mem[1]={got_y}")
