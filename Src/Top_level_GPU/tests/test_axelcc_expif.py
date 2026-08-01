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
        "../../../assembler/builds/hex/test_expif.hex"
    )
)


@cocotb.test()
async def test_axelcc_expif(dut):
    """
    Verifies if-inside-for and the exp8() builtin reaching real hardware --
    neither combo had ever been exercised by any prior example/test. Needed
    before the Phase 5 softmax kernel, which does both: for(j){ if(d<bound)
    clamp d; e = exp8(d); }.

    d sequence: j=0 -> 0, j=1 -> -32, j=2 -> -64, j=3 -> forced to -128 by
    the if. Expected EXP8 LUT outputs (from alu.sv, hand-read): 127, 77, 47,
    17. total = 127+77+47+17 = 268.
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
    assert cyc is not None, "TIMEOUT: expif did not finish"

    expected = [127, 77, 47, 17]
    got = [u32_to_signed(data_memory.get(j)) for j in range(4)]
    assert got == expected, f"expif: mem[0..3]={got}, expected {expected}"

    total = u32_to_signed(data_memory.get(4))
    assert total == 268, f"expif: mem[4]={total}, expected 268"

    cocotb.log.info(f"axelcc expif PASSED: {got}, total={total}, cycles={cyc}")
