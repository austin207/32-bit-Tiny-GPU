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
        "../../../assembler/builds/hex/test_func_basic.hex"
    )
)


@cocotb.test()
async def test_axelcc_func_basic(dut):
    """
    First real-RTL exercise of the func/CALL/SRET subroutine mechanism
    (call_stack.sv, decoder.sv opcodes 0x1C/0x1D, pc.sv's call_en/sret_en
    priority logic) -- previously verified only via golden_test.py's
    codegen-only hand trace (see tests/golden_test.py's "test_func_basic"
    entry), never actually simulated on hardware until now.

    Source (axelcc/examples/test_func_basic.axelc):
        func int add3(int a, int b, int c) { return a + b + c; }
        kernel void test_func_basic(int base) {
            int x = add3(1, 2, 3);
            int y = add3(10, 20, 30);
            mem[base] = x;
            mem[base + 1] = y;
        }

    add3 is CALLed twice from the same kernel with the same func body
    (two call sites, one func, no inlining -- the two-pass backpatch and
    the R14-R19 register-window convention are both exercised, and
    calling the same func twice in a row proves no state leaks between
    calls since sema.c never allows more than one call in flight).

    x = add3(1,2,3) = 6, y = add3(10,20,30) = 60. base is itself a kernel
    parameter loaded from PARAM_BASE; chosen as 0 here so the results land
    at mem[0]/mem[1], distinct from PARAM_BASE (0x100) where base itself
    is stored.
    """
    instructions = load_hex_file(HEX_PATH)

    base = 0
    data_memory = {}
    set_params(data_memory, base)

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions)
    assert cyc is not None, "TIMEOUT: test_func_basic did not finish"

    x = u32_to_signed(data_memory.get(base))
    y = u32_to_signed(data_memory.get(base + 1))
    assert x == 6, f"add3(1,2,3): mem[{base}]={x}, expected 6"
    assert y == 60, f"add3(10,20,30): mem[{base + 1}]={y}, expected 60"
    cocotb.log.info(
        f"axelcc test_func_basic PASSED: mem[{base}]={x}, mem[{base + 1}]={y}"
    )
