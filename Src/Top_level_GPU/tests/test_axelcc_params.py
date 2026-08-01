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
        "../../../assembler/builds/hex/test_params.hex"
    )
)

PARAM_BASE = 0x100


@cocotb.test()
async def test_axelcc_params(dut):
    """
    Regression test for axelcc's kernel parameter ABI: `kernel void
    paramtest(int a, int b) { mem[0] = a + b; }` -- parser/sema already
    accepted `kernel void foo(int a, int b)` and registered params as
    symbols, but codegen.c had no case that ever loaded a parameter's value,
    so a reference to it compiled to a read of an uninitialized register.
    Fixed by having codegen() emit LDR from PARAM_BASE+i into each
    parameter's assigned register before the kernel body runs. The host
    supplies argument values the same way it supplies any other kernel
    input: plain writes into data_memory, here at PARAM_BASE/PARAM_BASE+1.

    a=5, b=7 -> mem[0] = 12
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = {PARAM_BASE: 5, PARAM_BASE + 1: 7}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions)
    assert cyc is not None, "TIMEOUT: paramtest did not finish"

    got = u32_to_signed(data_memory.get(0))
    assert got == 12, f"paramtest: mem[0]={got}, expected 12"
    cocotb.log.info(f"axelcc paramtest PASSED: mem[0]={got}")
