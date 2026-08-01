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
        "../../../assembler/builds/hex/test_nestedfor.hex"
    )
)


@cocotb.test()
async def test_axelcc_nestedfor(dut):
    """
    Nested for-loops were structurally supported by axelcc (no for_depth
    check in sema.c, codegen.c's STMT_FOR offset math reads live
    g->buf->count so an inner loop's instructions are correctly counted
    into the outer loop's branch offsets) but had never been exercised by
    any example or test. Needed before the Phase 5 QK^T kernel, which
    requires for(j){ for(k){ ... } } to compute each score. Proving it here
    in isolation first.

    total = sum_{i=0..3} sum_{j=0..3} i*j = (0+1+2+3)*(0+1+2+3) = 36
    """
    instructions = load_hex_file(HEX_PATH)
    data_memory = {}

    init_bus(dut)
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    instructions_ref = [instructions]
    cocotb.start_soon(program_memory_model(dut, instructions_ref))
    cocotb.start_soon(data_memory_model(dut, data_memory))

    cyc = await launch_kernel(dut, instructions_ref, instructions)
    assert cyc is not None, "TIMEOUT: nestedfor did not finish"

    got = u32_to_signed(data_memory.get(0))
    assert got == 36, f"nestedfor: mem[0]={got}, expected 36"
    cocotb.log.info(f"axelcc nestedfor PASSED: mem[0]={got}, cycles={cyc}")
